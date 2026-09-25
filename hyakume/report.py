"""ダイジェストの Markdown / HTML 出力。"""

from __future__ import annotations

import html
import json

from .models import Digest, Persona


def render_markdown(digest: Digest, personas: list[Persona]) -> str:
    a = digest.analysis
    by_id = {p.id: p for p in personas}
    by_key = {it.key: it for it in digest.items}

    def who(ids: list[str]) -> str:
        return "、".join(by_id[i].occupation if i in by_id else i for i in ids)

    out: list[str] = []
    out.append(f"# 百目ダイジェスト — {a.headline}")
    out.append("")
    out.append(
        f"run `{digest.run_id}` / {digest.created_at} / "
        f"ペルソナ {digest.persona_count} 人 / 収集 {digest.item_count} 件"
    )
    out.append("")
    out.append("## 俯瞰")
    out.append("")
    out.append(a.overview)
    out.append("")
    if a.cross_cutting:
        out.append("## 横断的な動き（複数分野で同時に観測）")
        out.append("")
        out += [f"- {s}" for s in a.cross_cutting]
        out.append("")
    if a.clusters:
        out.append("## トピッククラスタ")
        out.append("")
        for c in a.clusters:
            out.append(f"### {c.name}")
            out.append("")
            out.append(c.summary)
            out.append("")
            out.append(f"_{c.significance}_")
            out.append("")
            for key in c.item_keys:
                it = by_key.get(key)
                if it is None:
                    continue
                out.append(
                    f"- [{it.title}]({it.url}) — {it.reach} 人が注目（{who(it.seen_by)}）"
                )
                out.append(f"  {it.summary}")
            out.append("")
    if a.weak_signals:
        out.append("## 弱いシグナル（少数のペルソナだけが捉えた動き）")
        out.append("")
        out += [f"- {s}" for s in a.weak_signals]
        out.append("")
    if a.blind_spots:
        out.append("## 死角（現在のペルソナ構成で拾えていない可能性のある領域）")
        out.append("")
        out += [f"- {s}" for s in a.blind_spots]
        out.append("")

    out.append("## 注目度ランキング（到達ペルソナ数順）")
    out.append("")
    for it in digest.items[:30]:
        out.append(
            f"1. [{it.title}]({it.url}) — {it.reach} 人 / 関心 {it.avg_interest:.1f}"
            + (f" / {it.published}" if it.published else "")
        )
    out.append("")

    out.append("## ペルソナ別ハイライト")
    out.append("")
    for p in personas:
        mine = [it for it in digest.items if p.id in it.seen_by]
        if not mine:
            continue
        out.append(f"### {p.short()}")
        out.append("")
        for it in mine[:5]:
            idx = it.seen_by.index(p.id)
            reason = it.reasons[idx] if idx < len(it.reasons) else ""
            out.append(f"- [{it.title}]({it.url})" + (f" — {reason}" if reason else ""))
        out.append("")

    if digest.usage:
        u = digest.usage
        out.append("---")
        out.append(
            f"API 使用量: {u.get('requests', 0)} リクエスト / 入力 {u.get('input_tokens', 0):,} "
            f"/ 出力 {u.get('output_tokens', 0):,} / キャッシュ読取 {u.get('cache_read_input_tokens', 0):,} トークン"
        )
    return "\n".join(out) + "\n"


_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>百目 — __HEADLINE__</title>
<style>
:root{--bg:#0f1115;--fg:#e6e6e6;--muted:#9aa0a6;--card:#171a21;--accent:#7cc4ff;--line:#262a33}
@media (prefers-color-scheme: light){:root{--bg:#fafafa;--fg:#111;--muted:#666;--card:#fff;--accent:#0b62c4;--line:#e3e3e3}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.15rem;border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:32px}
.meta{color:var(--muted);font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.item{padding:8px 0;border-bottom:1px solid var(--line)}.item:last-child{border-bottom:0}
.item a{color:var(--accent);text-decoration:none}.item a:hover{text-decoration:underline}
.badge{display:inline-block;background:var(--accent);color:var(--bg);border-radius:999px;font-size:.75rem;padding:0 8px;margin-right:6px}
.tag{display:inline-block;border:1px solid var(--line);border-radius:6px;font-size:.75rem;padding:0 6px;margin:0 3px 0 0;color:var(--muted)}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
select,input{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:.9rem}
ul{padding-left:20px}
</style>
</head>
<body>
<main>
<h1>__HEADLINE__</h1>
<div class="meta">run __RUN__ / __CREATED__ / ペルソナ __PCOUNT__ 人 / 収集 __ICOUNT__ 件</div>
<h2>俯瞰</h2><div class="card">__OVERVIEW__</div>
<h2>横断的な動き</h2><div class="card"><ul>__CROSS__</ul></div>
<h2>トピッククラスタ</h2><div id="clusters"></div>
<h2>弱いシグナル</h2><div class="card"><ul>__WEAK__</ul></div>
<h2>死角</h2><div class="card"><ul>__BLIND__</ul></div>
<h2>すべてのアイテム</h2>
<div class="controls">
  <select id="persona"><option value="">すべてのペルソナ</option></select>
  <input id="q" placeholder="タイトル・トピックで絞り込み">
</div>
<div id="items" class="card"></div>
</main>
<script>
const DATA = __DATA__;
const byId = Object.fromEntries(DATA.personas.map(p=>[p.id,p]));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const who = ids => ids.map(i => byId[i] ? byId[i].occupation : i).join("、");
function itemHtml(it){
  return `<div class="item"><span class="badge">${it.seen_by.length}人</span><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>
  <div class="meta">${esc(who(it.seen_by))}${it.published?" / "+esc(it.published):""}</div>
  <div>${esc(it.summary)}</div><div>${it.topics.map(t=>`<span class="tag">${esc(t)}</span>`).join("")}</div></div>`;
}
const byKey = Object.fromEntries(DATA.items.map(i=>[i.key,i]));
document.getElementById("clusters").innerHTML = DATA.analysis.clusters.map(c =>
  `<div class="card"><h3>${esc(c.name)}</h3><p>${esc(c.summary)}</p><p class="meta">${esc(c.significance)}</p>${c.item_keys.map(k=>byKey[k]).filter(Boolean).map(itemHtml).join("")}</div>`).join("");
const sel = document.getElementById("persona");
for (const p of DATA.personas){ const o=document.createElement("option"); o.value=p.id; o.textContent=`${p.name}（${p.occupation}）`; sel.appendChild(o); }
function render(){
  const pid = sel.value, q = document.getElementById("q").value.trim().toLowerCase();
  const rows = DATA.items.filter(it => (!pid || it.seen_by.includes(pid)) &&
    (!q || (it.title+" "+it.topics.join(" ")+" "+it.summary).toLowerCase().includes(q)));
  document.getElementById("items").innerHTML = rows.map(itemHtml).join("") || "<div class='meta'>該当なし</div>";
}
sel.addEventListener("change", render); document.getElementById("q").addEventListener("input", render); render();
</script>
</body>
</html>
"""


def render_html(digest: Digest, personas: list[Persona]) -> str:
    a = digest.analysis
    data = {
        "personas": [p.model_dump() for p in personas],
        "items": [it.model_dump() for it in digest.items],
        "analysis": a.model_dump(),
    }
    li = lambda xs: "".join(f"<li>{html.escape(x)}</li>" for x in xs)  # noqa: E731
    page = _HTML
    for k, v in {
        "__HEADLINE__": html.escape(a.headline),
        "__RUN__": html.escape(digest.run_id),
        "__CREATED__": html.escape(digest.created_at),
        "__PCOUNT__": str(digest.persona_count),
        "__ICOUNT__": str(digest.item_count),
        "__OVERVIEW__": html.escape(a.overview).replace("\n", "<br>"),
        "__CROSS__": li(a.cross_cutting),
        "__WEAK__": li(a.weak_signals),
        "__BLIND__": li(a.blind_spots),
        "__DATA__": json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(k, v)
    return page
