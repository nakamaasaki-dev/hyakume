"""仮想ペルソナの生成。

多様性を確保するため、少人数ずつバッチで生成し、既に作った人物像を
「避けるべきもの」としてプロンプトに渡す。
"""

from __future__ import annotations

import logging
import uuid

from .llm import Backend
from .models import Persona, PersonaBatch

log = logging.getLogger(__name__)

BATCH_SIZE = 10

DIVERSITY_AXES = """\
多様性の軸（バッチ全体、そして既存ペルソナと合わせて偏りなく散らすこと）:
- 年齢: 10 代〜80 代
- 職業: 会社員、経営者、研究者、学生、農業、医療、教育、公務員、職人、アーティスト、
  投資家、エンジニア、主婦・主夫、フリーランス、退職者、など
- 地域: 日本の各地方、および海外（北米・欧州・アジア・中東・アフリカ・南米）
- 関心領域: テクノロジー、科学、政治・国際情勢、経済・金融・投資、スポーツ、
  音楽（邦楽・洋楽・クラシック）、映画・ドラマ・アニメ・ゲーム、ファッション・美容、
  料理・食、健康・医療、教育・子育て、不動産・建築、旅行、地域ニュース、環境・エネルギー、
  歴史・文化・宗教、法律、労働・キャリア、趣味（釣り、車、鉄道、園芸、DIY...）など
- 情報の取り方: 速報好き、深掘り好き、一次情報重視、SNS 中心、専門誌中心、など
- 言語: 主に日本語だが、英語・中国語・韓国語・スペイン語などで情報を読む人物も含める
"""

SYSTEM = """\
あなたは情報収集システムのために「仮想ペルソナ」を設計する専門家です。
目的は、多数の異なる人物の目を通して世界を俯瞰することです。
一人ひとりが「その人ならではの情報源・検索クエリ」を持つように、具体的で生々しい人物像を作ってください。
実在の人物やそれを連想させる名前は使わないでください。
search_queries は、その人物が今日ニュースを追うなら実際に打ち込みそうな、具体的で検索エンジンに向いた短いクエリにしてください（人物名やテーマの固有名詞を含める）。
rss_feeds は、確実に存在する公開フィード URL だけを入れてください。自信がなければ空にしてください。
"""


def generate_personas(
    backend: Backend,
    count: int,
    *,
    seed: str = "",
    language: str = "ja",
    existing: list[Persona] | None = None,
) -> list[Persona]:
    """count 人のペルソナを生成する。existing があれば重複を避けて追加する。"""
    personas: list[Persona] = list(existing or [])
    target = len(personas) + count
    while len(personas) < target:
        n = min(BATCH_SIZE, target - len(personas))
        user = _batch_prompt(n, personas, seed=seed, language=language)
        batch = backend.structured(PersonaBatch, SYSTEM, user)
        for draft in batch.personas[:n]:
            persona = Persona(id=_new_id(), **draft.model_dump())
            personas.append(persona)
            log.info("persona: %s", persona.short())
        if not batch.personas:
            raise RuntimeError("persona generation returned no personas")
    return personas


def _batch_prompt(n: int, existing: list[Persona], *, seed: str, language: str) -> str:
    parts = [f"新しい仮想ペルソナを {n} 人作ってください。", "", DIVERSITY_AXES]
    if seed:
        parts += [
            "",
            f"今回の情報収集の重点テーマ: {seed}",
            "半数程度はこのテーマに関心を持つ人物にし、残りはテーマと無関係な多様な人物にしてください。",
        ]
    parts += ["", f"出力の説明文（bio, interests など）は {language} で書いてください。"]
    if existing:
        parts += ["", "既に存在するペルソナ（これらと年齢・職業・地域・関心が重ならないようにする）:"]
        parts += [f"- {p.short()} 関心: {', '.join(p.interests[:4])}" for p in existing]
    return "\n".join(parts)


def _new_id() -> str:
    return "p_" + uuid.uuid4().hex[:8]
