# skill-blueprint

`skills/` フォルダ内のスキル群を、**1枚の設計図(HTML)** にする Claude Code プラグインです。

- 最初に読むスキル(START)
- 各スキルの見出し(SKILL.md の見出しそのまま)
- 条件によって別のスキルへ進む流れを、条件ラベルつきの矢印で結ぶ

## できること

- **設計図の生成**: `/skill-blueprint <対象> [言語] [全体|個別]`
  - 対象: `skills/` 内のフォルダ名、パス、`@project`(`.claude/skills`)、`@user`(`~/.claude/skills`)
  - 範囲: **全体**(省略時)は対象の全スキルを1枚に。**個別**はスキル1つにつき1枚(SKILL.md と references の関係)
  - 言語: 省略すると原文のまま、指定すると見出しや説明をその言語に訳します(`/skill-blueprint @project 日本語 個別`)。
- **操作**: マウスホイールで拡大縮小、カードや矢印のラベルをドラッグして移動、項目をクリックすると SKILL.md の該当行を右パネルで表示します。
- **PDF 書き出し**: 設計図の右上の「PDF」ボタンから、印刷ダイアログで「PDFに保存」を選ぶと、図全体が1ページのPDFになります。コマンドなら `python -I "<プラグインのパス>/skills/skill-blueprint/scripts/export_pdf.py" blueprints/<フォルダ名>`(ヘッドレスの Edge / Chrome を使用。出力は `blueprints/<フォルダ名>/blueprint.pdf`)。
- **実行ログの重ね表示(リアルタイム)**: AI がスキルを使うと、今のスキルが脈打ち、通った矢印が太くなります。
- **事後の項目推定と統計**: 終了後に会話ログから通った見出しを推定して色づけします。「統計」ビューで、スキル・矢印・項目ごとの通過回数を見られます。

## インストール

```
/plugin marketplace add nabepy/skill-blueprint
/plugin install skill-blueprint@skill-blueprint
```

必要なもの: **Python 3.8 以上**(`python` コマンド。標準ライブラリのみで、追加インストールは不要)。

## 使い方

```
/skill-blueprint @project
```

結果はプロジェクト直下の `blueprints/<フォルダ名>/` に出力されます。

```
blueprints/<フォルダ名>/
  spec.json          設計(手直し用)
  index.html         設計図
  logs/events.jsonl  実行ログ(スキル名・時刻・セッションIDのみ。会話の本文は保存しません)
  stats.json         解析結果
```

設計図を作ると、ローカルサーバー(`127.0.0.1` のみ)が自動で裏に立ち上がり、表示された URL(`http://localhost:<ポート>/index.html`)で開きます。
ポートは設計図フォルダごとに決まります(別プロジェクトの設計図と取り違えません)。実行ログは1秒ごとに読み直されます。
手動で操作する場合:

```
python -I "<プラグインのパス>/skills/skill-blueprint/scripts/serve.py" blueprints/<フォルダ名> --detach   # 起動(動いていれば再利用)
python -I "<プラグインのパス>/skills/skill-blueprint/scripts/serve.py" blueprints/<フォルダ名> --stop     # 停止
python -I "<プラグインのパス>/skills/skill-blueprint/scripts/serve.py" blueprints/<フォルダ名> --status   # 状態

## 実行ログについて

プラグインを有効にすると、同梱の hooks が動きます。`blueprints/*/spec.json` に載っているスキルの利用だけを
`logs/events.jsonl` に追記し、それ以外のセッションでは何も書きません。

- スキル名・時刻・セッションID・読み込んだ行範囲だけを保存します。プロンプトや回答の本文は保存しません。
- 項目(見出し)の通過は、会話ログ(Claude Code が保存するファイル)を読んでの**推定**です。スキルと矢印の回数は記録に基づく正確な値です。
- 記録をやめるには、プラグインを無効にしてください。
- リポジトリに設計図を入れる場合は、`blueprints/*/logs/` を `.gitignore` に入れることをおすすめします。

## ライセンス

MIT
