# oc2 — HostからDocker Sandbox内のOpenCode v2.1.4を起動

**Status: FEATURE_BRANCH_PATCHED / FIRST_LIVE_ATTEMPT_FAILED / RETEST_PENDING**

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
3. `sbx ls`で既存Sandboxを確認。なければ`sbx create --name oc2-dev shell`でマウントなしSandboxを新規作成。既存Sandboxの再利用は、`sbx ls --format json`でSandbox名とshell agentを照合し、`sbx inspect NAME --json`の`runtime_mounts`が**空配列**である場合だけ許可。名前の不一致・マウント情報の欠落・マウントありは安全停止。
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

2026-11-03の初回実機実行では、`oc2-dev`のmountless Sandbox作成に成功しましたが、直後の `mkdir: cannot create directory '': No such file or directory` で停止しました。これは旧ランチャーが `sbx exec ... bash -c` の `$1` / `$2` 引数に依存していた問題と整合します。featureブランチ上で直接argv実行に修正しましたが、**修正後の実機再検証は未実施**です。

再試行前には別の作業ツリーに未コミット変更がないか確認してください。既存の `oc2-dev` を削除せず、そのまま再利用します。

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

## 2026-11-03 — sbx exec引数転送の初回実機修正

旧実装では初期化や存在チェックに `bash -c '...' oc2 "$path"` を使っていました。実機の初回起動では `mkdir` に空の引数が渡される事象が観測されました。

対策:

- ディレクトリ生成・権限設定を `sbx exec SANDBOX mkdir ...` / `chmod ...` に変更
- 存在・CLIバージョン検査のパスを固定引用し、`bash -c` の後ろに引数を渡さない
- TUIを `sbx exec -it -w ... SANDBOX env -i ... opencode --standalone` で直接起動
- argv形状のオフライン回帰テストを追加

改修後に必要な確認は `python3 -m unittest discover -s sandbox/tests -p 'test_oc2.py' -v` と実機の `oc2 --prepare-only` です。既存のNetwork PolicyやSandboxを削除・初期化しません。オフラインテストと実機確認がPASSするまではワンコマンド構築完了と判定しません。

## 2026-11-03 — v0.49.2 mountless再利用判定修正

初回実機試行で`oc2-dev`の作成後、次の実行時には`OC2_STOP: could not verify that the existing Sandbox has no Host mount`で停止しました。原因は`sbx ls --format json`が`workspace`や`workspaces`を返さないことです。

Host Operatorの実測:
- `oc2-dev`の一覧フィールド: `agent, created_at, id, last_used_at, name, status`
- `sbx inspect oc2-dev --json`のトップレベルに`runtime_mounts`あり
- `runtime_mounts: []` （マウントなし）

これを受けて既存Sandbox再利用時の判定を`sbx inspect NAME --json`に変更しました。既存の一覧情報による名前・agentの確認も維持し、`runtime_mounts`が空配列のときだけ続行します。既存一覧に`workspace`情報があり、それがマウントを示す場合も拒否します。無条件でmountlessとみなす処理には変更していません。

修正後の実機検証は未実施です。次に新しい修正HEADを一時worktreeへ取り込み、オフラインテスト・`oc2 --prepare-only`の順で実施してください。既存の`oc2-dev`は削除しないでください。
