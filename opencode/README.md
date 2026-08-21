# OpenCode (oh-my-openagent) 設定ガイド

このディレクトリには、AIエージェントハーネス `oh-my-openagent`（通称 `oh-my-opencode`）を最大限に活用するための設定ファイルが格納されています。

## 1. 構成ファイル

### `opencode.jsonc`
OpenCode プラットフォーム自体のコア設定ファイルです。

### `omo.jsonc`
メインの設定ファイルであり、各専門エージェントに割り当てる LLM モデルや知能カテゴリーなどを管理します。
`profiles.personal` と `profiles.work` で環境別のモデル構成を管理します。
*Target Version: v4.19.4*

## 2. 使い方

以前のようなテンプレートやプロファイル切り替えスクリプト（`omo-profiles.sh`）は廃止されました。
設定を変更する場合は、各ファイルに応じて以下の通り対応してください。

- **`opencode.jsonc`**: `apm.yml` (SSOT) から自動生成されるため、直接編集せず `apm.yml` を編集して `make sync-opencode` を実行してください。このファイルは Git の追跡対象外です。
- **`omo.jsonc`**: このファイルを直接編集してください。このファイルは OMO ネイティブプロファイルの SSOT として Git で追跡されています。

## 3. 知能カテゴリーとエージェント (11 Specialists)

Sisyphus（監督）は、タスクの性質に応じて最適な「知能カテゴリー」を選択し、専門エージェントを指揮します。

### 知能カテゴリー一覧 (Core Categories)

タスクの難易度や種類に応じてモデルとパラメータを最適化する定義です。

| カテゴリー | 特徴・バリアント | 想定される用途 | 推奨モデル (Brain) |
| :--- | :--- | :--- | :--- |
| **ultrabrain** | `xhigh` / 最強推論 | 複雑な計画立案、コード監査、アーキテクチャ設計、リスク分析。 | Kimi K3 → GPT-5.6 Sol |
| **deep** | `xhigh` / 自律解決 | 難解なバグ修正、機能実装、リファクタリングなど職人的作業。 | gpt-5.6-terra (xhigh) |
| **quick** | `low` / 高速応答 | ドキュメント検索、コード探索、些細な修正、プロトタイピング。 | gpt-5.6-luna (low) |
| **visual-engineering** | UI/UX 特化 | UIデザイン解析、CSSアニメーション、フロントエンド最適化。 | Gemini 3.1 Pro |
| **unspecified-high** | 高負荷汎用 | 特定の役割に当てはまらないが、高い知能を要する汎用作業。 | GPT-5.6 Sol (high) |
| **unspecified-low** | `xhigh` / 低負荷汎用 | 定形的な作業、単純なデータ変換などの低コストな汎用作業。 | gpt-5.6-luna (xhigh) |
| **writing** | 文書作成 特化 | 技術解説、ドキュメンテーション、リリースノートの作成。 | Kimi (k2.7-code) |
| **artistry** | 創造性 特化 | ジェネラティブアート、クリエイティブな発想、芸術的表現。 | Gemini 3.1 Pro |

### エージェント一覧とカテゴリー・マッピング

各エージェントは役割を持ち、デフォルトで以下のカテゴリーが割り当てられています。

| エージェント | カテゴリー | 推奨/フォールバックチェーン (優先順) | 役割・専門領域 |
| :--- | :--- | :--- | :--- |
| **Sisyphus** | `ultrabrain` | `kimi-k3` → `claude-fable-5` → `claude-opus-4-8` → `claude-opus-4-7` (max) → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.6-sol` (medium) → `glm-5.2` | 司令塔。全体の品質管理、タスクの分解と委譲。 |
| **Hephaestus** | `deep` | `gpt-5.6-terra` (xhigh) → `gpt-5.6-sol` (medium) | 実装職人。自律的なコードの書き込み、複雑なロジック実装。 |
| **Oracle** | `ultrabrain` | `gpt-5.6-sol` (high) → `qwen3.6-plus` (high) → `claude-opus-4-8` (max) → `glm-5.2` | 賢者。アーキテクチャ設計の相談、難解なバグのデバッグ。 |
| **Librarian** | `quick` | `gpt-5.6-luna` (low) → `gpt-5.6-terra` (medium) → `qwen3.5-plus` → `minimax-m3` → `minimax-m2.7` → `claude-haiku-4-5` | 司書。外部ドキュメントやOSSの実装例の高速検索。 |
| **Explore** | `quick` | `gpt-5.6-luna` (low) → `gpt-5.6-terra` (medium) → `qwen3.5-plus` → `minimax-m3` → `minimax-m2.7` → `claude-haiku-4-5` | 探検家。コードベースの高速探索、grep検索、スキャフォールディング 。 |
| **Prometheus** | `ultrabrain` | `claude-opus-4-8` (max) → `gpt-5.6-sol` (high) → `glm-5.2` → `qwen3.6-plus` | 流れ者。タスクの分解と並列実行計画（Agent Swarm）の作成。 |
| **Metis** | `ultrabrain` | `claude-sonnet-5` → `claude-sonnet-4-6` → `claude-opus-4-8` (max) → `gpt-5.6-sol` (high) → `glm-5.2` → `kimi-k2.5` | 計画コンサル。計画前のリスク特定と曖昧さの排除。 |
| **Momus** | `ultrabrain` | `gpt-5.6-sol` (xhigh) → `claude-opus-4-8` (max) → `qwen3.6-plus` (high) → `glm-5.2` | 計画レビュアー。Prometheusが作成した計画の厳格な検証。 |
| **Atlas** | `ultrabrain` | `kimi-k3` → `claude-sonnet-5` → `claude-sonnet-4-6` → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.6-sol` (medium) → `glm-5.2` | 現場監督。環境管理、Todo項目の体系的な管理と調整。 |
| **Multimodal-Looker** | `ultrabrain` | `kimi-k3` → `gpt-5.6-sol` (medium) → `kimi-k2.7-code` → `kimi-k2.6` → `glm-5.2` | 視覚アナリスト。UIデザイン、画像、図解、PDFの解析。 |
| **Sisyphus-Junior** | (動的) | `kimi-k3` → `claude-sonnet-5` → `claude-sonnet-4-6` → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.6-sol` (medium) → `minimax-m3` | 作業員. 特定のカテゴリーに特化して生成される実行用エージェント. |

## 4. LLMモデル選択のベストプラクティス

エージェントの能力を最大限に引き出すためには、エージェントの思考スタイルに合った「脳（モデルファミリー）」を割り当てることが重要です。

### 推奨スタック: OpenCode Go + OpenAI + Kimi K3 (Best Value)
最も効率的でバランスの良い組み合わせです。v4.19.4 では **Kimi K3** がファーストクラス対応となり、Sisyphus 系エージェントの司令塔・Todo 管理に最適です。

- **OpenCode Go ($10/mo)**: Kimi (Claude系代替, **K3 対応**), Qwen (Gemini系代替), MiniMax を提供。
- **OpenAI Plus/Pro ($20/mo)**: GPT-5.6/5.4/5.5 (実装・監査系) を提供。

### 思考スタイルとモデルの相性

| スタイル | 特徴 | 適合モデル | 最適なエージェント |
| :--- | :--- | :--- | :--- |
| **メカニクス駆動** | **指示追従型。** 長大で複雑な手順、多段のTodo管理に極めて強い。 | Claude Family, Kimi, GLM | Sisyphus, Atlas, Metis |
| **原則駆動** | **自律探索型。** 最小限の指示で自律的に解決策を見出す。深い実装に強い。 | GPT Family, DeepSeek, Qwen, Kimi K3 | Hephaestus, Oracle, Momus |
| **視覚推論型** | **UI・構造理解。** デザイン解析、CSS、レイアウトの理解に特化。 | Gemini Family, Qwen | Looker |

### カテゴリー別・推奨モデルと代替ルール (v4.19.4)

| カテゴリー | デフォルトモデル | フォールバックチェーン (優先順) |
| :--- | :--- | :--- |
| **ultrabrain** | `gpt-5.6-sol` (xhigh) | `gpt-5.6-sol` (xhigh) → `qwen3.6-plus` (high) → `claude-opus-5` (max) → `glm-5.2` |
| **deep** | `gpt-5.6-terra` (xhigh) | `gpt-5.6-terra` (xhigh) → `gpt-5.6-sol` (medium) → `claude-opus-5` (max) → `qwen3.6-plus` (high) |
| **quick** | `gpt-5.6-luna` (low) | `gpt-5.6-luna` (low) → `deepseek-v4-flash-free` → `kimi-k3` → `kimi-k2.7-code` |
| **visual-engineering** | `qwen3.6-plus` (high) | `qwen3.6-plus` (high) → `glm-5.2` → `claude-opus-5` (max) → `kimi-k2.7-code` |
| **artistry** | `qwen3.6-plus` (high) | `qwen3.6-plus` (high) → `claude-opus-5` (max) → `gpt-5.6-sol` |
| **unspecified-high** | `gpt-5.6-sol` (high) | `gpt-5.6-sol` (high) → `claude-opus-5` (max) → `glm-5.2` → `kimi-k2.7-code` → `qwen3.6-plus` → `kimi-k2.5` |
| **unspecified-low** | `gpt-5.6-luna` (xhigh) | `gpt-5.6-luna` (xhigh) → `kimi-k3` → `kimi-k2.7-code` → `kimi-k2.6` → `gpt-5.4-mini` → `qwen3.5-plus` → `minimax-m3` |
| **writing** | `kimi-k3` | `kimi-k3` → `kimi-k2.7-code` → `qwen3.5-plus` → `kimi-k2.6` → `claude-sonnet-5` → `minimax-m3` → `minimax-m2.7` |

---
*Updated: 2026-07-30*


## 5. 環境の切り替え (Switching Environments)

モデル構成をシーン（仕事用・個人用など）に合わせて切り替えるには、OMO ネイティブプロファイルを利用します。

### 用意されているファイル
- **`profiles.work`**: Amazon Bedrock の Claude を中心とした業務向け構成。
- **`profiles.personal`**: OpenAI、Kimi、Gemini を組み合わせた個人・検証向け構成。

### 適用方法
`opencode-wrapper.sh` が設定する `OMO_PROFILE` を使って起動してください。

```bash
# 業務用構成（Bedrock）に切り替える場合
PROFILE=work opencode

# 個人用構成（OpenAI）に切り替える場合
PROFILE=personal opencode
```

この方法により、`omo.jsonc` を書き換えることなく、瞬時に推論エンジンのスタックを切り替えることが可能です。

## 6. 高度な使い方：PROFILEによる自動切り替え

本プロジェクトでは、`dotfiles-zsh` と連携し、`PROFILE=work opencode` と打つだけでモデルプロファイルの切替と「空きポートの自動割り当て」を同時に行うシェル関数が用意されています。ランチャー内部で `OMO_PROFILE` に変換されます。

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
     - "@nick-vi/opencode-type-inject@1.2.3"
     - "opencode-vibeguard@1.0.0"
   ```
2. **同期の実行**:
   ```bash
   make sync-opencode
   make setup-opencode
   ```

### v4.19.4 主要新機能

最新の v4.19.4 にて強化・導入された主要機能です。

#### Kimi K3 is a first-class citizen
Sisyphus、Sisyphus-Junior、Atlas に Kimi K3 プロンプトバリアントが追加され、モデルファミリー検出とフォールバックルーティングが自動化されました。OpenRouter 経由でも Moonshot API 直接でも、omo は K3 を認識して適切なプロンプトを選択します。

#### Goals replace Ralph Loop
レガシー Ralph Loop 配線が Goal 機能に置き換わりました。状態、永続化、パーサー、設定移行、`/goal` コマンドが提供され、既存の Ralph Loop 設定は自動移行されます。

#### Senpi task engine reliability
Senpi タスクシステムの信頼性が向上: タスクロスト時の residency 解放、TTL クリーンアップ、レコードストアの FD 再利用、リードポーラーの増分スキャンなど。

#### Senpi platform expansion
`hyperplan` 敵対的計画スキル、Boulder 状態の Senpi セッションプラットフォーム、codegraph MCP 登録、Codex start-work 継続が追加されました。

---

### v4.17.0 主要機能（継続）

最新の v4.17.0 にて強化・導入された主要機能です。

### Codex Work That Scales to the Task
LazyCodex は、すべての実装を1つの汎用実行エージェントにルーティングする代わりに、実際の変更サイズとリスクから低・中・高難易度のワーカーを選択するようになりました。新規インストール時のデフォルトは372Kコンテキストウィンドウを持つ GPT-5.6 Sol となり、探索（exploration）およびディープアナリティクス（deep-analysis）カテゴリーは新しい Luna および Terra ルート（`gpt-5.6-luna`, `gpt-5.6-terra`）を使用します。これにより、軽微な作業は低コストで、真に推論能力が必要な変更はより強力に対応できるようになります。

### ULW Loops Recover and Prove the Right Revision
中断された ULW 実行は、制限付きの Stop フックを介して自動的に再開できるようになりました。証拠（evidence）は試行ごとに分離され、それを生成したコミットに関連付けられ、最終レビュアーが開始する前にチェックされます。スポーンガードとレビュアーのプリフライトチェックにより、暴走ファンアウトを防ぎ、古い証拠が新しい HEAD の証明として誤って再ラベル付けされるのを防ぎます。

### More Useful, Safer Task Output
Senpi タスク TUI は、解決されたモデルの詳細とコンテキストステータス、制御、および出力の抜粋を表示するようになりました。行幅が制限され、ターミナル制御シーケンスがクリーンアップされたため、狭いターミナルや信頼できないタスク出力によってインターフェースが崩れることがなくなりました。

### Cleaner Plugin Installs and Honest Prompt QA
Codex バンドルは、無効な相対デーモンパスを持つネストされたコンポーネントの MCP マニフェスト（`.mcp.json`）を同梱しなくなりました。プロンプトとスキルの変更は、文言の完全一致や単語数のテストといった脆い手法ではなく、パースされた値、ランタイムセンチネル、出荷される成果物の等価性などの振る舞いの境界線でテストされるようになりました。
