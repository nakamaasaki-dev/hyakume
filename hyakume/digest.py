"""集約したアイテムから俯瞰ダイジェストを生成する。"""

from __future__ import annotations

import logging

from .aggregate import aggregate, topic_counts
from .llm import Backend
from .models import CollectedItem, Digest, DigestAnalysis, Persona

log = logging.getLogger(__name__)

MAX_ITEMS_FOR_ANALYSIS = 160

SYSTEM = """\
あなたは情報分析官です。多数の仮想ペルソナ（それぞれ異なる関心・分野・地域を持つ人物）が
それぞれの視点で集めてきた情報の一覧を受け取り、世界で今何が起きているかを俯瞰します。

重視すること:
- 「複数の異なる分野のペルソナが同じ事象を見ている」ものは、社会全体で大きな動きである可能性が高い。
- 「1 人だけが見ている」ものは、専門領域の弱いシグナルかもしれない。見落とさない。
- 分野をまたぐ繋がり（例: 技術の動きが金融・政治・生活にどう波及しているか）を言語化する。
- 事実と推測を区別し、推測には「〜の可能性」と明記する。
- クラスタの item_keys には、渡された key をそのまま使う。
"""


def build_digest(
    backend: Backend,
    run_id: str,
    personas: list[Persona],
    collected: list[CollectedItem],
    *,
    language: str = "ja",
) -> Digest:
    items = aggregate(collected)
    persona_by_id = {p.id: p for p in personas}
    analysis = _analyze(backend, items, persona_by_id, language=language)
    return Digest(
        run_id=run_id,
        persona_count=len(personas),
        item_count=len(items),
        analysis=analysis,
        items=items,
        usage=backend.usage.as_dict(),
    )


def _analyze(
    backend: Backend, items, persona_by_id: dict[str, Persona], *, language: str
) -> DigestAnalysis:
    if not items:
        return DigestAnalysis(
            headline="収集結果なし",
            overview="今回の実行では情報が収集できませんでした。",
            clusters=[],
            cross_cutting=[],
            weak_signals=[],
            blind_spots=[],
        )
    lines = []
    for it in items[:MAX_ITEMS_FOR_ANALYSIS]:
        viewers = ", ".join(
            f"{persona_by_id[pid].occupation}" if pid in persona_by_id else pid
            for pid in it.seen_by[:6]
        )
        lines.append(
            f"key: {it.key}\n"
            f"  title: {it.title}\n"
            f"  reach: {it.reach} 人 (avg interest {it.avg_interest:.1f}) viewers: {viewers}\n"
            f"  topics: {', '.join(it.topics)}\n"
            f"  summary: {it.summary}\n"
            + ("  why: " + " / ".join(it.reasons[:3]) + "\n" if it.reasons else "")
        )
    topics = ", ".join(f"{t}({n})" for t, n in topic_counts(items)[:40])
    persona_summary = "\n".join(
        f"- {p.short()}: {', '.join(p.interests[:4])}" for p in persona_by_id.values()
    )
    user = (
        f"ペルソナ一覧（{len(persona_by_id)} 人）:\n{persona_summary}\n\n"
        f"トピック出現数（到達ペルソナ数で重み付け）: {topics}\n\n"
        f"収集アイテム（スコア順、{min(len(items), MAX_ITEMS_FOR_ANALYSIS)} / {len(items)} 件）:\n\n"
        + "\n".join(lines)
        + f"\n\n出力はすべて {language} で書いてください。"
    )
    return backend.structured(DigestAnalysis, SYSTEM, user)
