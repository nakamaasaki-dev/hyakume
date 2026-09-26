# 百目 (Hyakume)

> 私は全ての情報を得て全知になりたい。
> AI で仮想の人格を 50 種類くらい作り、その人格の人が好むであろう情報を AI で収集してくる。
> 仮想のペルソナを多数所有することによって、俯瞰で全てを観測できるのではないか。

**Hyakume** はその構想をそのまま形にした情報集約ツールです。

1. **ペルソナ生成** — Claude が年齢・職業・地域・関心・言語の異なる仮想人物を多数（既定 50 人）設計する
2. **収集** — 各ペルソナになりきった Claude が web 検索（＋任意で RSS）で「その人が今日読みたい情報」を集める
3. **俯瞰** — 全ペルソナの収集結果を URL 単位で統合し、「何人のペルソナがその情報に到達したか」を軸に、
   横断的な動き・トピッククラスタ・弱いシグナル・死角をまとめたダイジェスト（Markdown / HTML）を生成する

スポーツ好きにはスポーツの情報が、洋楽好きには洋楽の情報が集まり、それらを重ね合わせることで
「複数の異なる分野の人が同時に見ている事象」= 社会全体の大きな動きが浮かび上がります。

## セットアップ

```bash
git clone https://github.com/nakamaasaki-dev/hyakume.git
cd hyakume
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...   # または `ant auth login`
```

Python 3.10 以上が必要です。

## 使い方

まずは API を呼ばずに全体の流れを確認できます。

```bash
hyakume --mock run -n 10
hyakume show                 # 最新ダイジェスト (Markdown) を表示
open data/runs/<run_id>/digest.html
```

本番実行:

```bash
# 1. 仮想ペルソナを 50 人生成 → data/personas.json
hyakume personas -n 50
hyakume personas -n 50 --seed "生成AIと日本社会"   # 半数を重点テーマ寄りにする
hyakume personas --list

# 2. 各ペルソナに収集させる → data/runs/<run_id>/items.json
hyakume collect --workers 6 --max-searches 5

# 3. 俯瞰ダイジェストを生成 → data/runs/<run_id>/digest.{md,html,json}
hyakume digest
hyakume show

# 1〜3 をまとめて（ペルソナが無ければ生成する）
hyakume run -n 50
```

### 主なオプション

| オプション | 説明 |
|---|---|
| `--limit N` | 先頭 N 人だけ収集する（コストを抑えた試運転に） |
| `--max-searches N` | 1 人あたりの web 検索回数上限（既定 5） |
| `--max-items N` | 1 人あたりの抽出件数上限（既定 12） |
| `--workers N` | 収集の並列数（既定 4） |
| `--no-rss` | ペルソナの購読 RSS を取りに行かない |
| `--model` / `--collector-model` | 使用モデル。収集だけ `claude-sonnet-5` にするとコストを抑えられる |
| `--effort` | `low` / `medium` / `high`(既定) / `xhigh` / `max` |
| `--language` | 出力言語（既定 `ja`） |
| `--data-dir` | データ保存先（既定 `./data`） |
| `--mock` | API を呼ばずに疑似データで動かす |

環境変数 `HYAKUME_MODEL` / `HYAKUME_COLLECTOR_MODEL` / `HYAKUME_EFFORT` / `HYAKUME_DATA_DIR` でも既定値を変えられます（`.env.example` 参照）。

## スマホや PC のブラウザで見る（GitHub Pages で自動公開）

`.github/workflows/digest.yml` が毎朝 7 時（日本時間）に百目を実行し、最新のダイジェストを
`https://<ユーザー名>.github.io/hyakume/` に公開します。手元で何も動かさなくても、
URL を開くだけでスマホから読めます。

初回だけ、GitHub のリポジトリページで次の設定をしてください。

1. **Settings → Pages** の「Build and deployment」で Source を **GitHub Actions** にする
2. **Settings → Secrets and variables → Actions → New repository secret** で
   Name に `ANTHROPIC_API_KEY`、Secret に Anthropic の API キーを入れて保存する
   （未設定の間はダミーデータで動くので、先に画面だけ確認できます）
3. **Actions** タブ → 左の「digest」→ **Run workflow** で 1 回手動実行する

無料プランでは GitHub Pages は公開リポジトリでのみ使えます。非公開のままにしたい場合は
Settings → General の一番下「Change repository visibility」で公開に切り替えるか、
有料プランをご検討ください。

## 出力

`data/runs/<run_id>/digest.md` の構成:

- **俯瞰** — 全体像の要約
- **横断的な動き** — 複数の異なる分野のペルソナが同時に観測した事象
- **トピッククラスタ** — 事象のまとまりごとの要約と、到達ペルソナ数付きの記事一覧
- **弱いシグナル** — 1〜2 人しか見ていないが今後大きくなりうる動き
- **死角** — 現在のペルソナ構成では拾えていない領域（次の `personas --append` の材料に）
- **注目度ランキング** — 到達ペルソナ数 × 関心度でのランキング
- **ペルソナ別ハイライト** — 各人が何を、なぜ読んだか

`digest.html` はペルソナ別の絞り込みと検索ができる単一ファイルのビューアです。

## 仕組み

```
personas.py   Claude (structured output) で 10 人ずつ、既存と重ならないように生成
collect.py    ペルソナごとに Claude + web_search サーバーツールで検索 → JSON 抽出
              （RSS がある場合は取得して、ペルソナ視点で取捨選択・要約）
aggregate.py  URL を正規化して統合、到達ペルソナ数・平均関心度でスコアリング
digest.py     統合結果を Claude に渡し、クラスタ・横断シグナル・弱いシグナル・死角を抽出
report.py     Markdown / HTML に整形
```

- モデルは既定で `claude-opus-5`、adaptive thinking + `effort` で制御しています。
- web 検索を伴う呼び出しでは、安全分類器による拒否時にサーバー側で別モデルへ再実行する
  `fallbacks: "default"` を有効にしています。不要なら `hyakume/llm.py` の該当行を外してください。
- 抽出された URL は検索結果に実際に含まれていたものだけを採用し、捏造 URL を落とします。
- ペルソナ 1 人の失敗は記録して続行します（他のペルソナの収集は止まりません）。

## コストの目安

収集は「ペルソナ数 × 検索回数」でトークンを消費します。まずは
`hyakume run -n 50 --limit 5 --max-searches 3` のように小さく回し、
`usage:` 行（リクエスト数・入出力トークン）を見てから全員に広げるのがおすすめです。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

テストはモックバックエンドで動くため API キーは不要です。

## ライセンス

MIT
