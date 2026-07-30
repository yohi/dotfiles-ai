# 依存の種類別レシピ + モデルスキーマ更新手順

このファイルは [SKILL.md](../SKILL.md) のワークフローから参照される補助資料です。

1. `apm.yml` に固定された依存を「どう最新化するか」「バージョン間の差分をどこから取るか」を種類別にまとめています。
2. `models.dev/model-schema.json` を使った OpenCode LLM モデル更新手順をまとめています。

## 目次

- [種類別レシピ一覧](#種類別レシピ一覧)
- [差分説明の取得手順（種類別）](#差分説明の取得手順種類別)
- [現在の apm.yml インベントリ（スナップショット）](#現在の-apmyml-インベントリスナップショット)
- [LLM モデルスキーマ更新手順](#llm-モデルスキーマ更新手順)
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

## LLM モデルスキーマ更新手順

### 1. 最新モデル一覧の取得

```bash
python .claude/skills/apm-updater/scripts/check_updates.py --models
```

`https://models.dev/model-schema.json` から `[$defs][Model][enum]` を抽出し、プロバイダーごとにグループ化して表示します。ネットワーク不通時は `unresolved` として報告します。

### 2. apm.yml provider セクションの検証

```bash
python .claude/skills/apm-updater/scripts/check_updates.py --validate-models
```

`apm.yml` 内の YAML リスト形式のモデル識別子を読み取り、以下を検証します:

- 各モデルが `models.dev/model-schema.json` の `enum` に含まれているか
- `amazon-bedrock` セクションのモデルが `global.anthropic.claude-*` または `openai.gpt-*` で始まっているか

検証結果は行番号付きで出力されます。問題がなければ「all whitelist entries match models.dev schema」と表示されます。

### 3. apm.yml の更新ルール

- `provider` セクション配下の各プロバイダーの `whitelist` または `models` リストを、最新スキーマで定義されている有効なモデル名と一致させます。
- **Bedrock 制限**: `amazon-bedrock` の whitelist は `global.anthropic.claude-*` と `openai.gpt-*` のみにします。リージョン固有モデルや古い世代は含めません。
- `opencode.jsonc` を直接編集してはいけません。`opencode/omo.jsonc` はプロファイル別モデル設定の SSOT です。`apm.yml` 更新後は `make sync-opencode` で `opencode/opencode.jsonc` を再生成します。

### 4. omo.jsonc プロファイル（profiles.personal / profiles.work）の更新ルール

OMO ネイティブプロファイル方式では、モデル設定は `opencode/omo.jsonc` 内の `profiles.personal` / `profiles.work` で管理されます。これらはランチャー（`_scripts/opencode-wrapper.sh`）が `OMO_PROFILE=personal|work` 環境変数を設定し、`~/.omo/omo.jsonc` を読み込むことで有効化されます。

- `profiles.personal`: Bedrock モデル（`amazon-bedrock/*`）を含めず、OpenAI / Kimi / Gemini / GLM / Qwen / Minimax 等の最新モデルを `agents.<name>.model` / `fallback_models`、および `categories.<name>.model` / `fallback_models` に割り当てます。
- `profiles.work`: Bedrock モデルのみを使用します（`hephaestus.disabled: true` 等の既存設定は維持）。最新の Bedrock Claude モデル（`global.anthropic.claude-*`）を同じく `agents` / `categories` 各モデル・フォールバックに割り当てます。

### 5. opencode/README.md の更新ルール

- `https://github.com/code-yeongyu/oh-my-openagent` の最新リリースを確認します。
- 更新対象: `Target Version` セクション、知能カテゴリー・エージェント構成のデフォルト推奨モデル一覧。
- **保護対象**: `profiles.personal` / `profiles.work` の切り替え手順、zsh 連携スクリプトやエイリアスの設定解説、`apm.yml` からのプラグイン同期手順および構造的説明。
- 丸ごとの置き換えは絶対に避け、差分のみを部分的にアップデートします。

## 注意点

- `apm.yml` は SSOT。書き換えは対象行のみの最小差分にし、YAML 全体を再整形しない。
- 版数だけ / ハッシュだけを差し替え、引用符・インデント・`[all]` などの extras・`//subpath` は保持する。
- 適用後の再解決には `make apm-install`（`apm.lock.yaml` を更新）が必要。MCP 版数変更時は `make sync-mcp`、スキル/プラグイン変更時は `make sync-agents`、OpenCode モデル/環境変更時は `make sync-opencode` を案内する（このスキルでは自動実行しない）。
- 編集後は `python .claude/skills/apm-updater/scripts/check_updates.py --validate-duplicates` を実行して重複がないか確認する。
