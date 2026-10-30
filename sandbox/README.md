# OpenCode Sandbox runtime — 設定雛形

> **Status: DESIGN_ONLY / TEMPLATE_ONLY**
>
> このディレクトリは Docker Sandboxes 上の OpenCode 実行構成を検討するための雛形です。
> 現段階では、デプロイ・設定同期・ネットワーク許可・認証情報転送を実行しません。
> `sbxenv.yaml` や Docker / OpenCode の公式設定スキーマを模倣したものではありません。

## 目的と責務

- **Host（正本）**: `dotfiles-ai` の設定SSOT、個別のGitリポジトリ、レビュー済み成果物を保持する。
- **Sandbox（実行）**: OpenCode、Plugin、シェル、テスト、ビルド、AIによる変更を実行する。
- **転送境界**: ホストの設定・ソースは必要なものだけ選別して投入し、変更は差分をレビューしてからホストへ採用する。
- **非対象**: ホスト上の OpenCode v1 を置換すること、`dotfiles-core` のセットアップ手順を置換すること。

既存の `apm.yml` はモデル・MCP・OpenCode設定のSSOTです。`opencode/opencode.jsonc` とリポジトリ直下の `opencode.json` は生成物なので編集しないでください。Sandbox向けの設定を作る将来のアダプターは、SSOTから**許可した設定だけ**を抽出します。既存の `make setup`、`make sync-opencode`、`make sync-mcp` に暗黙接続しません。

## 雛形の内容

| ファイル | 役割 |
| --- | --- |
| `profiles/opencode-v2.1.4.example.yaml` | OpenCode v2.1.4の実行プロファイル候補（独自メタデータ） |
| `config/config-selection.example.yaml` | ホストSSOTからSandboxへ渡す候補の宣言。既定は全拒否 |
| `policy/network.example.yaml` | ネットワーク許可候補。既定は全拒否 |
| `opencode-v2/opencode.jsonc.example` | Sandbox用Server設定の最小サンプル |
| `opencode-v2/cli.json.example` | Sandbox用TUI設定の最小サンプル |

これらは**雛形**であり、ファイルを配置しただけで適用されるものではありません。YAMLを解釈・強制するプログラムもまだありません。

## 既存の実験結果（参考）

`oc-v2-poc` はホストの作業ディレクトリをマウントしないDocker Sandboxで作成しました。
OpenCode v2.1.4で、`akane@3.0.0-alpha.2` のServer Plugin初期化と、`sibyl@3.0.0-alpha.1` のTUI Plugin初期化・Sidebar表示・終了処理を検証しました。
**検証用ラッパー経由**での結果であり、通常インストール経路、Subagent実活動、全監視機能、別のSandboxの安全性まで保証するものではありません。

## 配備・運用に際して固定する原則

1. `~/.config/opencode`、`~/.local/share/opencode`、`~/.ssh`、`.env`、APIキー、クラウド認証ファイルを**丸ごと渡さない**。
2. `apm.yml` のMCPにはホストコマンドや権限付き外部接続が含まれ得る。Sandbox側のMCPを既定で無効にし、必要なものだけ別途レビューする。
3. ホストのリポジトリは正本。**Direct Mountによる書込み共有を既定にしない**。まずは検証済みの `sbx cp` によるコピー入出力を使用する。
4. Clone Modeは将来の候補。Git正本との同期方式・秘密情報・未コミット変更の扱いを検証してから採用する。
5. 通信はDefault Deny。許可は宛先・時間・目的を限定し、作業後は明示的に撤回する。YAML上のルールは`sbx policy`を自動変更しない。
6. `sbx-poc` と `y_ohi` の権限境界を維持する。共有のためにホームディレクトリの権限を緩めない。
7. エージェントの操作権限だけでなく、許可されたホストデータの読み取り・持ち出しもリスクとして扱う。Sandboxは万能な境界ではない。

## 次の実装候補（未実装）

- ホスト上で動く、allowlist形式の設定エクスポーター（シークレット検査・シンボリックリンク拒否・チェックサム付き）。
- `sbx cp`による構成投入と、Sandbox内での読み込み・検証。
- `akane`（Server）と`sibyl`（TUI）の通常登録経路の検証。
- Git差分、テスト証拠、ビルド成果物の回収とホストでの明示的採用。
- 再作成時の復元、通信許可撤回、ホスト非変更の検証。

**既存の dotfiles-ai の生成・同期ターゲットを変更する前に、上記を別途実装・レビューしてください。**
