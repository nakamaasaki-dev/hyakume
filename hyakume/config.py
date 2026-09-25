"""実行時設定。環境変数と CLI フラグから組み立てる。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5"


@dataclass
class Settings:
    """1 回の実行で使う設定。"""

    model: str = field(default_factory=lambda: os.environ.get("HYAKUME_MODEL", DEFAULT_MODEL))
    collector_model: str = field(
        default_factory=lambda: os.environ.get(
            "HYAKUME_COLLECTOR_MODEL", os.environ.get("HYAKUME_MODEL", DEFAULT_MODEL)
        )
    )
    effort: str = field(default_factory=lambda: os.environ.get("HYAKUME_EFFORT", "high"))
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("HYAKUME_DATA_DIR", "./data"))
    )
    language: str = "ja"
    mock: bool = False
    workers: int = 4
    max_searches: int = 5
    max_items_per_persona: int = 12
    rss_entries_per_feed: int = 10
    use_rss: bool = True
    verbose: bool = False
