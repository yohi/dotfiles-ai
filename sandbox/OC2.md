# oc2 — HostからDocker Sandbox内のOpenCode v2.1.4を起動

**Status: FEATURE_BRANCH_IMPLEMENTED / OFFLINE_UNIT_TESTED / LIVE_OC2_NOT_YET_VERIFIED**

この初期実装は、既存P6の設定エクスポートを再利用して単一のHost側ランチャーに統合します。v1設定の完全移行ではありません。

## 起動

Host上でfeatureブランチのdotfiles-aiをチェックアウトし、初回だけPATHにbinを追加します。

~~~bash
export PATH="/path/to/dotfiles-ai/bin:$PATH"
oc2
~~~

- `oc2 --dry-run`: Sandbox操作・ファイル書込みなしで計画を表示
- `oc2 --prepare-only`: 設定・Sandbox・CLIを準備し、TUIは起動しない
- `oc2 --sandbox oc2-dev`: Sandbox名を指定する（既定値はoc2-dev）
- `oc2 --sbx-user sbx-poc`: sbx実行アカウントを指定
- `oc2 --seed-sandbox oc-v2-poc`: OpenCode v2.1.4導入済みの既存mountless PoCを読み取り専用のseedに使う
- `oc2 --seed-sandbox ""`: seedを使わない

ホスト側PythonにはPyYAMLが必要です（本リポジトリのpyproject.tomlで管理）。依存環境が未準備の場合は先に整備してください。

Host実行ユーザーがsbx-pocと異なる場合はsudoを介してsbxを呼び出します。sudo権限・パスワード入力が必要になる場合があります。sudoersは変更しません。

## 処理内容

1. `apm.yml`をSSOTとして、既存の`prepare_opencode_v2.py`で最小設定を出力。
2. `stage_opencode_v2.verify_bundle()`によるHash・内容検証。
3. `sbx ls`で既存Sandboxを確認。なければ`sbx create --name oc2-dev shell`でマウントなしSandboxを新規作成。既存SandboxはWorkspaceマウントがあれば停止。
4. 選別した設定とguest検証スクリプトだけを`sbx cp`でコピー。guest側でもHash・許可フィールドを検証。
5. 設定Hashごとに専用XDG領域を生成。同一Hashなら検証して再利用。既存成果物を無断上書きしない。
6. 固定OpenCode v2.1.4を確認。なければmountlessの`oc-v2-poc`からCLIのnode_modulesだけを読み取りコピーし、versionを再検証。
7. seedがない場合はSandbox内で`@opencode/cli@2.1.4`のnpmインストールを試行。**ネットワークポリシーは変更しない**ため、アクセスできなければ安全停止。
8. `sbx exec -it`と`opencode --standalone`でTUIを起動。共有バックグラウンドServerのポート競合を回避。

## 対象と除外

現行のエクスポーターが許可する設定は`shell`と`snapshot`だけです。Provider、OMO、Agents、Rules、Commands、Skills、Akane、Sibyl、MCP、認証情報は初期実装では自動移植しません。`plugins: []`、`mcp: {}`は出力スナップショットの内容であり、OpenCodeの他の設定ソースからの自動検出まで完全に無効化する保証ではありません。

SandboxへSSH Agent・API Key・トークン・Host OpenCode v1の設定全体・HostのGitリポジトリはコピーしません。Hostに書込みWorkspaceをマウントしません。既存`oc-v2-poc`のG3/P6実験データも変更しません。`OPENCODE_WATCHDOG_ENABLED=false`、LLMリクエストは送信しません。

Sandbox内に作成されるデータ：
- `/home/agent/workspace/oc2/bundles/<manifest-prefix>`
- `/home/agent/workspace/oc2/runtime/<manifest-prefix>`

本ランチャーによるSandbox構築・TUI起動の実機検証は**未実施**です。現時点で確認したのはソース単体テストのみです。

## テスト

~~~bash
python3 -m unittest discover -s sandbox/tests -p 'test_oc2.py' -v
python3 -m py_compile sandbox/scripts/oc2.py sandbox/scripts/oc2_guest.py
~~~

テストはFakeRunnerと一時ディレクトリのみを使用し、sbx、sudo、ネットワーク、モデル推論を行いません。

## 次に必要な検証・実装

- 実際のsbx v0.49.2のJSON形式、ディレクトリ転送、CLI seedをHost/Sandbox上で確認
- 通常ユーザーとsbx-pocのsudo/権限境界を確認
- Rules/Commands/Skills/Agent/Model/OMOおよびAkane/Sibylをv2形式へ選別・変換
- クラウドLLMへの資格情報非開示接続とHostの差分回収経路

このfeatureブランチは**ワンコマンド起動の基盤実装**です。設定・モデル・開発Workspaceを含む実用環境がすべて完成したという主張ではありません。
