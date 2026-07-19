---
name: apm-updater
description: Checks and updates THIS repository's apm.yml and the OpenCode files derived from it. Handles (1) pinned dependency versions and commit hashes in apm.yml -- APM skill git refs (owner/repo#tag), npm plugins under `plugin:`, and MCP server packages under `dependencies.mcp` -- and (2) LLM model whitelists in apm.yml plus the OpenCode environment profiles (opencode/personal.env, opencode/work.env) and opencode/README.md using the latest model-schema from models.dev. Use whenever the user wants to bump apm.yml dependencies, refresh MCP/plugin/skill pins, check if apm.yml is outdated, update OpenCode LLM model settings, or sync opencode/README.md with the latest oh-my-openagent release. Do NOT use for package.json / uv / other lockfile bumps, GitHub Actions version updates, or adding brand-new MCP/skill/plugin entries to apm.yml.
---

# apm.yml / OpenCode 一括最新化スキル

## Context / 目的

このリポジトリ (`dotfiles-ai`) の [apm.yml](../../../apm.yml) は、外部スキル・プラグイン・MCP サーバー・LLM モデル定義の **SSOT（Single Source of Truth）** です。ここに固定されている版数、コミットハッシュ、モデル whitelist を最新に保つ作業は手作業だと地味で間違えやすいです。

このスキルはその一連を安全に回します。

- **「最新版/モデルの検出」は決定的なスクリプトに任せる**。
- **「バージョン間で何が変わったか」の説明は人間が判断できる形で必ず提示する**。
- **apm.yml への書き込みはユーザーの承認後にのみ行う**。
- **生成物は直接編集しない**: `opencode.jsonc` や
  `gemini/settings.json` などは、`apm.yml` を最小差分で更新した後、
  決められた `make` コマンドで再同期する。

## いつ使うか

- 「apm.yml のバージョンを最新にして」「依存を更新して」「古くなってない?」
- 「chronos-graph のハッシュを最新コミットに」「nexus を上げて」「プラグインを bump して」
- 更新に伴って「何が変わったか教えて」「変更点を出して」と言われたとき
- 「OpenCode のモデル設定を最新化して」「models.dev のモデルスキーマに合わせて」「personal.env / work.env のモデルを更新して」
- 「opencode/README.md を oh-my-openagent の最新リリースに合わせて更新して」
- 「make sync-opencode」「make check-sync-opencode」を実行して検証して

## 前提と安全設計

- **SSOT を壊さない**: `apm.yml` から `opencode.jsonc` や
  `gemini/settings.json` などが生成されます。生成物を直接いじらず、
  常に `apm.yml` を最小差分で書き換えます。YAML 全体を再整形すると
  巨大な差分になりレビュー不能になるため、対象行だけを置換します。
- **必ず差分提示 → 承認 → 適用**: 更新テーブルと各依存の変更点を先に出し、承認を得てから書き込みます。
- **`@latest` / 未固定は既定で据え置き**: `@latest` や版数なしの依存は意図的に最新追従にしている可能性が高いため、現状の解決先を報告するだけに留め、勝手にピン留めしません。
- **git 操作はしない**: コミット/プッシュはこのスキルでは実行せず、Conventional Commits（日本語）のコミットメッセージ案を提示するに留めます。
- **再同期・検証は案内のみ**: `apm.yml` 更新後に必要な `make apm-install` / `make sync-opencode` などは、自動実行せず手順として案内します（ネットワークや生成物への影響が大きいため）。

## ワークフロー

### A. 依存バージョン・コミットハッシュの更新

#### A1. 現状インベントリの取得

同梱スクリプトで `apm.yml` 内の「版数/ハッシュが固定された依存」を機械的に洗い出します。

```bash
python .claude/skills/apm-updater/scripts/check_updates.py --json
```

- `--json`: 機械可読な結果（後段の編集で正確な行・現在値を参照するために使う）。
- 人間向けの表がほしいときは引数なしで実行。
- ネットワークを使わず在庫だけ見たいときは `--no-network`。

検出される種別:

- `plugin` … トップレベル `plugin:` の npm パッケージ（例 `@yohi/justice@2.3.0`, `oh-my-openagent@4.15.1`）
- `mcp-npm` … MCP サーバーの `args:` にある npm 指定（例 `@yohi/nexus@1.22.0`）
- `mcp-git` … MCP の `git+https://....git@<hash>` 形式のコミットハッシュ（例 chronos-graph）
- `apm-skill` … `dependencies.apm` の `owner/repo#<tag>` 形式（例 `obra/superpowers#v6.0.2`）
- `latest` … `@latest` 追従（情報表示のみ、既定では変更しない）

#### A2. 最新バージョン / ハッシュの解決

スクリプトが種別ごとに best-effort で解決します（失敗時は `unresolved` と表示し、決してクラッシュしません）。

- npm (`plugin` / `mcp-npm`): `npm view <name> version`
- git tag (`apm-skill`): `git ls-remote --tags` から最新の semver タグ
- git hash (`mcp-git`): `git ls-remote <url> HEAD` の先頭コミット

#### A3. バージョン間差分の説明を生成

更新候補（`update = true`）の各依存について、現在版と最新版の間で何が変わったかを日本語で要約します。単なる版数の羅列ではなく、ユーザーが「上げてよいか」を判断できる材料を出します。情報源の取り方は [references/dependency-inventory.md](references/dependency-inventory.md) を参照してください。

- npm パッケージ: `npm view <name> repository.url` で GitHub リポジトリを特定し、`gh release view <newtag> --repo <owner/repo>` のリリースノート、または compare ビューを使う。
- apm-skill (git tag): `gh release view <newtag> --repo <owner/repo>`、無ければ compare ビュー。
- mcp-git (commit hash): `gh api repos/<owner/repo>/compare/<oldsha>...<newsha>` のコミット一覧、または対象 URL を shallow fetch して `git log --oneline <old>..<new>`。

破壊的変更（BREAKING CHANGE、major バージョンの上昇）は特に目立たせます。リリースノートが取得できない依存は「変更点は取得できなかった（比較 URL: ...）」と正直に書き、リンクだけでも提示します。

#### A4. 更新サマリの提示とユーザー承認

「出力フォーマット」の通りに、更新テーブル + 各依存の変更点 + 参照 URL をまとめて提示し、適用してよいか承認を求めます。ユーザーが一部だけ適用したい場合（例: 「nexus 以外」）に対応できるよう、依存ごとに識別しやすく並べます。

#### A5. apm.yml への適用（承認後のみ）

承認された依存についてのみ、`apm.yml` の該当行を最小差分で書き換えます。版数だけ / ハッシュだけを置換し、周囲の引用符・インデント・`[all]` などの extras は保持します。

### B. OpenCode LLM モデル・環境プロファイル・README の更新

#### B1. 最新モデルスキーマ情報の取得と解析

`https://models.dev/model-schema.json` から JSON スキーマを取得します。
`["$defs"]["Model"]["enum"]` のリストに含まれる最新のモデル識別子（例: `openai/gpt-5.4-mini` や `amazon-bedrock/global.anthropic.claude-opus-4-8` など）を抽出します。

これは `check_updates.py --models` で同時に確認できます:

```bash
python .claude/skills/apm-updater/scripts/check_updates.py --models
```

#### B2. apm.yml の provider/model セクション更新 (SSOT)

- `apm.yml` はモデル定義の SSOT です。`opencode.jsonc` を直接編集してはいけません。
- `provider` セクション配下の各プロバイダー（`openai`, `nvidia`, `cloudflare-workers-ai`, `opencode`, `amazon-bedrock`, `opencode-go` など）の `whitelist` もしくは `models` リストを、最新スキーマで定義されている有効なモデル名と一致するように更新します。
- **Bedrock モデル（`amazon-bedrock`）の制限**: `amazon-bedrock` の `whitelist` に含めるモデルは、`global.anthropic.claude-*`（グローバルプレフィックス付きの最新 Claude モデル）および `openai.gpt-*`（Bedrock 上で提供される OpenAI モデル）のみとします。その他のリージョン固有モデルや古い世代のモデルは whitelist に含めず、除外してください。
- 更新後、以下を実行して `opencode/opencode.jsonc` を再生成します:

```bash
make sync-opencode
```

#### B3. 環境プロファイル (personal.env & work.env) の更新

`opencode/personal.env` および `opencode/work.env` に定義されている各エージェントおよびカテゴリのモデル・フォールバックモデルを更新します。

- **`personal.env` の更新ルール**:
  - AWS Bedrock モデル（`amazon-bedrock/*`）を**含めない**ように構成します。
  - 最新の OpenAI モデル（`openai/gpt-*`）や、その他利用可能な最新モデル（Kimi, Gemini, GLM, Qwen, Minimax など）を割り当てます。
- **`work.env` の更新ルール**:
  - Bedrock モデル（`amazon-bedrock/*`）**のみ**を使用するように構成します（他のプロバイダーは含めません。ただし `HEPHAESTUS_DISABLED=true` などの例外設定は維持します）。
  - 最新の Bedrock Claude モデル（`global.anthropic.claude-*`）を割り当てます。

#### B4. opencode/README.md の更新

- GitHub の `https://github.com/code-yeongyu/oh-my-openagent` から最新のリリース（Release Tag）および変更内容を確認します。
- 公式の変更内容に基づいて、`opencode/README.md` に記載されている `Target Version` や、知能カテゴリー・エージェント構成のデフォルト推奨モデルなどの差分のみを部分的にアップデートします。
- **注意**: 当プロジェクト固有の説明（`work.env`/`personal.env` の切り替え方法、zsh 連携、`apm.yml` からのプラグイン同期など）を消去してしまわないよう、丸ごとの置き換えは絶対に避けてください。
  - **更新すべき対象範囲**:
    - `Target Version` セクション
    - 知能カテゴリー・エージェント構成のデフォルト推奨モデル一覧
  - **維持（保護）すべき対象範囲**:
    - `work.env` / `personal.env` の環境切り替え手順
    - zsh 連携スクリプトやエイリアスの設定解説
    - `apm.yml` からのプラグイン同期手順およびその構造的説明

### C. 整合性の検証とクリーンアップ

更新完了後、静的解析・構文チェック等のチェックを実施します:

```bash
make check-sync-opencode
```

コミットを行う際は、Git Standards に従って Conventional Commits の規則（例: `feat(opencode): モデルおよび環境プロファイルの最新化` や `chore(deps): apm.yml の依存を最新化`）を遵守します。

## 出力フォーマット（依存更新時）

更新サマリは必ず次の構成で出します。まず全体テーブル、続いて依存ごとの変更点、最後に承認依頼です。

```text
## apm.yml 更新サマリ

| 種別 | 依存 | 現在 | 最新 | 更新 |
|------|------|------|------|------|
| plugin | @yohi/justice | 2.3.0 | 2.4.1 | あり |
| mcp-git | yohi/chronos-graph | cb1f33f | a1b2c3d | あり |
| mcp-npm | @yohi/nexus | 1.22.0 | 1.22.0 | なし |
| plugin | @nick-vi/opencode-type-inject | latest | (latest 追従) | 据え置き |

### @yohi/justice: 2.3.0 -> 2.4.1
- 主な変更点:
  - <箇条書きで要約>
  - <BREAKING があれば明示>
- 参照: https://github.com/<owner/repo>/compare/v2.3.0...v2.4.1

### yohi/chronos-graph: cb1f33f -> a1b2c3d
- 主な変更点:
  - <コミット要約>
- 参照: https://github.com/yohi/chronos-graph/compare/cb1f33f...a1b2c3d

---
上記を apm.yml に適用してよいですか?（一部のみ・全部・見送り を選べます）
```

適用後は、変更した行と「次アクション」（`make apm-install` / `make sync-mcp` / `make sync-agents` / `make sync-opencode`）+ コミットメッセージ案を短く報告します。

## 参照

- [references/dependency-inventory.md](references/dependency-inventory.md) — 依存の種類別「最新取得」「差分取得」レシピ、現在の apm.yml インベントリのスナップショット、および LLM モデルスキーマ更新手順。
- [scripts/check_updates.py](scripts/check_updates.py) — 検出 + 最新解決スクリプト（ASCII のみ・原則 stdlib のみ）。
