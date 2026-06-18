---
name: custom/update-opencode-models
description: Updates the LLM models in apm.yml, personal.env, and work.env using the latest model-schema from models.dev, and updates opencode/README.md from the latest release of oh-my-openagent.
---

# Update OpenCode Models and Environments

## Context
このスキルは、OpenCode（oh-my-openagent）のLLMモデル設定（`apm.yml`）および環境プロファイル（`personal.env`、`work.env`）を最新のLLMモデル定義スキーマ（`https://models.dev/model-schema.json`）に基づいて更新し、また `opencode/README.md` を `oh-my-openagent` の最新リリースから同期・最新化するための手順とルールを提供します。

## Instructions
<instructions>

### 1. 最新モデルスキーマ情報の取得と解析
- `https://models.dev/model-schema.json` から JSON スキーマを取得します。
- `["$defs"]["Model"]["enum"]` のリストに含まれる最新のモデル識別子（例: `openai/gpt-5.4-mini` や `amazon-bedrock/global.anthropic.claude-opus-4-8` など）を抽出します。
- 抽出したモデル情報をもとに、プロジェクトで使用可能なモデル一覧を一時的な対照表として整理します。

### 2. apm.yml の更新 (SSOT)
- `apm.yml` はモデル定義の Single Source of Truth (SSOT) です。`opencode.jsonc` を直接編集してはいけません。
- `provider` セクション配下の各プロバイダー（`openai`, `nvidia`, `cloudflare-workers-ai`, `opencode`, `amazon-bedrock`, `opencode-go` など）の `whitelist` もしくは `models` リストを、最新スキーマで定義されている有効なモデル名と一致するように更新します。
- **Bedrock モデル（`amazon-bedrock`）の制限**:
  - `amazon-bedrock` の `whitelist` に含めるモデルは、**`global.anthropic.claude-*`（グローバルプレフィックス付きの最新 Claude モデル）および `openai.gpt-*`（Bedrock上で提供される OpenAI モデル）のみ**とします。
  - その他のリージョン固有モデルや古い世代のモデルは whitelist に含めず、除外してください。
- 更新後、以下のコマンドを実行して `opencode/opencode.jsonc` を再生成します：
  ```bash
  make sync-opencode
  ```

### 3. 環境プロファイル (personal.env & work.env) の更新
`opencode/personal.env` および `opencode/work.env` に定義されている各エージェントおよびカテゴリのモデル・フォールバックモデルを更新します。

- **`personal.env` の更新ルール**:
  - AWS Bedrock モデル（`amazon-bedrock/*`）を**含めない**ように構成します。
  - 最新の OpenAI モデル（`openai/gpt-*`）や、その他利用可能な最新モデル（Kimi, Gemini, GLM, Qwen, Minimax など）を割り当てます。
- **`work.env` の更新ルール**:
  - Bedrock モデル（`amazon-bedrock/*`）**のみ**を使用するように構成します（他のプロバイダーは含めません。ただし `HEPHAESTUS_DISABLED=true` などの例外設定は維持します）。
  - 最新の Bedrock Claude モデル（`global.anthropic.claude-*`）を割り当てます。

### 4. opencode/README.md の更新
- GitHub の `https://github.com/code-yeongyu/oh-my-openagent` から最新のリリース（Release Tag）および変更内容を確認します。
- 公式の変更内容に基づいて、`opencode/README.md` に記載されている `Target Version` や、知能カテゴリー・エージェント構成のデフォルト推奨モデルなどの差分のみを部分的にアップデートします。
- **注意**: 当プロジェクト固有の説明（`work.env`/`personal.env` の切り替え方法、zsh連携、apm.yml からのプラグイン同期など）を消去してしまわないよう、丸ごとの置き換えは絶対に避けてください。
  - **更新すべき対象範囲**:
    - `Target Version` セクション
    - 知能カテゴリー・エージェント構成のデフォルト推奨モデル一覧
  - **維持（保護）すべき対象範囲**:
    - `work.env` / `personal.env` の環境切り替え手順
    - zsh 連携スクリプトやエイリアスの設定解説
    - `apm.yml` からのプラグイン同期手順およびその構造的説明

### 5. 整合性の検証とクリーンアップ
- 更新完了後、静的解析・構文チェック等のチェックを実施します：
  ```bash
  make check-sync-opencode
  ```
- コミットを行う際は、Git Standards に従って Conventional Commits の規則（例: `feat(opencode): モデルおよび環境プロファイルの最新化`）を遵守します。

</instructions>
