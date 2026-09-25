"""Claude API の薄いラッパー。

- ``structured()``: Pydantic スキーマに沿った JSON を返させる
- ``search()``: サーバー側 web 検索ツールを使って調査させ、本文と参照 URL を返す

``Backend`` プロトコルを満たす別実装（``mock.MockBackend``）を差し替えることで、
API キーなしでもパイプライン全体を動かせる。
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    """スレッドセーフなトークン使用量カウンタ。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    requests: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, usage) -> None:
        if usage is None:
            return
        with self._lock:
            self.requests += 1
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
            self.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.cache_creation_input_tokens += (
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )

    def as_dict(self) -> dict[str, int]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }


@dataclass
class SearchResult:
    text: str
    sources: list[dict[str, str]]  # {"url": ..., "title": ...}


class Backend(Protocol):
    usage: Usage

    def structured(
        self, schema: type[T], system: str, user: str, *, model: str | None = None
    ) -> T: ...

    def search(
        self,
        system: str,
        user: str,
        *,
        max_uses: int = 5,
        allowed_domains: list[str] | None = None,
        model: str | None = None,
    ) -> SearchResult: ...


class RefusedError(RuntimeError):
    """モデルが安全上の理由で応答を拒否した。"""


WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeBackend:
    """Anthropic SDK を使う本番バックエンド。"""

    def __init__(self, model: str, effort: str = "high", timeout: float = 600.0):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=timeout)
        self.model = model
        self.effort = effort
        self.usage = Usage()

    # ----------------------------------------------------------- structured
    def structured(
        self, schema: type[T], system: str, user: str, *, model: str | None = None
    ) -> T:
        response = self.client.messages.parse(
            model=model or self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
        )
        self.usage.add(response.usage)
        if response.stop_reason == "refusal":
            raise RefusedError(_refusal_message(response))
        if response.parsed_output is None:
            raise RuntimeError("structured output missing (stop_reason=%s)" % response.stop_reason)
        return response.parsed_output

    # --------------------------------------------------------------- search
    def search(
        self,
        system: str,
        user: str,
        *,
        max_uses: int = 5,
        allowed_domains: list[str] | None = None,
        model: str | None = None,
    ) -> SearchResult:
        tool: dict = {"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_uses}
        if allowed_domains:
            tool["allowed_domains"] = allowed_domains

        messages: list[dict] = [{"role": "user", "content": user}]
        sources: dict[str, str] = {}
        response = None
        for _ in range(6):  # pause_turn の再開上限
            response = self.client.beta.messages.create(
                model=model or self.model,
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=[tool],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            self.usage.add(response.usage)
            _collect_sources(response.content, sources)
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break

        assert response is not None
        if response.stop_reason == "refusal":
            raise RefusedError(_refusal_message(response))

        text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return SearchResult(
            text=text, sources=[{"url": u, "title": t} for u, t in sources.items()]
        )


def _refusal_message(response) -> str:
    details = getattr(response, "stop_details", None)
    if details is None:
        return "refused"
    return f"refused ({getattr(details, 'category', None)}): {getattr(details, 'explanation', '')}"


def _collect_sources(content, sources: dict[str, str]) -> None:
    """web_search_tool_result と citations から参照 URL を集める。"""
    for block in content:
        btype = getattr(block, "type", "")
        if btype == "web_search_tool_result":
            results = getattr(block, "content", None)
            if isinstance(results, list):  # エラー時は list ではなく単一オブジェクト
                for r in results:
                    url = getattr(r, "url", None)
                    if url:
                        sources.setdefault(url, getattr(r, "title", "") or "")
        elif btype == "text":
            for c in getattr(block, "citations", None) or []:
                url = getattr(c, "url", None)
                if url:
                    sources.setdefault(url, getattr(c, "title", "") or "")


# ---------------------------------------------------------------------------
# テキストからの JSON 抽出（web 検索付き応答は structured output と併用できないため）
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str):
    """応答テキストから最初に見つかった JSON（配列/オブジェクト）を返す。"""
    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)]
    candidates.append(text)
    for cand in candidates:
        cand = cand.strip()
        # 先に出現した括弧の種類から試す（配列の中の配列を誤って拾わないため）
        pairs = sorted(
            (p for p in (("[", "]"), ("{", "}")) if cand.find(p[0]) != -1),
            key=lambda p: cand.find(p[0]),
        )
        for opener, closer in pairs:
            start = cand.find(opener)
            end = cand.rfind(closer)
            if end > start:
                try:
                    return json.loads(cand[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("no JSON found in response")


def make_backend(settings) -> Backend:
    if settings.mock:
        from .mock import MockBackend

        return MockBackend()
    return ClaudeBackend(model=settings.model, effort=settings.effort)
