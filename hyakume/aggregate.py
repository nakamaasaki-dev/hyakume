"""複数ペルソナの収集結果を 1 つの俯瞰ビューに統合する。"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import AggregatedItem, CollectedItem

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "source", "s", "cmpid", "ncid",
}


def normalize_url(url: str) -> str:
    """トラッキングパラメータやスキーム・末尾スラッシュの違いを吸収した URL キー。"""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parts.path) or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
             if k.lower() not in _TRACKING_PARAMS]
    query.sort()
    return urlunsplit(("https", host, path, urlencode(query), ""))


def aggregate(items: list[CollectedItem]) -> list[AggregatedItem]:
    """URL 単位でまとめ、どのペルソナが見たかを記録する。スコア降順で返す。"""
    merged: dict[str, AggregatedItem] = {}
    for it in items:
        key = normalize_url(it.url)
        agg = merged.get(key)
        if agg is None:
            agg = AggregatedItem(
                key=key,
                title=it.title,
                url=it.url,
                summary=it.summary,
                topics=list(it.topics),
                published=it.published,
                source=it.source,
            )
            merged[key] = agg
        else:
            if len(it.summary) > len(agg.summary):
                agg.summary = it.summary
            if not agg.published and it.published:
                agg.published = it.published
            for t in it.topics:
                if t not in agg.topics:
                    agg.topics.append(t)
        if it.persona_id not in agg.seen_by:
            agg.seen_by.append(it.persona_id)
            agg.interests.append(it.interest)
            if it.why_it_matters:
                agg.reasons.append(it.why_it_matters)
    return sorted(merged.values(), key=lambda a: (-a.score, a.title))


def topic_counts(items: list[AggregatedItem]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for it in items:
        for t in it.topics:
            counts[t] = counts.get(t, 0) + it.reach
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
