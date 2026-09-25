"""API キーなしでパイプライン全体を試すためのオフラインバックエンド。

決定的な疑似データを返す。テストと `--mock` フラグで使う。
"""

from __future__ import annotations

import hashlib
import json
import re

from .llm import SearchResult, Usage
from .models import (
    Cluster,
    DigestAnalysis,
    ExtractedItems,
    Item,
    PersonaBatch,
    PersonaDraft,
    RssRating,
    RssRatings,
)

_ARCHETYPES = [
    ("スポーツ", ["サッカー 日本代表", "MLB 大谷翔平", "箱根駅伝"], "スポーツ紙記者"),
    ("洋楽", ["Billboard Hot 100", "グラミー賞 ノミネート", "新譜 リリース"], "レコード店員"),
    ("AI", ["LLM 新モデル", "生成AI 規制", "GPU 供給"], "機械学習エンジニア"),
    ("金融", ["日銀 利上げ", "米国 CPI", "半導体株"], "個人投資家"),
    ("農業", ["米価 動向", "スマート農業", "農林水産省 補助金"], "稲作農家"),
    ("医療", ["新薬 承認", "感染症 流行", "医師 働き方改革"], "内科医"),
    ("ゲーム", ["Switch 新作", "Steam セール", "eスポーツ 大会"], "ゲーム実況者"),
    ("政治", ["国会 法案", "選挙 情勢", "外交 首脳会談"], "地方議員秘書"),
    ("教育", ["大学入試 改革", "GIGAスクール", "不登校 支援"], "高校教師"),
    ("環境", ["再生可能エネルギー", "カーボンプライシング", "気候変動 会議"], "環境NPO職員"),
]

_SHARED_TOPICS = ["生成AI", "半導体", "円安", "選挙"]


def _h(s: str) -> int:
    return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)


class MockBackend:
    def __init__(self):
        self.usage = Usage()
        self._counter = 0

    def structured(self, schema, system: str, user: str, *, model: str | None = None):
        self._counter += 1
        if schema is PersonaBatch:
            return self._personas(user)
        if schema is ExtractedItems:
            return ExtractedItems(items=[])
        if schema is RssRatings:
            n = len(re.findall(r"^\[(\d+)\]", user, re.M))
            return RssRatings(
                ratings=[
                    RssRating(index=i, keep=(i % 2 == 0), interest=4, summary=f"mock 要約 {i}",
                              why_it_matters="mock", topics=["rss"])
                    for i in range(n)
                ]
            )
        if schema is DigestAnalysis:
            return self._analysis(user)
        raise TypeError(f"mock does not support {schema}")

    def search(self, system, user, *, max_uses=5, allowed_domains=None, model=None) -> SearchResult:
        self._counter += 1
        m = re.search(r"関心事: (.+)", user)
        interests = [s.strip() for s in (m.group(1) if m else "一般").split(",")]
        name_m = re.search(r"名前: (.+)", user)
        seed = name_m.group(1) if name_m else user[:20]
        items: list[Item] = []
        for i, interest in enumerate(interests[:4]):
            slug = _h(interest) % 10_000
            items.append(
                Item(
                    title=f"{interest} に関する最新の動き #{slug}",
                    url=f"https://example.com/news/{slug}",
                    summary=f"{interest} 分野で新しい発表があった（モックデータ）。",
                    why_it_matters=f"{seed} の関心事 {interest} に直結する。",
                    topics=[interest],
                    interest=3 + (i % 3),
                    published="2026-09-25",
                )
            )
        # 全ペルソナに共通するニュースを 1〜2 件混ぜ、横断シグナルを再現する
        for t in _SHARED_TOPICS[: 1 + _h(seed) % 2]:
            items.append(
                Item(
                    title=f"{t} をめぐる大きな動き",
                    url=f"https://example.com/shared/{_h(t) % 100}",
                    summary=f"{t} について社会全体に影響する報道（モックデータ）。",
                    why_it_matters=f"{seed} の生活や仕事にも影響が及ぶ。",
                    topics=[t, "社会"],
                    interest=4,
                    published="2026-09-24",
                )
            )
        sources = [{"url": it.url, "title": it.title} for it in items]
        text = "調査結果です。\n```json\n" + json.dumps(
            [it.model_dump(exclude={"source"}) for it in items], ensure_ascii=False
        ) + "\n```"
        return SearchResult(text=text, sources=sources)

    # ------------------------------------------------------------------
    def _personas(self, user: str) -> PersonaBatch:
        m = re.search(r"を (\d+) 人作", user)
        n = int(m.group(1)) if m else 10
        existing = len(re.findall(r"^- ", user, re.M))
        drafts = []
        for i in range(n):
            k = existing + i
            field, queries, occupation = _ARCHETYPES[k % len(_ARCHETYPES)]
            drafts.append(
                PersonaDraft(
                    name=f"仮想人物{k + 1:02d}",
                    age=18 + (k * 7) % 60,
                    occupation=occupation,
                    location=["東京", "大阪", "札幌", "福岡", "ロンドン", "シンガポール"][k % 6],
                    bio=f"{field} を軸に情報を追う人物（モック）。",
                    interests=[field, f"{field} の最新動向", "地域ニュース"],
                    search_queries=queries,
                    preferred_domains=[],
                    rss_feeds=[],
                    language="ja",
                )
            )
        return PersonaBatch(personas=drafts)

    def _analysis(self, user: str) -> DigestAnalysis:
        keys = re.findall(r"^key: (\S+)", user, re.M)
        clusters = [
            Cluster(
                name="共通シグナル",
                summary="複数のペルソナが同時に注目した事象。",
                significance="社会全体に波及している可能性が高い。",
                item_keys=[k for k in keys if "/shared/" in k],
            ),
            Cluster(
                name="分野別の動き",
                summary="各ペルソナの専門領域の動き。",
                significance="個別分野の変化。",
                item_keys=[k for k in keys if "/news/" in k][:20],
            ),
        ]
        return DigestAnalysis(
            headline="モック実行: 横断シグナルと分野別トピック",
            overview="モックバックエンドによる俯瞰。共通トピックが複数ペルソナに観測された。",
            clusters=[c for c in clusters if c.item_keys],
            cross_cutting=["生成AI と半導体の話題が分野を超えて観測された"],
            weak_signals=["特定ペルソナのみが捉えた専門領域の動き"],
            blind_spots=["宗教・思想", "南米・アフリカ地域"],
        )
