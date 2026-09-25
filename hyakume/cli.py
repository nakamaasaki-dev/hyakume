"""hyakume コマンドラインインターフェース。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .collect import collect_all
from .config import Settings
from .digest import build_digest
from .llm import make_backend
from .personas import generate_personas
from .report import render_html, render_markdown
from .storage import Store

log = logging.getLogger("hyakume")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hyakume",
        description="百目: 多数の仮想ペルソナに情報を集めさせ、世界を俯瞰する",
    )
    p.add_argument("--version", action="version", version=f"hyakume {__version__}")
    p.add_argument("--data-dir", type=Path, default=None, help="データ保存先 (default: ./data)")
    p.add_argument("--model", default=None, help="ペルソナ生成・ダイジェスト用モデル")
    p.add_argument("--collector-model", default=None, help="ペルソナごとの収集に使うモデル")
    p.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--language", default="ja", help="出力言語 (default: ja)")
    p.add_argument("--mock", action="store_true", help="API を呼ばずに疑似データで実行")
    p.add_argument("-v", "--verbose", action="store_true")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("personas", help="仮想ペルソナを生成する")
    sp.add_argument("-n", "--count", type=int, default=50)
    sp.add_argument("--seed", default="", help="重点テーマ（任意）")
    sp.add_argument("--append", action="store_true", help="既存ペルソナに追加する")
    sp.add_argument("--list", action="store_true", help="既存ペルソナを表示するだけ")

    sc = sub.add_parser("collect", help="各ペルソナに情報収集させる")
    _add_collect_args(sc)

    sd = sub.add_parser("digest", help="収集結果から俯瞰ダイジェストを作る")
    sd.add_argument("--run", default="latest")

    sr = sub.add_parser("run", help="personas(必要なら) → collect → digest を一括実行")
    sr.add_argument("-n", "--count", type=int, default=50, help="ペルソナがまだ無い場合の生成数")
    sr.add_argument("--seed", default="")
    _add_collect_args(sr)

    ss = sub.add_parser("show", help="ダイジェスト (Markdown) を表示する")
    ss.add_argument("--run", default="latest")

    sub.add_parser("runs", help="実行履歴を一覧する")
    return p


def _add_collect_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--limit", type=int, default=0, help="先頭 N 人だけ収集（0=全員）")
    sp.add_argument("--workers", type=int, default=4, help="並列数")
    sp.add_argument("--max-searches", type=int, default=5, help="1 人あたりの web 検索回数上限")
    sp.add_argument("--max-items", type=int, default=12, help="1 人あたりの抽出件数上限")
    sp.add_argument("--no-rss", action="store_true", help="RSS 取得を行わない")


def _settings(args) -> Settings:
    s = Settings()
    if args.data_dir:
        s.data_dir = args.data_dir
    if args.model:
        s.model = args.model
        if not args.collector_model:
            s.collector_model = args.model
    if args.collector_model:
        s.collector_model = args.collector_model
    if args.effort:
        s.effort = args.effort
    s.language = args.language
    s.mock = args.mock
    s.verbose = args.verbose
    for name in ("workers", "max_searches"):
        if hasattr(args, name):
            setattr(s, name, getattr(args, name))
    if hasattr(args, "max_items"):
        s.max_items_per_persona = args.max_items
    if hasattr(args, "no_rss"):
        s.use_rss = not args.no_rss
    return s


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    settings = _settings(args)
    store = Store(settings.data_dir)

    try:
        if args.command == "personas":
            return cmd_personas(args, settings, store)
        if args.command == "collect":
            return cmd_collect(args, settings, store)
        if args.command == "digest":
            return cmd_digest(args, settings, store)
        if args.command == "run":
            return cmd_run(args, settings, store)
        if args.command == "show":
            return cmd_show(args, store)
        if args.command == "runs":
            for r in store.list_runs():
                print(r)
            return 0
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


# ---------------------------------------------------------------------------


def cmd_personas(args, settings: Settings, store: Store) -> int:
    existing = store.load_personas()
    if args.list:
        for p in existing:
            print(f"{p.id}  {p.short()}  関心: {', '.join(p.interests)}")
        print(f"{len(existing)} personas", file=sys.stderr)
        return 0
    backend = make_backend(settings)
    base = existing if args.append else []
    if existing and not args.append:
        log.info("既存の %d 人を破棄して生成し直します（--append で追加）", len(existing))
    personas = generate_personas(
        backend, args.count, seed=args.seed, language=settings.language, existing=base
    )
    path = store.save_personas(personas)
    print(f"{len(personas)} personas -> {path}")
    _print_usage(backend)
    return 0


def cmd_collect(args, settings: Settings, store: Store) -> int:
    personas = store.load_personas()
    if not personas:
        raise FileNotFoundError("no personas; run `hyakume personas` first")
    if args.limit:
        personas = personas[: args.limit]
    backend = make_backend(settings)
    run_id = store.new_run_id()
    _do_collect(backend, personas, settings, store, run_id)
    _print_usage(backend)
    return 0


def _do_collect(backend, personas, settings, store, run_id) -> list:
    total = len(personas)
    done = [0]

    def progress(persona, items, exc):
        done[0] += 1
        status = f"{len(items)} 件" if items is not None else f"失敗: {exc}"
        print(f"[{done[0]}/{total}] {persona.short()} — {status}", file=sys.stderr)

    print(f"run {run_id}: {total} 人で収集開始", file=sys.stderr)
    items = collect_all(backend, personas, settings, on_progress=progress)
    path = store.save_items(run_id, items)
    print(f"{len(items)} items -> {path}")
    return items


def cmd_digest(args, settings: Settings, store: Store) -> int:
    run_id = store.resolve_run(args.run)
    personas = store.load_personas()
    items = store.load_items(run_id)
    backend = make_backend(settings)
    _do_digest(backend, run_id, personas, items, settings, store)
    _print_usage(backend)
    return 0


def _do_digest(backend, run_id, personas, items, settings, store) -> None:
    digest = build_digest(backend, run_id, personas, items, language=settings.language)
    md = render_markdown(digest, personas)
    html = render_html(digest, personas)
    paths = store.save_digest(digest, md, html)
    print(f"digest: {paths['md']}\nhtml:   {paths['html']}")
    print()
    print(f"# {digest.analysis.headline}")
    print()
    print(digest.analysis.overview)


def cmd_run(args, settings: Settings, store: Store) -> int:
    backend = make_backend(settings)
    personas = store.load_personas()
    if not personas:
        personas = generate_personas(
            backend, args.count, seed=args.seed, language=settings.language
        )
        store.save_personas(personas)
        print(f"{len(personas)} personas generated", file=sys.stderr)
    if args.limit:
        personas = personas[: args.limit]
    run_id = store.new_run_id()
    items = _do_collect(backend, personas, settings, store, run_id)
    _do_digest(backend, run_id, personas, items, settings, store)
    _print_usage(backend)
    return 0


def cmd_show(args, store: Store) -> int:
    run_id = store.resolve_run(args.run)
    path = store.run_dir(run_id) / "digest.md"
    if not path.exists():
        raise FileNotFoundError(f"no digest for run {run_id}; run `hyakume digest --run {run_id}`")
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def _print_usage(backend) -> None:
    u = backend.usage.as_dict()
    if u["requests"]:
        print(
            f"usage: {u['requests']} req, in {u['input_tokens']:,}, out {u['output_tokens']:,}, "
            f"cache read {u['cache_read_input_tokens']:,}",
            file=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
