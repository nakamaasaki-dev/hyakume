"""モックバックエンドでパイプライン全体を通す。"""

from hyakume.cli import main
from hyakume.storage import Store


def test_end_to_end_with_mock(tmp_path, capsys):
    data = tmp_path / "data"
    assert main(["--mock", "--data-dir", str(data), "personas", "-n", "12"]) == 0
    store = Store(data)
    personas = store.load_personas()
    assert len(personas) == 12
    assert len({p.id for p in personas}) == 12

    assert main(["--mock", "--data-dir", str(data), "collect", "--workers", "3"]) == 0
    run_id = store.resolve_run("latest")
    items = store.load_items(run_id)
    assert items
    assert {i.persona_id for i in items} == {p.id for p in personas}

    assert main(["--mock", "--data-dir", str(data), "digest"]) == 0
    digest = store.load_digest(run_id)
    assert digest.persona_count == 12
    # 共通トピックは複数ペルソナに到達しているはず
    assert digest.items[0].reach > 1
    md = (store.run_dir(run_id) / "digest.md").read_text(encoding="utf-8")
    assert "俯瞰" in md and "注目度ランキング" in md
    html = (store.run_dir(run_id) / "digest.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html

    assert main(["--data-dir", str(data), "show"]) == 0
    assert "百目ダイジェスト" in capsys.readouterr().out


def test_run_command_generates_personas_when_missing(tmp_path):
    data = tmp_path / "data"
    assert main(["--mock", "--data-dir", str(data), "run", "-n", "5", "--limit", "3"]) == 0
    store = Store(data)
    assert len(store.load_personas()) == 5
    digest = store.load_digest(store.resolve_run("latest"))
    assert digest.persona_count == 3
