"""ペルソナごとの情報収集。

各ペルソナについて
1. サーバー側 web 検索で「その人が今日読みたい情報」を探させ、JSON で抽出
2. （任意）購読 RSS を取得し、ペルソナ視点で取捨選択・要約
を行い、CollectedItem のリストにまとめる。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from pydantic import ValidationError

from .config import Settings
from .llm import Backend, RefusedError, extract_json
from .models import CollectedItem, ExtractedItems, Item, Persona, RssRatings
from .rss import FeedEntry, fetch_feed

log = logging.getLogger(__name__)

SEARCH_SYSTEM = """\
あなたは情報収集エージェントです。与えられた「仮想ペルソナ」になりきり、
その人物が今日まさに読みたい・知りたい最新情報を web 検索で探してください。

手順:
1. ペルソナの関心事と検索クエリをもとに、複数回 web 検索を行う（できるだけ異なる角度で）。
2. 見つけた情報のうち、そのペルソナが本当に関心を持つものだけを選ぶ。
3. 最後に、必ず次の形式の JSON 配列を ```json フェンスで囲んで出力する。前後の説明文は最小限に。

[
  {
    "title": "記事タイトル",
    "url": "https://...",
    "summary": "内容の要約 1〜3 文（{language}）",
    "why_it_matters": "なぜこのペルソナに重要か 1 文",
    "topics": ["トピック", "タグ"],
    "interest": 1〜5 の整数,
    "published": "YYYY-MM-DD または空文字"
  }
]

制約:
- url は検索結果に実際に含まれていたものだけを使う。捏造しない。
- 同じ記事の重複は避ける。最大 {max_items} 件。
- 古い定番情報ではなく、直近の動き・ニュース・発表を優先する。
"""

EXTRACT_SYSTEM = """\
与えられたテキストから、記事情報の一覧を構造化して抽出してください。
URL はテキストに現れたものだけを使い、捏造しないでください。
"""

RSS_SYSTEM = """\
あなたは与えられた「仮想ペルソナ」本人です。購読フィードの新着一覧を見て、
自分が本当に読みたいものだけを keep=true にし、要約と関心度（1〜5）を付けてください。
興味のないものは keep=false にし、summary は空で構いません。
"""


def collect_for_persona(
    backend: Backend, persona: Persona, settings: Settings
) -> list[CollectedItem]:
    items: list[CollectedItem] = []
    items += _collect_web(backend, persona, settings)
    if settings.use_rss and persona.rss_feeds:
        items += _collect_rss(backend, persona, settings)
    return _dedupe(items)


def collect_all(
    backend: Backend,
    personas: list[Persona],
    settings: Settings,
    *,
    on_progress: Callable[[Persona, list[CollectedItem] | None, Exception | None], None]
    | None = None,
) -> list[CollectedItem]:
    """全ペルソナを並列に収集する。個別の失敗は記録して続行する。"""
    results: list[CollectedItem] = []
    with ThreadPoolExecutor(max_workers=max(1, settings.workers)) as pool:
        futures = {
            pool.submit(collect_for_persona, backend, p, settings): p for p in personas
        }
        for fut in as_completed(futures):
            persona = futures[fut]
            try:
                got = fut.result()
            except Exception as exc:  # noqa: BLE001 - 1 人の失敗で全体を止めない
                log.warning("collect failed for %s: %s", persona.short(), exc)
                if on_progress:
                    on_progress(persona, None, exc)
                continue
            results.extend(got)
            if on_progress:
                on_progress(persona, got, None)
    return results


# ---------------------------------------------------------------------------


def _persona_block(persona: Persona) -> str:
    lines = [
        f"名前: {persona.name}",
        f"年齢: {persona.age}",
        f"職業: {persona.occupation}",
        f"居住地: {persona.location}",
        f"人物像: {persona.bio}",
        f"関心事: {', '.join(persona.interests)}",
        f"よく使う検索クエリ: {' / '.join(persona.search_queries)}",
        f"主に読む言語: {persona.language}",
    ]
    if persona.preferred_domains:
        lines.append(f"よく読むサイト: {', '.join(persona.preferred_domains)}")
    return "\n".join(lines)


def _collect_web(backend: Backend, persona: Persona, settings: Settings) -> list[CollectedItem]:
    system = SEARCH_SYSTEM.replace("{language}", settings.language).replace(
        "{max_items}", str(settings.max_items_per_persona)
    )
    user = "以下のペルソナとして情報収集してください。\n\n" + _persona_block(persona)
    try:
        result = backend.search(
            system, user, max_uses=settings.max_searches, model=settings.collector_model
        )
    except RefusedError as exc:
        log.warning("search refused for %s: %s", persona.short(), exc)
        return []

    items = _parse_items(result.text)
    if items is None:
        # JSON が崩れていた場合は構造化抽出でリカバリする
        try:
            extracted = backend.structured(
                ExtractedItems,
                EXTRACT_SYSTEM,
                result.text,
                model=settings.collector_model,
            )
            items = extracted.items
        except Exception as exc:  # noqa: BLE001
            log.warning("extraction fallback failed for %s: %s", persona.short(), exc)
            items = []

    known_urls = {s["url"] for s in result.sources}
    out: list[CollectedItem] = []
    for it in items[: settings.max_items_per_persona]:
        if not it.url.startswith("http"):
            continue
        if known_urls and it.url not in known_urls and not _same_page(it.url, known_urls):
            log.debug("dropping URL not present in search results: %s", it.url)
            continue
        out.append(CollectedItem(persona_id=persona.id, **it.model_dump()))
    return out


def _same_page(url: str, known: set[str]) -> bool:
    """検索結果の URL と末尾スラッシュや http/https 違いだけなら同一と見なす。"""
    norm = url.rstrip("/").replace("http://", "https://")
    return any(k.rstrip("/").replace("http://", "https://") == norm for k in known)


def _parse_items(text: str) -> list[Item] | None:
    try:
        data = extract_json(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return None
    items: list[Item] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        try:
            raw.setdefault("source", "web")
            raw["interest"] = _clamp_int(raw.get("interest", 3))
            items.append(Item(**{k: v for k, v in raw.items() if k in Item.model_fields}))
        except ValidationError:
            continue
    return items


def _clamp_int(value, lo: int = 1, hi: int = 5) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 3
    return max(lo, min(hi, v))


def _collect_rss(backend: Backend, persona: Persona, settings: Settings) -> list[CollectedItem]:
    entries: list[FeedEntry] = []
    for feed in persona.rss_feeds[:3]:
        entries += fetch_feed(feed, limit=settings.rss_entries_per_feed)
    if not entries:
        return []
    listing = "\n".join(
        f"[{i}] {e.title}\n    {e.url}\n    {e.published} {e.summary[:300]}"
        for i, e in enumerate(entries)
    )
    user = (
        "ペルソナ:\n" + _persona_block(persona) + "\n\n新着エントリ:\n" + listing +
        f"\n\n要約は {settings.language} で書いてください。"
    )
    try:
        ratings = backend.structured(RssRatings, RSS_SYSTEM, user, model=settings.collector_model)
    except Exception as exc:  # noqa: BLE001
        log.warning("rss rating failed for %s: %s", persona.short(), exc)
        return []
    out: list[CollectedItem] = []
    for r in ratings.ratings:
        if not r.keep or not (0 <= r.index < len(entries)):
            continue
        e = entries[r.index]
        out.append(
            CollectedItem(
                persona_id=persona.id,
                title=e.title,
                url=e.url,
                summary=r.summary or e.summary[:200],
                why_it_matters=r.why_it_matters,
                topics=r.topics,
                interest=_clamp_int(r.interest),
                published=e.published,
                source="rss",
            )
        )
    return out


def _dedupe(items: list[CollectedItem]) -> list[CollectedItem]:
    seen: set[str] = set()
    out: list[CollectedItem] = []
    for it in items:
        key = it.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out
