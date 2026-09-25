"""データモデル。LLM に返させるスキーマと、内部で扱う集約データの両方。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ペルソナ
# ---------------------------------------------------------------------------


class PersonaDraft(BaseModel):
    """LLM が生成するペルソナ（id は後で付与する）。"""

    name: str = Field(description="フルネーム。実在の人物と重ならない架空の名前")
    age: int = Field(description="年齢")
    occupation: str = Field(description="職業や立場")
    location: str = Field(description="居住地（国・都市）")
    bio: str = Field(description="人物像を 2〜3 文で。価値観、日課、情報の集め方")
    interests: list[str] = Field(description="強い関心事 4〜8 個。具体的に")
    search_queries: list[str] = Field(
        description="この人物が最新情報を追うために実際に検索しそうなクエリ 5〜8 個。母語で"
    )
    preferred_domains: list[str] = Field(
        default_factory=list,
        description="よく読むサイトのドメイン 0〜5 個（例: nikkei.com）。ホスト名のみ",
    )
    rss_feeds: list[str] = Field(
        default_factory=list,
        description="購読していそうな公開 RSS/Atom フィードの完全な URL 0〜3 個。確実に存在するものだけ",
    )
    language: str = Field(default="ja", description="主に情報を読む言語コード (ja, en, ...)")


class PersonaBatch(BaseModel):
    personas: list[PersonaDraft]


class Persona(PersonaDraft):
    id: str

    def short(self) -> str:
        return f"{self.name}（{self.age}・{self.occupation}・{self.location}）"


# ---------------------------------------------------------------------------
# 収集アイテム
# ---------------------------------------------------------------------------


class Item(BaseModel):
    """1 件の情報。LLM が web 検索結果から抽出する。"""

    title: str
    url: str
    summary: str = Field(description="内容の要約 1〜3 文")
    why_it_matters: str = Field(default="", description="なぜこのペルソナにとって重要か 1 文")
    topics: list[str] = Field(default_factory=list, description="トピックタグ 1〜4 個")
    interest: int = Field(default=3, description="ペルソナにとっての関心度 1〜5")
    published: str = Field(default="", description="公開日が分かれば YYYY-MM-DD。不明なら空文字")
    source: str = Field(default="web", description="web または rss")


class ExtractedItems(BaseModel):
    items: list[Item]


class CollectedItem(Item):
    persona_id: str


class RssRating(BaseModel):
    index: int = Field(description="評価対象エントリの index")
    keep: bool = Field(description="このペルソナが読みたいと思う内容なら true")
    interest: int = Field(description="関心度 1〜5")
    summary: str = Field(default="", description="要約 1〜2 文（keep=true のとき）")
    why_it_matters: str = Field(default="")
    topics: list[str] = Field(default_factory=list)


class RssRatings(BaseModel):
    ratings: list[RssRating]


# ---------------------------------------------------------------------------
# 集約
# ---------------------------------------------------------------------------


class AggregatedItem(BaseModel):
    key: str
    title: str
    url: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    published: str = ""
    source: str = "web"
    seen_by: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    interests: list[int] = Field(default_factory=list)

    @property
    def reach(self) -> int:
        return len(self.seen_by)

    @property
    def avg_interest(self) -> float:
        if not self.interests:
            return 0.0
        return sum(self.interests) / len(self.interests)

    @property
    def score(self) -> float:
        """到達ペルソナ数と平均関心度から算出する重要度。"""
        return self.reach * 2.0 + self.avg_interest


class Cluster(BaseModel):
    name: str = Field(description="クラスタ名。短く具体的に")
    summary: str = Field(description="このクラスタで何が起きているか 2〜4 文")
    significance: str = Field(description="全体像の中での位置づけ・なぜ注目すべきか 1〜2 文")
    item_keys: list[str] = Field(description="所属するアイテムの key")


class DigestAnalysis(BaseModel):
    headline: str = Field(description="今回の俯瞰を一言で表す見出し")
    overview: str = Field(description="全体像の俯瞰。300〜600 字。何が起き、何が繋がっているか")
    clusters: list[Cluster] = Field(description="トピッククラスタ 5〜12 個")
    cross_cutting: list[str] = Field(
        description="複数の異なるペルソナ（分野）にまたがって現れた横断的な動き・洞察 3〜7 個"
    )
    weak_signals: list[str] = Field(
        description="1〜2 人のペルソナしか見ていないが、今後大きくなりうる弱いシグナル 3〜7 個"
    )
    blind_spots: list[str] = Field(
        description="現在のペルソナ構成では拾えていなさそうな領域・視点 2〜5 個"
    )


class Digest(BaseModel):
    run_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    persona_count: int
    item_count: int
    analysis: DigestAnalysis
    items: list[AggregatedItem]
    usage: dict[str, int] = Field(default_factory=dict)
