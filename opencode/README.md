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

### personal のモデル選択とプロバイダー選択

本来の責務分離は次の通りです。

```text
OmO
  task / category から LLM モデルを選択
       ↓
Cloudflare AI Gateway Dynamic Route
  同じ LLM モデルを維持したまま provider を選択 / failover
```

ただし **Cloudflare Dynamic Routing は現在一時停止中**です。新規作成・再作成した Route が provider invocation 前に Error 2005 となる事象（`cloudflare/ai#611`）があり、さらに Dynamic Routing は Custom Providers をまだサポートしていません（`cloudflare/cloudflare-docs#29840`）。

そのため `personal` では当面、Kimi / GLM / DeepSeek の同一モデル provider fallback を OmO の `models` / `fallback_models` で明示し、`cloudflare-ai-gateway-custom` の直結パスを使用します。Providerは **OmOの適性 / Plus Luna主力 / Ollama週次活用 / Go月次温存** に基づき、用途別に選択します。GOAT は週間上限到達のため、Primary / Fallback から一時的に除外しています（モデルカタログ定義は維持し、手動選択は可能）。これにより cache locality を保ちつつ、利用可能なサブスクリプションの利用枠を活用します。Gemini 3.1 Pro は Dynamic Route 定義と同じ Google AI Studio provider へ直接接続します。

Sisyphus-Junior は意図的に固定モデルを設定しません。category-routed task では、選択された category のモデルを引き継がせます。

## 3. 知能カテゴリーとエージェント (10 Specialists)

Sisyphus（監督）は、タスクの性質に応じて最適な「知能カテゴリー」を選択し、専門エージェントを指揮します。

### 知能カテゴリー一覧 (Core Categories)

| Category | Primary / Variant |
| :--- | :--- |
| `ultrabrain` | Plus Sol (`max`) |
| `deep` | Plus Sol (`high`) |
| `quick` | Plus Luna (`low`) |
| `visual-engineering` | Gemini 3.1 Pro (`high`) |
| `unspecified-high` | Plus Luna (`max`) |
| `unspecified-low` | Plus Luna (`medium`) |
| `writing` | Ollama K2.7 (未指定) |
| `artistry` | Ollama K2.7 (未指定) |

### Justice / Superpowers カテゴリー

レビュー必須の作業や実装工程では、次の専用カテゴリーを使用します。Work は Bedrock 内で fallback し、Personal は各カテゴリーに定義した provider chain を使用します。

| カテゴリー | 用途 | Work (Bedrock) |
| :--- | :--- | :--- |
| **sp-mechanical** | rename、typo、設定変更などの定型作業 | Haiku 4.5 → Sonnet 5.5 |
| **sp-implementation** | 通常の TDD 実装 | Sonnet 5.5 → Opus 5.5 (high) |
| **sp-integration** | 複数module、API、state、concurrency の統合作業 | Sonnet 5.5 → Opus 5.5 (max) |
| **sp-deep** | 調査・深い推論 | Opus 5.5 (max) → Sonnet 5.5 |
| **sp-architecture** | アーキテクチャ設計・高影響判断 | Opus 5.5 (max) → Sonnet 5.5 |
| **sp-review** | Task 単位の必須レビュー | Sonnet 5.5 → Opus 5.5 (high) |
| **sp-final-review** | Plan / branch 全体の必須最終レビュー | Opus 5.5 (max) → Sonnet 5.5 |

### エージェント一覧とカテゴリー・マッピング

OmO公式のモデル適性を優先。Kimi K2.7は現行ProviderにVariant定義がないため、未指定を維持する。

| Agent | Primary / Variant | Fallback / Variant（順序） |
| :--- | :--- | :--- |
| `sisyphus` | Ollama K2.7 (未指定) | Sakura K2.7 (未指定) → Go K2.7 (未指定) |
| `hephaestus` | Plus Sol (`high`) | OCTG Sol (`high`) |
| `oracle` | Plus Sol (`xhigh`) | Gemini 3.1 Pro (`high`) |
| `librarian` | Plus Luna (`low`) | Ollama DeepSeek Flash (`low`) |
| `explore` | Plus Luna (`low`) | Ollama DeepSeek Flash (`low`) |
| `multimodal-looker` | Plus Sol (`low`) | Gemini 3.1 Pro (`high`) |
| `justice-review-controller` | Plus Sol (`high`) | なし |
| `justice-review-worker` | Plus Sol (`high`) | なし |
| `prometheus` | Ollama K2.7 (未指定) | Go K2.7 (未指定) |
| `metis` | Go K2.7 (未指定) | Ollama K2.7 (未指定) |
| `momus` | OCTG Terra (`high`) | Plus Sol (`xhigh`) |
| `atlas` | Ollama K2.7 (未指定) | Sakura K2.7 (未指定) → Go K2.7 (未指定) |

SisyphusのultraworkはPlus Sol/high、Sisyphus-JuniorはCategory継承。Justice command pinはPlus Solのまま固定。

### モデルカタログ運用（2026-10-19）

- **Go / Console Free を分離**: `opencode-go/<id>` は Go の契約内モデル、`opencode/<id>` は Console の別枠（従量課金モデルと期間限定 Free）。同名モデルもAPI/契約は別。
- **Go の候補**: Kimi K2.7 / K3、GLM-5.3 Flash、DeepSeek V4.1 Flash。LongCat 2.5 Preview Free、MiniMax M3.1 Flash Free、Beam Free は期間限定の手動選択候補としてのみ登録。
- **Console Free の候補**: GLM-5.3 Flash Free、DeepSeek V4.1 Flash Free、MiniMax M3.1 Flash Free、LongCat 2.5 Preview Free。2026-10-19 時点の公式情報で無料・ゼロ保持・学習不使用のモデルだけを登録。自動ルーティングには入れない。
- **監視のみ**: MiMo / Nemotron / stealth Free 等はデータ利用条件の相違から利用カタログに追加しない。
- **退避・廃止**: CommandCode GOAT はモデルカタログを維持し、利用枠回復まで自動ルーティングからのみ退避。未使用の AIHubMix / ZenMax / TokenRouter / NVIDIA Custom / OpenRouter Free の定義を削除。Dynamic Routing は無効のまま維持し、未検証の Free Route を除去。
- **請求上の注意**: `Free` というモデル名やホワイトリストだけで無料継続・課金 fail-closed は保証されない。Console の自動チャージ、Go の Extra usage は別途確認して無効化する。
- **ログと境界**: `cf-aig-collect-log-payload: "true"` と Work profile は維持。PersonalのAgent/Categoryのみ後続PRで変更する。

公式: [OpenCode Console Models](https://dev.opencode.ai/v2/docs/console/models) / [OpenCode Go](https://dev.opencode.ai/v2/docs/console/go)

## 4. LLMモデル選択のベストプラクティス

エージェントの能力を最大限に引き出すためには、エージェントの思考スタイルに合った「脳（モデルファミリー）」を割り当てることが重要です。

### 思考スタイルとモデルの相性

| スタイル | 特徴 | 適合モデル | 最適なエージェント |
| :--- | :--- | :--- | :--- |
| **メカニクス駆動** | **指示追従型。** 長大で複雑な手順、多段のTodo管理に極めて強い。 | Kimi Family, Claude Family | Sisyphus, Atlas, Metis |
| **原則駆動** | **自律探索型。** 最小限の指示で自律的に解決策を見出す。深い実装に強い。 | GPT Family (Sol, Terra, Luna), GLM Family | Hephaestus, Oracle, Momus |
| **視覚推論型** | **UI・構造理解。** デザイン解析、CSS、レイアウトの理解に特化。 | Gemini Family | Looker |

### カテゴリー別・モデルルーティング一覧

各行はPrimaryを含めて完全修飾の実モデルIDを `omo.jsonc` に保持する。ここでは Providerと推論強度を簡略表示する。

| Category | Primary / Variant | Fallback / Variant（順序） |
| :--- | :--- | :--- |
| `sp-mechanical` | Plus Luna (`low`) | Ollama DeepSeek Flash (`low`) |
| `sp-implementation` | Plus Luna (`max`) | Ollama GLM Flash (`high`) → Plus Sol (`high`) → Go GLM Flash (`high`) |
| `sp-integration` | Plus Luna (`max`) | Ollama GLM Flash (`high`) → Plus Sol (`high`) → Go GLM Flash (`high`) |
| `sp-deep` | OCTG Terra (`high`) | Plus Sol (`high`) |
| `sp-architecture` | Plus Luna (`max`) | Plus Sol (`max`) → OCTG Terra (`high`) |
| `sp-review` | Ollama DeepSeek Flash (`max`) | Plus Sol (`high`) → Go DeepSeek Flash (`max`) |
| `sp-final-review` | Plus Sol (`max`) | なし（障害時停止） |
| `ultrabrain` | Plus Sol (`max`) | OCTG Terra (`high`) |
| `deep` | Plus Sol (`high`) | OCTG Terra (`high`) |
| `quick` | Plus Luna (`low`) | Ollama DeepSeek Flash (`low`) |
| `writing` | Ollama K2.7 (未指定) | Sakura K2.7 (未指定) → Go K2.7 (未指定) |
| `unspecified-low` | Plus Luna (`medium`) | Ollama DeepSeek Flash (`low`) |
| `unspecified-high` | Plus Luna (`max`) | Ollama K2.7 (未指定) → Plus Sol (`high`) → Go K2.7 (未指定) |
| `visual-engineering` | Gemini 3.1 Pro (`high`) | Ollama K2.7 (未指定) → Plus Luna (`max`) |
| `artistry` | Ollama K2.7 (未指定) | Sakura K2.7 (未指定) → Gemini 3.1 Pro (`high`) |

`fallback_models = models[1:]` を15カテゴリーすべてで維持する。Workは従来どおりBedrock-only。

Work では Claude Fable 5.1 をモデルカタログに登録し、Claude Opus 5.5 を最上位推論・レビュー、Claude Sonnet 5.5 を主力実装、Claude Haiku 4.5 を高速な軽量作業に割り当てています。Fable はカタログ登録のみで、既定の agent / category routing には使いません。Work profile の agent・category・fallback はすべて Bedrock の Claude モデルを使用します。

| Work モデル | Bedrock model ID | 主な用途 |
| :--- | :--- | :--- |
| Claude Fable 5.1 | `amazon-bedrock/global.anthropic.claude-fable-5-1` | カタログ登録（明示選択用） |
| Claude Opus 5.5 | `amazon-bedrock/global.anthropic.claude-opus-5-5` | 最上位推論・高度レビュー |
| Claude Sonnet 5.5 | `amazon-bedrock/global.anthropic.claude-sonnet-5-5` | 主力実装・汎用作業 |
| Claude Haiku 4.5 | `amazon-bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0` | 高速検索・軽量作業 |

### Work Fallback の明示的なBedrock-only制約

OmO v4.19.4のruntime fallbackは、`models` だけでなく `fallback_models` の明示指定が必要な実行経路を含む。Workの8カテゴリー（`ultrabrain`、`deep`、`quick`、`writing`、`unspecified-low`、`unspecified-high`、`visual-engineering`、`artistry`）について `fallback_models = models[1:]` を補完する。これにより全15カテゴリーで **Bedrock-only** の順序を固定する。personalへのProvider越境を許さない。

PR #158ではモデル選択・Primary・Fallback順序を変更していない。実運用上の429認識・Fallback逆行・Goの `x-opencode-session` 伝播は独立に検証する。ログ保持、GOAT一時退避、GLM-5.3 full手動運用、Console Free手動運用、Justice mandatory reviewのPinは維持する。

参考: https://github.com/code-yeongyu/oh-my-openagent/issues/6868 / https://dev.opencode.ai/v2/docs/console/go

### PersonalのProvider利用枠方針（2026-10-20）

- **ChatGPT Plus**: Luna/maxを高頻度の実装・統合・アーキテクチャ・高度汎用に使用。SolはHephaestus/Oracle/高度推論/最終レビュー/Justice。リセット・Banked Resetは将来の増枠保証ではない。
- **Ollama（週次）**: Kimi K2.7をSisyphus/Prometheus/Atlas/writing/artistry、DeepSeek/maxをsp-review、GLMを実装Fallback。
- **OpenCode Go・CommandCode（月次）**: GoはMetisの低頻度・高価値用途と最終Fallback。GOATはカタログを維持し、現時点で自動経路は停止。
- **OCTG STANDARD（少量・共有）**: Astra/Sol/LunaのPrimary使用はゼロ。Hephaestusの緊急FallbackのみOCTG Sol/high。
- **OCTG MINI**: Terra/highはMomusとsp-deepのPrimary。高難度タスクのFallbackにも使用。
- **Justice**: sp-final-reviewはPlus Sol/maxのみ。レビュー失敗時は自動降格せずGateを停止する（実際のGate動作は別途実行検証）。
- **ログと課金**: CloudflareのPayload Loggingを維持。並列制限だけでは料金・quotaのfail-closedを保証しない。


### Open model の役割

| モデル | 主な役割 |
| :--- | :--- |
| **Kimi K2.7 Code** | Sisyphus / Prometheus / Metis / Atlas の主力オーケストレーション。Ollama / Go / Sakura に分散（GOAT除外）。 |
| **Kimi K3** | premium orchestration reserve。Ollama Legacyで明示利用（自動chainには置かない）。 |
| **GLM-5.3 Flash** | Luna/maxによる実装・統合のFallback。週次Ollamaを月次Goより優先。 |
| **GLM-5.3 full** | **手動指定のみ**。料金・quota効率の悪化を避け、agent/categoryのPrimaryとFallbackには配置しない。カタログ `glm-53` は維持。 |
| **DeepSeek V4.1 Flash** | sp-reviewはOllama/max主力。それ以外はLunaからのFallback。 |
| **GLM-5.2** | GOAT側モデル定義は維持。自動ルーティングから除外し、必要時に手動選択。 |

GLM-5.3 fullを明示する場合は、OmO v4.19.4 のalias解決不整合を避けて `cloudflare-ai-gateway-custom/custom-ollama-cloud/glm-5.3` を直接指定します。
Dynamic Routing が復旧したら、provider fallback は `cf-ai-gw-dynamic-routing` へ戻し、OmO は再び logical model 選択だけを担当させます。

---
*Updated: 2026-10-20 (Personal agent/category routing, Plus Luna/max 主力化)*

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
