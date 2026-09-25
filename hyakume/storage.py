"""data/ 配下のファイル入出力。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import CollectedItem, Digest, Persona


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.runs_dir = self.root / "runs"

    # ------------------------------------------------------------ personas
    @property
    def personas_path(self) -> Path:
        return self.root / "personas.json"

    def load_personas(self) -> list[Persona]:
        if not self.personas_path.exists():
            return []
        data = json.loads(self.personas_path.read_text(encoding="utf-8"))
        return [Persona(**p) for p in data]

    def save_personas(self, personas: list[Persona]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        self.personas_path.write_text(
            json.dumps([p.model_dump() for p in personas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.personas_path

    # ---------------------------------------------------------------- runs
    def new_run_id(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def list_runs(self) -> list[str]:
        if not self.runs_dir.exists():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if p.is_dir())

    def resolve_run(self, run_id: str | None) -> str:
        if run_id and run_id != "latest":
            return run_id
        runs = self.list_runs()
        if not runs:
            raise FileNotFoundError("no runs found; run `hyakume collect` first")
        return runs[-1]

    def save_items(self, run_id: str, items: list[CollectedItem]) -> Path:
        d = self.run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "items.json"
        path.write_text(
            json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_items(self, run_id: str) -> list[CollectedItem]:
        path = self.run_dir(run_id) / "items.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return [CollectedItem(**i) for i in data]

    def save_digest(self, digest: Digest, markdown: str, html: str) -> dict[str, Path]:
        d = self.run_dir(digest.run_id)
        d.mkdir(parents=True, exist_ok=True)
        paths = {
            "json": d / "digest.json",
            "md": d / "digest.md",
            "html": d / "digest.html",
        }
        paths["json"].write_text(digest.model_dump_json(indent=2), encoding="utf-8")
        paths["md"].write_text(markdown, encoding="utf-8")
        paths["html"].write_text(html, encoding="utf-8")
        return paths

    def load_digest(self, run_id: str) -> Digest:
        path = self.run_dir(run_id) / "digest.json"
        return Digest.model_validate_json(path.read_text(encoding="utf-8"))
