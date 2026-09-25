"""RSS/Atom フィードの取得。ネットワーク失敗は空リストとして扱う。"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

USER_AGENT = "hyakume/0.1 (+https://github.com/nakamaasaki-dev/hyakume)"


@dataclass
class FeedEntry:
    title: str
    url: str
    summary: str
    published: str
    feed_url: str


def fetch_feed(url: str, limit: int = 10, timeout: float = 15.0) -> list[FeedEntry]:
    try:
        import feedparser
    except ImportError:  # pragma: no cover
        log.warning("feedparser is not installed; skipping RSS")
        return []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001 - ネットワーク失敗は握りつぶして続行
        log.info("rss fetch failed %s: %s", url, exc)
        return []
    parsed = feedparser.parse(raw)
    entries: list[FeedEntry] = []
    for e in parsed.entries[:limit]:
        link = getattr(e, "link", "") or ""
        if not link:
            continue
        published = ""
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(e, attr, None)
            if t:
                published = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
                break
        entries.append(
            FeedEntry(
                title=(getattr(e, "title", "") or "").strip(),
                url=link,
                summary=_strip_html(getattr(e, "summary", "") or "")[:600],
                published=published,
                feed_url=url,
            )
        )
    return entries


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", text).replace("\xa0", " ").strip()
