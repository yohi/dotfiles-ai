# OpenCode (oh-my-openagent) 設定ガイド

このディレクトリには、AIエージェントハーネス `oh-my-openagent`（通称 `oh-my-opencode`）を最大限に活用するための設定ファイルが格納されています。

## 1. 構成ファイル

### `opencode.jsonc`
OpenCode プラットフォーム自体のコア設定ファイルです。

### `oh-my-openagent.jsonc`
エージェントの知能構成、役割定義、ツール権限などを管理するメイン設定ファイルです。
*Target Version: v3.17.15*

## 2. 使い方

以前のようなテンプレートやプロファイル切り替えスクリプト（`omo-profiles.sh`）は廃止されました。
設定を変更する場合は、上記の `.jsonc` ファイルを直接編集してください。

これらのファイルは Git で追跡されているため、変更履歴を管理できます。

## 3. 知能カテゴリーとエージェント (11 Specialists)

Sisyphus（監督）は、タスクの性質に応じて最適な「知能カテゴリー」を選択し、専門エージェントを指揮します。

### 知能カテゴリー一覧 (Core Categories)

タスクの難易度や種類に応じてモデルとパラメータを最適化する定義です。

| カテゴリー | 特徴・バリアント | 想定される用途 |
| :--- | :--- | :--- |
| **ultrabrain** | `xhigh` / 最強推論 | 複雑な計画立案、コード監査、アーキテクチャ設計、リスク分析。 |
| **deep** | `medium` / 自律解決 | 難解なバグ修正、機能実装、リファクタリングなど職人的作業。 |
| **quick** | `fast` / 高速応答 | ドキュメント検索、コード探索、些細な修正、プロトタイピング。 |
| **visual-engineering** | UI/UX 特化 | UIデザイン解析、CSSアニメーション、フロントエンド最適化。 |
| **writing** | 文書作成 特化 | 技術解説、ドキュメンテーション、リリースノートの作成。 |
| **artistry** | 創造性 特化 | ジェネレーティブアート、クリエイティブな発想、芸術的表現。 |
| **unspecified-high** | 高負荷汎用 | 特定の役割に当てはまらないが、高い知能を要する汎用作業。 |
| **unspecified-low** | 低負荷汎用 | 定形的な作業、単純なデータ変換などの低コストな汎用作業。 |

### エージェント一覧とカテゴリー・マッピング

各エージェントは役割を持ち、デフォルトで以下のカテゴリーが割り当てられています。

| エージェント | カテゴリー | 役割・専門領域 |
| :--- | :--- | :--- |
| **Sisyphus** | `ultrabrain` | 司令塔。全体の品質管理、タスクの分解と委譲。 |
| **Hephaestus** | `deep` | 実装職人。自律的なコードの書き込み、複雑なロジック実装。 |
| **Oracle** | `ultrabrain` | 賢者。アーキテクチャ設計の相談、難解なバグのデバッグ。 |
| **Librarian** | `quick` | 司書。外部ドキュメントやOSSの実装例の高速検索。 |
| **Explore** | `quick` | 探検家。コードベースの高速探索、grep検索、スキャフォールディング。 |
| **Prometheus** | `ultrabrain` | 戦略家。タスクの分解と並列実行計画（Agent Swarm）の作成。 |
| **Metis** | `ultrabrain` | 計画コンサル。計画前のリスク特定と曖昧さの排除。 |
| **Momus** | `ultrabrain` | 計画レビュアー。Prometheusが作成した計画の厳格な検証。 |
| **Atlas** | `ultrabrain` | 現場監督。環境管理、Todo項目の体系的な管理と調整。 |
| **Multimodal-Looker** | `ultrabrain` | 視覚アナリスト。UIデザイン、画像、図解、PDFの解析。 |
| **Sisyphus-Junior** | (動的) | 作業員. 特定のカテゴリーに特化して生成される実行用エージェント. |

## 4. LLMモデル選択のベストプラクティス

エージェントの能力を最大限に引き出すためには、カテゴリーごとに適した「脳（モデルファミリー）」を割り当てることが重要です。

### 推奨スタック: OpenCode Go + OpenAI (Best Value)
最も効率的でバランスの良い組み合わせです。

- **OpenCode Go ($10/mo)**: Kimi (Claude系代替), Qwen (Gemini系代替), MiniMax を提供。
- **OpenAI Plus/Pro ($20/mo)**: GPT-5.5/5.4 (実装・監査系) を提供。

### モデルファミリーの特性と使い分け

| ファミリー | 特徴 | 最適なカテゴリー / エージェント |
| :--- | :--- | :--- |
| **Claude系**<br>(Opus, Kimi, GLM) | **指示追従型。** 長大で複雑な手順、多段のTodo管理に極めて強い。 | `ultrabrain`, `unspecified` / Sisyphus, Atlas |
| **GPT系**<br>(GPT-5.5/5.4) | **原則駆動型。** 最小限の指示で自律的に解決策を見出す。深い実装に強い。 | `deep`, `ultrabrain` / Hephaestus, Oracle, Momus |
| **Gemini系**<br>(Gemini, Qwen) | **視覚・推論型。** デザイン解析、CSS、UIの構造理解に特化。 | `visual-engineering`, `artistry` / Looker |

### カテゴリー別・推奨モデルと代替ルール

| カテゴリー | 第一推奨 (Native) | 第二推奨 (Alternative) | 注意点 |
| :--- | :--- | :--- | :--- |
| **ultrabrain** | `gpt-5.5` (xhigh) | `claude-opus-4.7` (max) | 最高の推論能力を要求。 |
| **deep** | `gpt-5.5` (medium) | `claude-opus-4.7` (max) | **GPT推奨。** Claudeでの代用は指示を詳細にする必要あり。 |
| **quick** | `gpt-5.4-mini` | `minimax-m2.7` | 知能より速度とコストを優先。 |
| **visual** | `gemini-3.1-pro` | `qwen3.6-plus` | Claude/Kimiでは視覚解析精度が低下する。 |
| **writing** | `kimi-k2.6` | `gemini-3-flash` | 自然な文章表現と指示への正確さを重視。 |

---
*Updated: 2026-05-27*

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

