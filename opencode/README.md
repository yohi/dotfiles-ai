# OpenCode (oh-my-openagent) 設定ガイド

このディレクトリには、AIエージェントハーネス `oh-my-openagent`（通称 `oh-my-opencode`）を最大限に活用するための設定ファイルが格納されています。

## 1. 構成ファイル

### `opencode.jsonc`
OpenCode プラットフォーム自体のコア設定ファイルです。

### `oh-my-openagent.jsonc`
エージェントの知能構成、役割定義、ツール権限などを管理するメイン設定ファイルです。
*Target Version: v4.10.0*

## 2. 使い方

以前のようなテンプレートやプロファイル切り替えスクリプト（`omo-profiles.sh`）は廃止されました。
設定を変更する場合は、各ファイルに応じて以下の通り対応してください。

- **`opencode.jsonc`**: `apm.yml` (SSOT) から自動生成されるため、直接編集せず `apm.yml` を編集して `make sync-opencode` を実行してください。このファイルは Git の追跡対象外です。
- **`oh-my-openagent.jsonc`**: このファイルを直接編集してください。このファイルは Git で追跡されているため、変更履歴を管理できます。

## 3. 知能カテゴリーとエージェント (11 Specialists)

Sisyphus（監督）は、タスクの性質に応じて最適な「知能カテゴリー」を選択し、専門エージェントを指揮します。

### 知能カテゴリー一覧 (Core Categories)

タスクの難易度や種類に応じてモデルとパラメータを最適化する定義です。

| カテゴリー | 特徴・バリアント | 想定される用途 | 推奨モデル (Brain) |
| :--- | :--- | :--- | :--- |
| **ultrabrain** | `xhigh` / 最強推論 | 複雑な計画立案、コード監査、アーキテクチャ設計、リスク分析。 | GPT-5.5 (xhigh), Claude Fable 5 |
| **deep** | `medium` / 自律解決 | 難解なバグ修正、機能実装、リファクタリングなど職人的作業。 | GPT-5.5 (medium) |
| **quick** | `fast` / 高速応答 | ドキュメント検索、コード探索、些細な修正、プロトタイピング。 | GPT-5.4 Mini, Qwen 3.5 Plus |
| **visual-engineering** | UI/UX 特化 | UIデザイン解析、CSSアニメーション、フロントエンド最適化。 | Gemini 3.1 Pro, Qwen 3.6 Plus |
| **writing** | 文書作成 特化 | 技術解説、ドキュメンテーション、リリースノートの作成。 | Kimi K2.7-Code, Gemini 3 Flash |
| **artistry** | 創造性 特化 | ジェネレーティブアート、クリエイティブな発想、芸術的表現。 | Gemini 3.1 Pro |
| **unspecified-high** | 高負荷汎用 | 特定の役割に当てはまらないが、高い知能を要する汎用作業。 | Claude Fable 5, Opus 4.8/4.7 |
| **unspecified-low** | 低負荷汎用 | 定形的な作業、単純なデータ変換などの低コストな汎用作業。 | Claude Sonnet 4.6, Kimi K2.7-Code |

### エージェント一覧とカテゴリー・マッピング

各エージェントは役割を持ち、デフォルトで以下のカテゴリーが割り当てられています。

| エージェント | カテゴリー | 推奨/フォールバックチェーン (優先順) | 役割・専門領域 |
| :--- | :--- | :--- | :--- |
| **Sisyphus** | `ultrabrain` | `claude-fable-5` → `claude-opus-4-8` → `claude-opus-4-7` (max) → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.5` (medium) → `glm-5` | 司令塔。全体の品質管理、タスクの分解と委譲。 |
| **Hephaestus** | `deep` | `gpt-5.5` (medium) | 実装職人。自律的なコードの書き込み、複雑なロジック実装。 |
| **Oracle** | `ultrabrain` | `gpt-5.5` (high) → `gemini-3.1-pro` (high) → `claude-opus-4-7` (max) → `glm-5.1` | 賢者。アーキテクチャ設計の相談、難解なバグのデバッグ。 |
| **Librarian** | `quick` | `gpt-5.4-mini-fast` → `qwen3.5-plus` → `minimax-m3` → `minimax-m2.7-highspeed` → `claude-haiku-4-5` | 司書。外部ドキュメントやOSSの実装例の高速検索。 |
| **Explore** | `quick` | `gpt-5.4-mini-fast` → `qwen3.5-plus` → `minimax-m3` → `minimax-m2.7-highspeed` → `claude-haiku-4-5` | 探検家。コードベースの高速探索、grep検索、スキャフォールディング 。 |
| **Prometheus** | `ultrabrain` | `claude-opus-4-7` (max) → `gpt-5.5` (high) → `glm-5.1` → `gemini-3.1-pro` | 流れ者。タスクの分解と並列実行計画（Agent Swarm）の作成。 |
| **Metis** | `ultrabrain` | `claude-sonnet-4-6` → `claude-opus-4-7` (max) → `gpt-5.5` (high) → `glm-5.1` → `k2p5` | 計画コンサル。計画前のリスク特定と曖昧さの排除。 |
| **Momus** | `ultrabrain` | `gpt-5.5` (xhigh) → `claude-opus-4-7` (max) → `gemini-3.1-pro` (high) → `glm-5.1` | 計画レビュアー。Prometheusが作成した計画の厳格な検証。 |
| **Atlas** | `ultrabrain` | `claude-sonnet-4-6` → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.5` (medium) | 現場監督。環境管理、Todo項目の体系的な管理と調整。 |
| **Multimodal-Looker** | `ultrabrain` | `gpt-5.5` (medium) → `kimi-k2.7-code` → `kimi-k2.6` → `glm-4.6v` | 視覚アナリスト。UIデザイン、画像、図解、PDFの解析。 |
| **Sisyphus-Junior** | (動的) | `claude-sonnet-4-6` → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.5` (medium) → `minimax-m3` | 作業員. 特定のカテゴリーに特化して生成される実行用エージェント. |

## 4. LLMモデル選択のベストプラクティス

エージェントの能力を最大限に引き出すためには、エージェントの思考スタイルに合った「脳（モデルファミリー）」を割り当てることが重要です。

### 推奨スタック: OpenCode Go + OpenAI (Best Value)
最も効率的でバランスの良い組み合わせです。

- **OpenCode Go ($10/mo)**: Kimi (Claude系代替), Qwen (Gemini系代替), MiniMax を提供。
- **OpenAI Plus/Pro ($20/mo)**: GPT-5.5/5.4 (実装・監査系) を提供。

### 思考スタイルとモデルの相性

| スタイル | 特徴 | 適合モデル | 最適なエージェント |
| :--- | :--- | :--- | :--- |
| **メカニクス駆動** | **指示追従型。** 長大で複雑な手順、多段のTodo管理に極めて強い。 | Claude Family, Kimi, GLM | Sisyphus, Atlas, Metis |
| **原則駆動** | **自律探索型。** 最小限の指示で自律的に解決策を見出す。深い実装に強い。 | GPT Family, DeepSeek | Hephaestus, Oracle, Momus |
| **視覚推論型** | **UI・構造理解。** デザイン解析、CSS、レイアウトの理解に特化。 | Gemini Family, Qwen | Looker |

### カテゴリー別・推奨モデルと代替ルール (v4.10.0)

| カテゴリー | デフォルトモデル | フォールバックチェーン (優先順) |
| :--- | :--- | :--- |
| **ultrabrain** | `openai/gpt-5.5` (xhigh) | `openai/gpt-5.5` (xhigh) → `google/gemini-3.1-pro` (high) → `anthropic/claude-opus-4-7` (max) → `opencode-go/glm-5.1` |
| **deep** | `openai/gpt-5.5` (medium) | `openai/gpt-5.5` (medium) → `anthropic/claude-opus-4-7` (max) → `google/gemini-3.1-pro` (high) |
| **quick** | `openai/gpt-5.4-mini` | `openai/gpt-5.4-mini` → `anthropic/claude-haiku-4-5` → `google/gemini-3-flash` → `opencode-go/minimax-m3` → `opencode/gpt-5-nano` |
| **visual-engineering** | `google/gemini-3.1-pro` (high) | `google/gemini-3.1-pro` (high) → `zai-coding-plan/glm-5` → `anthropic/claude-opus-4-7` (max) → `opencode-go/glm-5.1` → `kimi-for-coding/k2p5` |
| **artistry** | `google/gemini-3.1-pro` (high) | `google/gemini-3.1-pro` (high) → `anthropic/claude-opus-4-7` (max) → `openai/gpt-5.5` |
| **unspecified-high** | `anthropic/claude-fable-5` | `anthropic/claude-fable-5` → `anthropic/claude-opus-4-8` → `anthropic/claude-opus-4-7` (max) → `openai/gpt-5.5` (high) → `opencode-go/kimi-k2.7-code` |
| **unspecified-low** | `anthropic/claude-sonnet-4-6` | `anthropic/claude-sonnet-4-6` → `opencode-go/kimi-k2.7-code` → `opencode-go/kimi-k2.6` → `google/gemini-3-flash` |
| **writing** | `opencode-go/kimi-k2.7-code` | `google/gemini-3-flash` → `opencode-go/kimi-k2.6` → `anthropic/claude-sonnet-4-6` → `opencode-go/minimax-m3` |

---
*Updated: 2026-06-15*

## 5. 環境の切り替え (Switching Environments)

モデル構成をシーン（仕事用・個人用など）に合わせて切り替えるには、`opencode/` 配下の `.env` ファイルを利用します。

### 用意されているファイル
- **`work.env`**: Amazon Bedrock (Claude 3.5 Sonnet/Opus等) を中心とした業務向け構成。
- **`personal.env`**: OpenAI (GPT-5.5等) を中心とした個人・検証向け構成。

### 適用方法
シェルで以下のコマンドを実行して環境変数をロードした後にエージェントを起動してください。

```bash
# 業務用構成（Bedrock）に切り替える場合
export $(cat opencode/work.env | xargs)

# 個人用構成（OpenAI）に切り替える場合
export $(cat opencode/personal.env | xargs)
```

この方法により、`oh-my-openagent.jsonc` を書き換えることなく、瞬時に推論エンジンのスタックを切り替えることが可能です。

## 6. 高度な使い方：PROFILEによる自動切り替え

本プロジェクトでは、`dotfiles-zsh` と連携し、`PROFILE=work opencode` と打つだけで「環境変数のロード」と「空きポートの自動割り当て」を同時に行うシェル関数が用意されています。

### 統合場所
- `~/dotfiles/components/dotfiles-zsh/functions/opencode.zsh`

この関数は `dotfiles-zsh` の起動時に自動的にロードされます。

### 実装されている機能
- **空きポートの自動検出**: `ss` または `lsof` を使用し、4090-4100 の範囲で未使用のポートを自動的に探し、`--port` 引数として付与します。
- **プロファイルの自動ロード**: `PROFILE` 環境変数が指定されている場合、`opencode/{PROFILE}.env` を自動的に `export` します（未指定時はデフォルトで `personal` プロファイルをロードします）。

### 使用例
```bash
# デフォルト（personal）構成で起動
opencode
# 出力例: ✅ Profile [personal] | Port [4090]

# 業務用構成で起動
PROFILE=work opencode
# 出力例: ✅ Profile [work] | Port [4091] (4090が使用中の場合)
```

## 7. プラグイン (機能拡張)

OpenCode の機能を拡張するため、現在以下のプラグインが [apm.yml](../apm.yml) (SSOT) 経由で導入されています。

### 導入済みプラグイン

- **`@nick-vi/opencode-type-inject`**
  - **役割**: ファイル読み取り時に TypeScript 等の型定義を自動注入します。
  - **メリット**: 静的解析エラーの自動フィードバックや型補完の精度を向上させます。
- **`opencode-vibeguard`**
  - **役割**: LLM へのプロンプト送信前に API キーや認証トークン等の機密情報を自動的にマスクし、ローカルで復元します。
  - **メリット**: セキュリティポリシー（機密情報の保護）を厳格に自動化します。

### プラグインの追加・変更手順

プラグインは [opencode.jsonc](opencode.jsonc) に直接記述せず、必ず SSOT である [apm.yml](../apm.yml) の `plugin:` セクションに追加してください。

1. **[apm.yml](../apm.yml) の編集**:
   ```yaml
   plugin:
     - "@nick-vi/opencode-type-inject@latest"
     - "opencode-vibeguard@latest"
   ```
2. **同期の実行**:
   ```bash
   make sync-opencode
   make setup-opencode
   ```

