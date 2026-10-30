# OpenCode Sandbox runtime — 設定と開発環境

> **Status: EXPORTER_POC / NO_DEPLOYMENT**
>
> このディレクトリは、ホスト管理・Sandbox実行に向けた設定雛形と、読み取り主体の限定的な設定エクスポーターです。
> Docker Sandboxの作成、`sbx policy`変更、ホストOpenCode v1の更新、認証情報の転送は行いません。
> `sandbox/` 配下のYAMLは、Docker Sandboxes公式スキーマではなく独自の設計用メタデータです。

## 責務と正本

- **Host**: `dotfiles-ai` の `apm.yml` を設定SSOTとし、プロジェクトのGitリポジトリを正本として保持する。
- **Sandbox**: OpenCode v2.1.4 / Plugin / shell / ビルドとテストを実行する。ホストGitの作業ツリーは直接書き換えない。
- **受渡し**: 選別済み設定とレビュー済みソースのみを渡し、変更結果はホストでレビュー後に明示的に採用する。

既存の `make setup`、`make sync-opencode`、`make sync-mcp` には接続しません。
`opencode/opencode.jsonc` とルート`opencode.json`は生成物なので編集しません。

## スタック構成

1. `feature/sandbox-runtime-scaffold-20261030` — 設定テンプレート・原則
2. `feature/sandbox-config-exporter-20261030` — エクスポーター・単体テスト（このブランチ）

後続のブランチは前段ブランチのHEADから分岐します。masterへの反映は別途レビュー後とします。

## エクスポーター（限定実装）

`sandbox/scripts/prepare_opencode_v2.py` は `apm.yml` を読み取り、**固定の許可リスト**から`shell`（bash/sh/zsh）と`snapshot`（boolean）のみを選びます。それ以外の設定値は一切出力しません。

生成ファイル：

- `opencode.jsonc`: 2.1.4用の最小Server設定、`plugins: []`、`mcp: {}`
- `cli.json`: 最小TUI設定、`plugins: []`
- `export-manifest.json`: ソース・出力ファイルのSHA-256、OpenCode固定バージョン

**未実装:** Plugin登録、設定選別YAMLの動的解釈、MCP移植、Secrets Broker、Sandboxへのコピー、通常のPlugin登録や自律開発タスク。設定生成結果の実OpenCode v2での動作確認も未実施です。

外部の一時ディレクトリへ手動で出力する場合：

```sh
python3 -m pip show PyYAML  # 依存が既存環境にあることを確認（インストールしない）
python3 sandbox/scripts/prepare_opencode_v2.py --out /tmp/opencode-v2-export-20261030
python3 sandbox/scripts/prepare_opencode_v2.py --out /tmp/opencode-v2-export-20261030 --check
python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v
```

出力先がすでに存在する場合は上書きせず停止します。異なる出力先を指定してください。
このエクスポーターは標準出力へ設定内容や環境変数を表示しません。生成物は秘密情報を含めない設計ですが、必ず配備前にレビューしてください。

## 雛形ファイル（自動適用されない）

| ファイル | 役割 |
| --- | --- |
| `profiles/opencode-v2.1.4.example.yaml` | 実行環境とPluginバージョンの設計候補 |
| `config/config-selection.example.yaml` | 将来の設定ファイル選別案（現状未接続） |
| `policy/network.example.yaml` | ネットワークDefault Denyの意図表明（現状未接続） |
| `opencode-v2/opencode.jsonc.example` | Serverの最小例 |
| `opencode-v2/cli.json.example` | TUIの最小例 |

## 実証済み範囲と制限

既存PoCの`oc-v2-poc`では、ホストWorkspaceをマウントせずにOpenCode v2.1.4を稼働させました。
`akane@3.0.0-alpha.2`（Server）と`sibyl@3.0.0-alpha.1`（TUI）を**検証用ラッパー経由**で同時に初期化し、Sidebar表示とTUI cleanupまで確認しました。
通常のパッケージ登録、監視の全機能、Subagentの実活動、ホストへの差分回収は未確認です。

## 固定する境界

1. ホストの設定・ソースを正本とし、Direct Mountの書込共有を既定にしない。まず`sbx cp`による明示的な受渡しを使う。
2. `~/.ssh`、`.env`、OpenCode認証情報、MCP実行コマンド、パーソナルトークンを丸ごとSandboxへ渡さない。
3. `apm.yml`が管理する高権限MCPやProvider定義をSandbox設定へ自動移植しない。必要なものは個別に検討する。
4. 通信はDefault Deny。許可が必要な場合は目的別に承認し、終了後に撤回する。YAMLは`sbx policy`を変更しない。
5. `sbx-poc`と`y_ohi`の権限境界を維持する。ホームディレクトリのパーミッションを広げない。
6. Sandboxが万能な隔離境界であるとは主張しない。Sandboxへ渡したデータの機密性も検討する。

次の実装候補は、エクスポート結果のSandboxへの安全な配備と、v2の通常Plugin登録経路の検証です。**既存のdotfiles-aiの生成・同期ターゲットは今回変更しません。**
