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

### personal のモデル選択とプロバイダー選択の責務分離

`personal` では、OmO と Cloudflare AI Gateway Dynamic Routing の責務を分離します。

```text
OmO
  task / category から LLM モデルを選択
       ↓
Cloudflare AI Gateway Dynamic Route
  同じ LLM モデルを維持したまま provider を選択 / failover
```

Kimi K2.7 / K3、GLM-5.2 / GLM-5.3 Flash、DeepSeek V4 Flash は `cloudflare-ai-gateway-dynamic/dynamic/*` を利用します。Sakura / Ollama / OpenCode Go / Command Code GOAT の選択は OmO では行わず、`cf-ai-gw-dynamic-routing` 側の同一モデル Route に委譲します。

Sisyphus-Junior は意図的に固定モデルを設定しません。category-routed task では、選択された category のモデルを引き継がせます。

## 3. 知能カテゴリーとエージェント (10 Specialists)

Sisyphus（監督）は、タスクの性質に応じて最適な「知能カテゴリー」を選択し、専門エージェントを指揮します。

### 知能カテゴリー一覧 (Core Categories)

タスクの難易度や種類に応じてモデルとパラメータを最適化する定義です。

| カテゴリー | 特徴・バリアント | 想定される用途 | デフォルトモデル (personal カタログ) |
| :--- | :--- | :--- | :--- |
| **ultrabrain** | `max` / 最強推論 | 複雑な計画立案、コード監査、アーキテクチャ設計、リスク分析。 | `sol-octg` |
| **deep** | `high` / 自律解決 | 難解なバグ修正、機能実装、リファクタリングなど職人的作業。 | `terra-octg` |
| **quick** | `low` / 高速応答 | ドキュメント検索、コード探索、些細な修正、プロトタイピング。 | `luna` |
| **visual-engineering** | UI/UX 特化 | UIデザイン解析、CSSアニメーション、フロントエンド最適化。 | `gemini-pro` |
| **unspecified-high** | 高負荷汎用 | 特定の役割に当てはまらないが、高い知能を要する汎用作業。 | `glm-52` |
| **unspecified-low** | 低負荷汎用 | 定形的な作業、単純なデータ変換などの低コストな汎用作業。 | `luna` |
| **writing** | 文書作成 特化 | 技術解説、ドキュメンテーション、リリースノートの作成。 | `kimi-k27` |
| **artistry** | 創造性 特化 | ジェネレーティブアート、クリエイティブな発想、芸術的表現。 | `gemini-pro` |

### エージェント一覧とカテゴリー・マッピング

各エージェントは役割を持ち、`personal` 構成では以下の実モデルが割り当てられています。

| エージェント | カテゴリー | personal 実モデル (provider/model) | 役割・専門領域 |
| :--- | :--- | :--- | :--- |
| **Sisyphus** | `ultrabrain` | `cloudflare-ai-gateway-dynamic/dynamic/kimi-k2.7-code`; ultrawork: `openai/gpt-5.6-sol` (high) | 司令塔。全体の品質管理、タスクの分解と委譲。 |
| **Hephaestus** | `deep` | `openai/gpt-5.6-sol` → OCTG Sol | 実装職人。反復量が多いため Plus Sol を主系とし、OCTG STANDARD を枯渇させにくくする。 |
| **Oracle** | `ultrabrain` | `cloudflare-ai-gateway-octg/gpt-5.6-terra` | 賢者。アーキテクチャ設計の相談、難解なバグのデバッグ。 |
| **Librarian** | `quick` | `openai/gpt-5.6-luna` | 司書。外部ドキュメントやOSSの実装例の高速検索。 |
| **Explore** | `quick` | `openai/gpt-5.6-luna` | 探検家。コードベースの高速探索、grep検索、スキャフォールディング。 |
| **Multimodal-Looker** | `ultrabrain` | `cloudflare-ai-gateway/google-ai-studio/gemini-3.1-pro` | 視覚アナリスト。UIデザイン、画像、図解、PDFの解析。 |
| **Prometheus** | `ultrabrain` | `cloudflare-ai-gateway-dynamic/dynamic/kimi-k2.7-code` | 流れ者。タスクの分解と並列実行計画の作成。 |
| **Metis** | `ultrabrain` | `cloudflare-ai-gateway-dynamic/dynamic/kimi-k2.7-code` | 計画コンサル。計画前のリスク特定と曖昧さの排除。 |
| **Momus** | `ultrabrain` | `cloudflare-ai-gateway-octg/gpt-5.6-terra` | 計画レビュアー。Prometheusが作成した計画の厳格な検証。 |
| **Atlas** | `ultrabrain` | `cloudflare-ai-gateway-dynamic/dynamic/kimi-k2.7-code` | 現場監督。環境管理、Todo項目の体系的な管理と調整。 |

## 4. LLMモデル選択のベストプラクティス

エージェントの能力を最大限に引き出すためには、エージェントの思考スタイルに合った「脳（モデルファミリー）」を割り当てることが重要です。

### 思考スタイルとモデルの相性

| スタイル | 特徴 | 適合モデル | 最適なエージェント |
| :--- | :--- | :--- | :--- |
| **メカニクス駆動** | **指示追従型。** 長大で複雑な手順、多段のTodo管理に極めて強い。 | Kimi Family, Claude Family | Sisyphus, Atlas, Metis |
| **原則駆動** | **自律探索型。** 最小限の指示で自律的に解決策を見出す。深い実装に強い。 | GPT Family (Sol, Terra, Luna), GLM Family | Hephaestus, Oracle, Momus |
| **視覚推論型** | **UI・構造理解。** デザイン解析、CSS、レイアウトの理解に特化。 | Gemini Family | Looker |

### カテゴリー別・モデルルーティング一覧

表中の短縮名は `omo.jsonc` の `models` カタログのキーです。v4.19.4 の一部 task path には alias 解決の不整合があるため、実設定では完全修飾 `provider/model` を記述します。

| カテゴリー | personal デフォルト | personal フォールバックチェーン | work (Bedrock) |
| :--- | :--- | :--- | :--- |
| **ultrabrain** | `sol-octg` (max) | `sol-octg` (max) → `sol` (max) → `terra-octg` (high) → `terra` (high) | `opus` (max) → `sonnet` |
| **deep** | `terra-octg` (high) | `terra-octg` (high) → `glm-52` → `terra` (high) → `sol` (medium) | `opus` (max) → `sonnet` |
| **quick** | `luna` (low) | `luna` (low) → `deepseek-v4-flash` | `haiku` → `sonnet` |
| **visual-engineering** | `gemini-pro` (high) | `gemini-pro` (high) → `kimi-k27` | `opus` (max) → `sonnet` |
| **artistry** | `gemini-pro` (high) | `gemini-pro` (high) → `kimi-k27` | `sonnet` → `haiku` |
| **unspecified-high** | `glm-52` | `glm-52` → `luna` (max) → `kimi-k3` | `opus` (max) → `sonnet` |
| **unspecified-low** | `luna` (medium) | `luna` (medium) → `glm-53-flash` | `sonnet` → `haiku` |
| **writing** | `kimi-k27` | `kimi-k27` | `sonnet` → `haiku` |

### OCTG Sol (STANDARD) の利用方針

OCTG の STANDARD pool は 1M tokens / UTC day と小さいため、すべての Sol workload の primary にはしません。一方で全経路を secondary にすると未使用のまま日次枠が失効しやすいため、**高価値・比較的低頻度の `ultrabrain` では OCTG Sol を primary のまま維持**します。

高頻度で実装・テスト・修正を反復する Hephaestus は Plus Sol を primary とし、OCTG Sol は fallback にします。また `modelConcurrency` で OCTG Sol を 1 並列に制限し、巨大コンテキスト要求の同時 reservation を抑制します。

### Dynamic open model の役割

| モデル | 主な役割 |
| :--- | :--- |
| **Kimi K2.7 Code** | Sisyphus / Prometheus / Metis / Atlas / writing の主力オーケストレーション |
| **Kimi K3** | 高負荷汎用タスクの premium orchestration reserve |
| **GLM-5.2** | substantial coding / deep fallback / unspecified-high primary |
| **GLM-5.3 Flash** | 軽〜中程度の agentic work、unspecified-low fallback |
| **DeepSeek V4 Flash** | 高ボリューム探索・調査、quick fallback |

**GLM-5.3 full は意図的に採用していません。** GLM-5.2 が substantial coding を担当し、GLM-5.3 Flash が agentic-fast という独立した役割を持つためです。Go / GOAT の共有 quota をさらに消費する full 5.3 を追加するより、現時点ではこの2モデルの役割分離を優先します。

---
*Updated: 2026-09-07*

## 5. 環境の切り替え (Switching Environments)

モデル構成をシーン（仕事用・個人用など）に合わせて切り替えるには、OMO ネイティブプロファイルを利用します。

### 用意されているファイル
- **`profiles.work`**: Amazon Bedrock の Claude を中心とした業務向け構成。
- **`profiles.personal`**: OpenAI、Kimi、GLM、DeepSeek、Gemini を組み合わせた個人・検証向け構成。

### 適用方法
OpenCode を直接起動する場合は `OMO_PROFILE` を指定します。リポジトリの wrapper を利用する場合は `PROFILE` を渡すと、wrapper が内部で `OMO_PROFILE` に変換します。

```bash
# OpenCode を直接起動する場合
OMO_PROFILE=work opencode
OMO_PROFILE=personal opencode

# リポジトリの wrapper を利用する場合
PROFILE=work _scripts/opencode-wrapper.sh
PROFILE=personal _scripts/opencode-wrapper.sh
```

この方法により、`omo.jsonc` を書き換えることなく、推論エンジンのスタックを切り替えられます。

## 6. 高度な使い方：PROFILEによる自動切り替え

本プロジェクトでは、`dotfiles-zsh` と連携し、`PROFILE=work opencode` と打つだけでモデルプロファイルの切替と「空きポートの自動割り当て」を同時に行うシェル関数が用意されています。ランチャー内部で `OMO_PROFILE` に変換されます。

### 統合場所
- `~/dotfiles/components/dotfiles-zsh/functions/opencode.zsh`

この関数は `dotfiles-zsh` の起動時に自動的にロードされます。

### 実装されている機能
- **空きポートの自動検出**: `ss` または `lsof` を使用し、4090-4100 の範囲で未使用のポートを自動的に探し、`--port` 引数として付与します。
- **プロファイルの自動ロード**: `PROFILE` 環境変数またはランチャー引数を `OMO_PROFILE` に変換して OMO ネイティブプロファイルを選択します（未指定時はデフォルトで `personal` プロファイルをロードします）。プロファイル用envファイルは読み込みません。

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

### Codex Work That Scales to the Task
LazyCodex は、すべての実装を1つの汎用実行エージェントにルーティングする代わりに、実際の変更サイズとリスクから低・中・高難易度のワーカーを選択するようになりました。新規インストール時のデフォルトは372Kコンテキストウィンドウを持つ GPT-5.6 Sol となり、探索（exploration）およびディープアナリティクス（deep-analysis）カテゴリーは新しい Luna および Terra ルート（`gpt-5.6-luna`, `gpt-5.6-terra`）を使用します。これにより、軽微な作業は低コストで、真に推論能力が必要な変更はより強力に対応できるようになります。

### ULW Loops Recover and Prove the Right Revision
中断された ULW 実行は、制限付きの Stop フックを介して自動的に再開できるようになりました。証拠（evidence）は試行ごとに分離され、それを生成したコミットに関連付けられ、最終レビュアーが開始する前にチェックされます。スポーンガードとレビュアーのプリフライトチェックにより、暴走ファンアウトを防ぎ、古い証拠が新しい HEAD の証明として誤って再ラベル付けされるのを防ぎます。

### More Useful, Safer Task Output
Senpi タスク TUI は、解決されたモデルの詳細とコンテキストステータス、制御、および出力の抜粋を表示するようになりました。行幅が制限され、ターミナル制御シーケンスがクリーンアップされたため、狭いターミナルや信頼できないタスク出力によってインターフェースが崩れることがなくなりました。

### Cleaner Plugin Installs and Honest Prompt QA
Codex バンドルは、無効な相対デーモンパスを持つネストされたコンポーネントの MCP マニフェスト（`.mcp.json`）を同梱しなくなりました。プロンプトとスキルの変更は、文言の完全一致や単語数のテストといった脆い手法ではなく、パースされた値、ランタイムセンチネル、出荷される成果物の等価性などの振る舞いの境界線でテストされるようになりました。
