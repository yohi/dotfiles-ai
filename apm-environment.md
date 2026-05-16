# Microsoft APMによるAIエージェント設定の一元管理：不均質環境における環境変数の設計とガバナンスの最適化

AIエージェントの自律性が高まる中、開発環境における「コンテキストの断片化」が深刻な課題として浮上している。GitHub Copilot、Claude Code、OpenCode、Gemini CLIといった多様なランタイムが普及する一方で、それぞれの設定方法や環境変数の管理ルールが異なるため、プロジェクト間でのポータビリティ（移植性）や、組織的なガバナンスの維持が困難になりつつある。この課題に対し、Microsoftが提唱するAgent Package Manager（APM）は、言語に依存しない依存関係管理モデルを採用し、AIプリミティブ（スキル、プロンプト、エージェント、MCPサーバー）を統合的にデプロイするための基盤を提供する 1。

本報告書では、APMを中心としたAIエージェント環境の構築において、主要なランタイム（Claude Code, Codex, GeminiCLI, OpenCode, CursorCLI, Antigravity）における環境変数の設定・管理方法のベストプラクティスを詳述する。単なる技術的な設定に留まらず、秘匿情報の管理、OSキーチェーンとの連携、CI/CDパイプラインにおける自動化、そして「.agents/skills」ディレクトリを通じたクロスプラットフォームな標準化といった、実戦的な運用戦略を提示する 3。

---

## 1. Microsoft APM：AIコンテキストのハブとしての役割と環境変数の抽象化

Microsoft APMは、AIエージェントのコンテキスト設定を再現可能な「パッケージ」として管理するツールであり、Terraformやnpmに似たアーキテクチャを持つ 1。APMの核となる概念は、依存関係を宣言する `apm.yml` と、解決された依存関係のグラフを固定する `apm.lock.yaml` である 1。

### APMにおける環境変数の取り扱いと安全な注入メカニズム

APMは、AIエージェントの設定ファイル（特にMCPサーバーやプロンプトテンプレート）に秘密情報を直接ハードコードすることを厳格に禁止する「Secure-by-default」の姿勢を貫いている 4。APMが提供する環境変数の管理における最大の利点は、ターゲットとなるランタイムごとに異なる環境変数のシンタックスを自動的に翻訳し、デプロイする機能にある 4。

| APM機能 | 概要 | 具体的な効果 |
| :--- | :--- | :--- |
| プレースホルダー置換 | `${env:VAR}` や `${VAR}` 形式の変数を検知 4 | ターゲット（Copilot, Claude等）のネイティブな環境変数形式に変換してデプロイ 4 |
| ターゲット検知 | `--target <harness>` による柔軟な出力制御 7 | 複数のエージェント環境（`.claude`, `.github`, `.cursor`等）に対し、一括で環境設定を同期 8 |
| 認証リゾルバー | `AuthResolver` による認証情報の集約管理 4 | `GITHUB_APM_PAT` 等の環境変数を用い、ホストや組織ごとに安全にトークンを解決 4 |
| ドリフト検知 | `apm audit` による整合性チェック 4 | 手動での環境変数変更や設定の上書きを検知し、セキュリティの空白期間を排除 4 |

APMはインストール時に `${env:VAR}` と記述された設定を読み取ると、それをデプロイ先のランタイムが解釈可能な形式（例：GitHub Copilotなら `${VAR}`）に変換し、ディスク上には秘密情報を書き込まないように設計されている 4。これにより、秘密情報のローテーションが発生した際も、シェル環境やキーチェーンを更新するだけで、設定ファイルを再生成することなく即座に反映が可能となる。

### 認証フローとプロトコル選択のベストプラクティス

APMを通じた一元管理において、パッケージのダウンロードや検証に使用する認証プロトコルの選択は極めて重要である 4。

* **Gitプロトコルの統一**: `APM_GIT_PROTOCOL` 環境変数を使用することで、組織内のすべてのエージェントパッケージに対してSSHまたはHTTPSのどちらを優先するかを指定できる 7。
* **企業内リサーチとSSOの統合**: エンタープライズ環境（GitHub Enterprise, ADO等）では、`GITHUB_TOKEN` や `GH_TOKEN` を適切にエクスポートすることで、APMがそれらを自動的にリゾルバーに統合し、プライベートリポジトリへのアクセスをシームレスに行う 4。
* **認証タイムアウトの調整**: 外部の認証ピッカー（WindowsのCredential Manager等）を使用する場合、`APM_GIT_GIT_CREDENTIAL_TIMEOUT` を調整することで、複雑な認証フローでのエラーを回避できる（最大180秒まで設定可能） 4。

---

## 2. Claude Code：多層的な優先順位とプロジェクトの隔離

AnthropicのClaude Codeは、環境変数をモデルの挙動、認証、およびセキュリティポリシーの制御に広範に利用している 9。Claude CodeをAPMで管理する際の核心は、その「多層的な優先順位モデル」の理解と、プロジェクトレベルでの設定の隔離にある。

### 環境変数の読み込み順序と優先順位

Claude Codeは以下の6つのソースから環境変数を読み込み、下に行くほど優先順位が高くなる構造を持つ 10。

| 順位 | ソース | 適用範囲 | 備考 |
| :---: | :--- | :--- | :--- |
| 1 | システム環境 | `/etc/environment` | 管理者によるマシン全体のデフォルト 10 |
| 2 | ユーザーシェルRC | `~/.zshrc, ~/.bashrc` | 個人ユーザーの永続的な設定 10 |
| 3 | セッションエクスポート | 現在のターミナルセッション | ワンショットでの挙動変更 10 |
| 4 | プロジェクト内 .env | カレントディレクトリ | APM管理における推奨場所（`.gitignore`必須） 10 |
| 5 | VS Code設定 | `claudeCode.environmentVariables` | エディタ経由での注入 10 |
| 6 | ローカルプロジェクト設定 | `.claude/settings.local.json` | プロジェクト内の個人設定（Git管理外） 11 |

この構造において、APMは `settings.json`（共有設定）や `CLAUDE.md`（プロジェクトの指示書）を管理し、実際の `ANTHROPIC_API_KEY` などの機密情報はプロジェクト内の `.env` またはシェルレベルで保持するのがベストプラクティスである 11。

### 主要な環境変数とその運用上の意義

Claude Codeの運用において制御すべき変数は多岐にわたる。これらはAPMの `apm-policy.yml` と組み合わせることで、組織レベルでの制約を課すことが可能である 1。

* **認証と接続**: `ANTHROPIC_API_KEY` は最も重要な変数であり、設定されている場合はサブスクリプションよりも優先される 9。また、プロキシ環境下では `ANTHROPIC_BASE_URL` や `ANTHROPIC_AUTH_TOKEN` を使用して、カスタムゲートウェイを介した接続が可能となる 10。
* **挙動の制約**: `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` を設定することで、テレメトリ情報の送信を抑制できる。これは機密性の高いプロジェクトにおいて必須の設定とされる 12。
* **コンテキスト管理**: `BASH_MAX_OUTPUT_LENGTH` は、エージェントが一度に読み取れるターミナル出力の長さを制御する。デフォルトは10,000文字だが、冗長なログが出力されるビルドプロセスなどでは50,000文字程度に引き上げることが推奨される 10。
* **サブエージェントの制御**: `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` を設定すると、非対話モードにおいて組み込みの探索・計画用サブエージェントを無効化し、特定のタスクに集中させることができる 9。

### プロジェクトの物理的な隔離

`CLAUDE_CONFIG_DIR` 環境変数を使用することで、デフォルトの `~/.claude` ではなく、プロジェクト専用のディレクトリ（例：`$(pwd)/.claude-config`）に設定、キャッシュ、セッション履歴を保存させることができる 10。APMで複数のAIプロジェクトを並行して管理する場合、この変数を利用してプロジェクト間の干渉を完全に防ぐことが、再現性の確保に繋がる。

---

## 3. OpenAI Codex CLI：プロファイル駆動の設定と環境の保存

OpenAIのCodex CLIは、`config.toml` という設定ファイルを軸に据えつつ、特定の環境変数をトリガーにして挙動を変化させる。Codexにおけるベストプラクティスは、名前付き「プロファイル」の活用と、サブプロセスへの環境変数の伝搬制御にある 15。

### 設定ファイルの階層と発見プロセス

Codexは、カレントディレクトリから遡って `.git` ディレクトリ（プロジェクトルート）に到達するまで `config.toml` を探索する 15。

* **ユーザーレベル**: `~/.codex/config.toml` に、モデルのデフォルト（例：gpt-4.5）や承認ポリシーを記述する 15。
* **プロジェクトレベル**: `.codex/config.toml` に、そのプロジェクト独自のMCPサーバー設定やスキルを記述する 15。
* **信頼モデル**: セキュリティ上の理由から、プロジェクト固有の設定は「信頼済みプロジェクト」としてマークされていない限り読み込まれない。この「信頼状態」自体も環境ごとに管理する必要がある 15。

### 環境変数の伝搬制御： shell_environment_policy

Codexがコマンドを生成して実行（`codex exec`）する際、どの環境変数を子プロセスに引き継ぐかは `[shell_environment_policy]` セクションで定義される 15。

```toml
[shell_environment_policy]
include_only =
```

デフォルトではセキュリティ保護のため、親プロセスの環境変数は限定的にしか引き継がれない 15。しかし、特定のビルドツールやプライベートリポジトリへのアクセスに必要なトークンがある場合、ここに明示的に追加する必要がある。APMを使用してCodex環境をデプロイする場合、このポリシー設定を `apm.yml` の中で一元定義し、デプロイ時にターゲットに合わせて展開するのが効率的である。

### 「env_clear」問題とその回避策

特定の言語環境（特にRuby on Railsなど）において、CodexがMCPサーバーを起動する前に `env_clear()` を実行してしまう場合があり、これにより必要な環境変数（`PATH`, `GEM_HOME` 等）が消失し、サーバーが起動しない事態が発生する 17。

この問題に対するベストプラクティスは、環境変数のスナップショットを `config.toml` に直接埋め込むことである 17。

```toml
[mcp_servers.rails-ai-context.env]
PATH = "/usr/local/bin:/usr/bin"
GEM_HOME = "/home/user/.gems"
```

APMのコンパイル機能を利用すれば、開発者の現在のシェル環境からこれらのパスを抽出し、動的に `config.toml` を生成することができるため、手動での書き換えを最小限に抑えられる。

---

## 4. Gemini CLI：エンタープライズ認証とIDEの動的同期

GoogleのGemini CLIは、Google Cloud Platform（GCP）との親和性が非常に高く、特にエンタープライズ用途での認証管理に長けている 18。環境変数の管理においては、Application Default Credentials（ADC）の扱いが中心となる。

### 認証方法の選択と環境変数

Gemini CLIでは、利用シーンに応じて以下の3つの認証経路から環境変数を選択する 18。

* `GEMINI_API_KEY`: AI Studioのキーを使用する。個人開発やプロトタイピングに最適 18。
* `GOOGLE_APPLICATION_CREDENTIALS`: Vertex AIを組織で使用する場合。サービスアカウントのJSONキーへのパスを指定する 18。
* `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_PROJECT_ID`: 使用するGCPプロジェクトを特定する。Gemini CLIはまず `PROJECT` を確認し、次に `PROJECT_ID` を確認する 18。

### IDEとの環境同期： GEMINI_CLI_IDE_PID

Gemini CLIのユニークな機能に、実行中のIDE（VS CodeやAntigravity等）との動的な同期がある 21。

* **自動検知**: 通常、IDEの統合ターミナルで実行されると自動的に環境を検知する 21。
* **手動紐付け**: 外部ターミナルから特定のIDEインスタンスにコンテキスト（開いているファイルやカーソル位置）を同期させたい場合、`GEMINI_CLI_IDE_PID` にIDEのプロセスIDを設定する 21。

この機能は、APMで複数の開発ワークスペースを管理している際、どのプロジェクトのコンテキストを優先するかを環境変数一本で制御できるため、マルチタスク環境において極めて強力である。

### サンドボックスとセキュリティ制御

Gemini CLIは `GEMINI_SANDBOX` 変数によって、生成されたコードの実行をサンドボックス内で行うかどうかを制御できる 20。APMのガバナンスポリシーと連携させ、「特定のブランチやリポジトリでは必ず `GEMINI_SANDBOX=true` を強制する」といった運用が、安全なエージェント利用の鍵となる。

---

## 5. OpenCode：認証と挙動の分離という「黄金律」

OpenCodeは、TUI（Terminal User Interface）を備えたオープンソースのAIエージェントであり、その設定思想は「共有可能な挙動」と「局所的な秘密情報」の徹底的な分離にある 13。

### 設定の優先順位とマージルール

OpenCodeは以下の順序で設定をマージする 22。

| 順位 | 設定ソース | 用途 |
| :---: | :--- | :--- |
| 1 | 組織デフォルト | `.well-known/opencode` から自動取得 22 |
| 2 | グローバル設定 | `~/.config/opencode/opencode.json` 22 |
| 3 | カスタムパス | `OPENCODE_CONFIG` 環境変数で指定 22 |
| 4 | プロジェクト設定 | リポジトリルートの `opencode.json` 22 |
| 5 | インライン設定 | `OPENCODE_CONFIG_CONTENT` 環境変数 22 |

### 「黄金律」の実践

OpenCodeコミュニティにおける環境変数管理のベストプラクティスは、以下の通りである 13。

* **Gitにコミットするもの**: `opencode.json`。ここには `model`（例：claude-3-5-sonnet）や `permissions`（例：`bash: ask`, `edit: allow`）といった、チーム全員が共通で使うべきルールを記述する 13。
* **Gitにコミットしないもの**: `.env`。ここには `ANTHROPIC_API_KEY` などの、billingや個人のIDに紐づく鍵を記述する 13。

APMを使用してOpenCodeプロジェクトを初期化する際、`apm init` コマンドは自動的に `.env` を `.gitignore` に追加し、機密情報の漏洩を未然に防ぐテンプレートを提供することが期待される。

### 組織的なガバナンスとMDM連携

OpenCodeは、macOSの「Managed Preferences」（MDM経由の `.mobileconfig`）を最高優先度の設定として読み込むことができる 22。企業環境において、特定の環境変数をユーザーが変更できないように強制する場合、このMDM連携が最終的な防御線となる。

---

## 6. Cursor CLI：IDEコンテキストと環境変数の橋渡し

Cursor CLI（`cursor-agent`）は、Cursorエディタの機能をターミナルから制御するためのツールであり、エディタ内で設定された「Project Rules」や「MCPサーバー」の情報を環境変数と組み合わせて利用する 24。

### MCPサーバーにおける環境変数注入

CursorのMCP設定（`.cursor/mcp.json`）では、各サーバーの起動に必要な環境変数を定義できる 24。

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

APMはこの `mcp.json` を生成する際、トークン部分を `${env:GITHUB_PAT}` のようなプレースホルダーとして書き出す。Cursorエディタ自体は環境変数の展開をサポートしていない場合があるが、APMを介してデプロイすることで、インストーラがローカルの環境変数から値を安全に注入した状態でファイルを生成、あるいはシェル環境から動的に読み込むラッパーを介在させることが可能になる 4。

### 認証トークンの管理： CURSOR_API_KEY

自動化されたタスクやリモート開発環境においてCursor CLIを使用する場合、`CURSOR_API_KEY` 環境変数を設定することで、対話的なログインをスキップして認証を完了できる 25。これは、後述するAPMのCI/CD連携において、ビルドプロセスの一環としてCursorにコード修正を行わせる際に必須となる。

---

## 7. Antigravity：エージェント第一主義のプラットフォーム環境

GoogleのAntigravityは、AIを「オートコンプリートツール」ではなく「自律的なエージェント」として扱う統合開発環境である 26。その環境管理は、複雑なタスクを実行するための「ミッションコントロール」として機能する 19。

### MCPストアと認証の統合管理

Antigravityのエージェントパネルにある「MCP Store」は、外部サービス（Neon, Supabase, Notion等）との接続を管理する 27。ここでの環境変数の扱いは高度に抽象化されている。

* **Google ADC (Application Default Credentials)**: `authProviderType: "google_credentials"` を設定することで、`gcloud auth application-default login` で取得したローカルの資格情報をそのままエージェントに利用させることができる 27。
* **OAuth 2.0**: AntigravityはサーバーとのOAuth連携を自動でハンドリングし、取得したアクセストークンを `~/.gemini/antigravity/mcp_oauth_tokens.json` に安全に保存する。ユーザーは環境変数を直接触ることなく、ブラウザ経由の認証だけでエージェントに高度な権限を与えられる 27。

### 秘密情報の注入： mcp_config.json

カスタムMCPサーバーを手動で設定する場合、`~/.gemini/antigravity/mcp_config.json` を直接編集する。この際、`env` オブジェクトに記述された変数は、エージェントがサーバープロセスを起動する際にのみメモリ上に展開される 27。

```json
{
  "mcpServers": {
    "my-secure-tool": {
      "command": "node",
      "args": ["server.js"],
      "env": {
        "SECRET_SERVICE_KEY": "sk-..."
      }
    }
  }
}
```

### Windows環境における特有の注意点

WindowsでAntigravityを使用する場合、ツールがLinuxスタイルの `$HOME` 環境変数を期待してクラッシュすることがある 29。これを回避するため、`HOME` 変数を `%USERPROFILE%` にマッピングする永続的な環境変数の設定が、Windowsユーザーにとってのベストプラクティスとなる 29。

---

## 8. APMによる統合：環境変数管理の共通戦略と高度な洞察

これまで見てきた各エージェントの特性を、Microsoft APMを用いてどのように一元管理すべきか。その具体的な戦略と、APMの機能アップデートから読み取れる将来的な展望を整理する。

### クロスプラットフォームなスキルディレクトリの標準化

APMの最新の動向の中で最も注目すべきは、`.agents/skills/` という共通ディレクトリの導入である 4。これまで、Copilotは `.github/skills/`、Claudeは `.claude/skills/` とバラバラだったデプロイ先を、`apm install --target agent-skills` を使用することで、すべての主要なエージェントが共通して参照できる単一の場所に集約できるようになった 4。

| ターゲット | 変換前パス | 変換後（APM 0.13.0+） | 共通環境変数 |
| :--- | :--- | :--- | :--- |
| Copilot | `.github/skills/` | `.agents/skills/` | `GITHUB_TOKEN` 4 |
| Claude | `.claude/skills/` | `.agents/skills/` | `ANTHROPIC_API_KEY` 5 |
| Cursor | `.cursor/` | `.agents/skills/` | `CURSOR_API_KEY` 5 |
| Codex | `.codex/` | `.agents/skills/` | `OPENAI_API_KEY` 5 |

この標準化により、環境変数の管理も「どのフォルダにどの変数を適用するか」という物理的な制約から解放され、「どのスキルがどの秘密情報を要求するか」という論理的な管理へと移行する。

### 機密情報管理の次世代モデル： secrets: ブロックの導入

現在、APMの開発ロードマップでは、`agent.yaml`（または `apm.yml`）内に `secrets:` ブロックを導入し、プラグgableなバックエンドをサポートする計画が進んでいる 32。

* **サポート予定のバックエンド**: OSキーチェーン、1Password CLI、HashiCorp Vault、AWS SSM 32。
* **意義**: これにより、開発者はローカルの `.env` ファイルへの依存を完全に断ち切ることができる。APMがOSのキーチェーンから直接秘密情報を取得し、メモリ上でのみエージェントに渡すようになるため、漏洩リスクが劇的に低減する。

### CI/CDにおける「ゼロ・コンフィグ」認証

GitHub ActionsなどのCI環境では、`microsoft/apm-action` を通じて環境変数を管理するのが最適である 33。

* **GITHUB_APM_PATの自動フォワード**: 同じ組織内のプライベートリポジトリであれば、GitHub Actionのデフォルトトークンが自動的にAPMの認証リゾルバーに渡されるため、追加の設定は不要である 4。
* **ドリフト検出の自動化**: CIのステップで `apm install --frozen` を実行することで、リポジトリ内の設定ファイルが環境変数やロックファイルと矛盾していないかを強制的にチェックし、セキュリティの穴を埋めることができる 6。

---

## 9. 結論：組織的なAIエージェント環境の構築に向けて

Microsoft APMを用いたAIエージェント設定の一元管理は、単なるツールの導入ではなく、ソフトウェア開発のライフサイクル全体に「エージェント・ガバナンス」を組み込む行為である。本報告書で詳述した環境変数のベストプラクティスを総括すると、以下の3つのレイヤーでの対策が求められる。

* **個人レイヤー**: OSキーチェーンやシェルRCを使い、秘密情報を永続化させつつ、対話的なセッションを維持する。
* **プロジェクトレイヤー**: `apm.yml` と `.env`（Git除外）を組み合わせ、挙動と資格情報を厳格に分離する。`${env:VAR}` 形式による抽象化を徹底し、特定のランタイムへの固執を避ける。
* **組織レイヤー**: `apm-policy.yml` によるソースの制限、およびCIにおける `apm audit` の実施。将来的な `secrets:` ブロックの導入を見据え、一元的なシークレットマネージャーへの移行準備を進める。

AIエージェントのランタイムが今後さらに多様化しても、環境変数という「共通の言語」をAPMという「翻訳機」で管理し続ける限り、開発者はツールに縛られることなく、本来の創造的な業務に集中することが可能となる。APMが提供する再現可能なコンテキストは、チーム開発における「AIの不確実性」を取り除くための、最も確実な基盤となる。

---

## 引用文献

* `[FEATURE] Renovate supporting apm.yml · Issue #639 · microsoft ...`
* `Microsoft APM: Agent Package Manager for reproducible agent context | explainx.ai Blog`
* `APM Usage - skills - GitHub`
* `apm/CHANGELOG.md at main · microsoft/apm · GitHub`
* `[FEATURE] Support .agents/skills as an apm install target for shared skill deployment · Issue #737 · microsoft/apm - GitHub`
* `apm install | Agent Package Manager - Microsoft Open Source`
* `apm install | Agent Package Manager - Microsoft Open Source`
* `apm/CONTRIBUTING.md at main · microsoft/apm - GitHub`
* `Environment variables - Claude Code Docs`
* `Claude Code environment variables: official docs (API_KEY, BASE_URL)`
* `Claude Code Quickstart Core Guide | Easy-Vibe Tutorial - GitHub Pages`
* `Claude Code Configuration - Documentation | Code By AI | Unified AI Coding Agents`
* `Sharing Team Configurations | CodeSignal Learn`
* `Claude Code Harness and Environment Engineering: Designing the Frontline Where Local AI Agents Actually Live | hidekazu-konishi.com`
* `Config basics – Codex | OpenAI Developers`
* `Advanced Configuration – Codex | OpenAI Developers`
* `MCP server for Rails apps that actually works with Codex CLI (solves the env_clear problem) - Reddit`
* `Gemini CLI authentication setup`
* `Getting started with Spec Driven Development in Antigravity - Google Codelabs`
* `Where Gemini CLI Stores Configuration Files - Inventive HQ`
* `IDE Integration | Gemini CLI`
* `Config | OpenCode`
* `Agents - OpenCode`
* `GitHub - Rodert/awesome-mcp: A curated list of MCP servers and related resources.`
* `Cursor CLI by Coder Labs | Coder Registry`
* `Getting Started with Google Antigravity`
* `Antigravity Editor: MCP Integration`
* `Postman's MCP Server Now Works With Google Antigravity IDE`
* `[Tip] Fix for Playwright "HOME environment variable is not set" on Windows`
* `Google pro subscription additional features : r/google_antigravity - Reddit`
* `AI coding agents - Sherlock`
* `Show HN: GitAgent – An open standard that turns any Git repo into an AI agent | Hacker News`
* `microsoft/apm-action: GitHub Action for Agent Package Manager`
