# 依存の種類別レシピ + 現在のインベントリ

このファイルは [SKILL.md](../SKILL.md) のステップ2・3から参照される補助資料です。`apm.yml` に固定された依存を「どう最新化するか」「バージョン間の差分をどこから取るか」を種類別にまとめています。

## 目次

- [種類別レシピ一覧](#種類別レシピ一覧)
- [差分説明の取得手順（種類別）](#差分説明の取得手順種類別)
- [現在の apm.yml インベントリ（スナップショット）](#現在の-apmyml-インベントリスナップショット)
- [注意点](#注意点)

## 種類別レシピ一覧

| 種別 | apm.yml 上の形 | 最新の取得 | 書き換える部分 |
|------|----------------|------------|----------------|
| `plugin` | `plugin:` 直下の `"<pkg>@<semver>"` | `npm view <pkg> version` | `@` 以降の版数のみ |
| `mcp-npm` | MCP の `args:` 内 `"<pkg>@<semver>"` | `npm view <pkg> version` | `@` 以降の版数のみ |
| `mcp-git` | `"git+https://....git@<sha>[extras]"` | `git ls-remote <url> HEAD` の先頭SHA | `@` と `[` の間の 40桁ハッシュのみ（`[all]` 等は保持） |
| `apm-skill` | `dependencies.apm:` の `owner/repo[//sub]#<tag>` | `git ls-remote --tags --refs <url>` の最新 semver タグ | `#` 以降のタグのみ |
| `latest` | `"<pkg>@latest"` | 参考: `npm view <pkg> version` | 既定では**書き換えない**（追従を維持） |

スコープ付き npm 名（`@yohi/justice`）は先頭の `@` がパッケージ名の一部です。版数は「最後の `@` の後ろ」です。取り違え防止のため手パースせず [check_updates.py](../scripts/check_updates.py) の `--json` 出力（`name` / `current` / `line`）を使ってください。

## 差分説明の取得手順（種類別）

目的は版数の羅列ではなく「上げてよいか判断できる要約」を出すことです。破壊的変更（major 上昇 / BREAKING CHANGE）は必ず目立たせます。

### npm パッケージ（`plugin` / `mcp-npm`）

1. リポジトリ特定: `npm view <pkg> repository.url`（例 `git+https://github.com/owner/repo.git`）。
2. リリースノート: `gh release view <newtag> --repo <owner/repo>`。タグ名は `v<semver>` か `<semver>` のどちらか。両方試す。
3. まとめて比較: `https://github.com/<owner/repo>/compare/<oldtag>...<newtag>`（webfetch でも可）。
4. リポジトリ非公開・特定不能なら: `npm view <pkg>` の `homepage` を参照し、「変更点取得不可」と正直に書いてリンクだけ提示。

### apm-skill（GitHub タグ）

1. `gh release view <newtag> --repo <owner/repo>` でリリースノート。
2. 無ければ compare: `https://github.com/<owner/repo>/compare/<oldtag>...<newtag>`。

### mcp-git（コミットハッシュ）

1. GitHub API 比較: `gh api repos/<owner/repo>/compare/<oldsha>...<newsha> --jq '.commits[].commit.message'` でコミットメッセージ一覧。
2. あるいは compare ビュー: `https://github.com/<owner/repo>/compare/<oldsha>...<newsha>`。
3. ローカルで見たい場合のみ: 一時 clone + `git log --oneline <old>..<new>`（このスキルでは基本 `gh`/webfetch を優先）。

## 現在の apm.yml インベントリ（スナップショット）

作成時点で `apm.yml` に固定されていた版数付き依存です。**実際の状態は [check_updates.py](../scripts/check_updates.py) の出力が真実源**であり、以下は理解のための参考（ドリフトしうる）です。

| 種別 | 依存 | 現在値（作成時点） |
|------|------|--------------------|
| `apm-skill` | `obra/superpowers` | `#v6.0.2` |
| `mcp-npm` | `@yohi/nexus` | `1.22.0` |
| `mcp-git` | `yohi/chronos-graph` | `cb1f33f...222c`（40桁 commit hash） |
| `plugin` | `@yohi/justice` | `2.3.0` |
| `plugin` | `@yohi/akane` | `1.5.1` |
| `plugin` | `oh-my-openagent` | `4.15.1` |
| `plugin` | `@yohi/chronos-gate` | `1.1.0` |
| `plugin` (latest) | `@nick-vi/opencode-type-inject` | `latest`（追従・据え置き） |
| `plugin` (latest) | `opencode-vibeguard` | `latest`（追従・据え置き） |

### 未固定（default branch 追従・既定では対象外）

以下は版数指定が無く常に最新を引くため、このスキルの既定の更新対象ではありません（ユーザーが固定を望んだ場合のみ、その時点の解決版を調べてピン留めを提案）:

- `dependencies.apm`: `anthropics/skills`, `coderabbitai/skills`, `greptileai/skills//check-pr`, `greptileai/skills//greploop`, `anthropics/claude-code//plugins/code-review`, `yohi/agent-skills//skills/*`
- トップレベル `skills:`: `coderabbitai/skills`, `greptileai/skills//check-pr`, `greptileai/skills//greploop`
- 版数なしの MCP コマンド: `coderabbitai-mcp`, `sonarqube-mcp-server`, `skillport-mcp`, `semgrep-mcp`

## 注意点

- `apm.yml` は SSOT。書き換えは対象行のみの最小差分にし、YAML 全体を再整形しない。
- 版数だけ / ハッシュだけを差し替え、引用符・インデント・`[all]` などの extras・`//subpath` は保持する。
- 適用後の再解決には `make apm-install`（`apm.lock.yaml` を更新）が必要。MCP 版数変更時は `make sync-mcp`、スキル/プラグイン変更時は `make sync-agents` を案内する（このスキルでは自動実行しない）。
