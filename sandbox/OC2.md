# oc2 — HostからDocker Sandbox内のOpenCode v2.1.4を起動

**Status: ONE_COMMAND_TUI_LIVE_PASS (historical) / OMO_REMOVAL_PATCH_READY / LIVE_RETEST_PENDING**

> この文書はOpenCode v2.1.4を対象とした初期実装の記録です。現行の
> OpenCode v2.2.5 Provider経路とCredential Mixinの手順は
> [Provider運用ガイド](../docs/opencode-v2-provider-routing.md)を参照してください。

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

元の設定エクスポーターは`apm.yml`から`shell`と`snapshot`だけを移行します。追加の`oc2_assets.py`が固定許可リストからGlobal Rules（AGENTS.md＋補助6件）、`/build-skill`コマンド、2つの自作Skills、TUIの`theme`だけを選別・変換します。Provider、外部Agent定義、その他のCommands、外部Skills、Akane、Sibyl、MCP、認証情報は自動移植しません。`plugins: []`、`mcp: {}`は出力スナップショットの内容であり、OpenCodeの他の設定ソースからの自動検出まで完全に無効化する保証ではありません。

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
- Rules/Commands/Skillsの安全な移行と、必要時のみV2ネイティブAgentを独立設計
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

## 2026-11-03 — Settings Migration R1（実機適用前）

`oc2`の作成・再利用・Configステージ・固定CLI準備・`--standalone`によるTUI起動はHuman Operatorの実機確認でPASSしました。この結果は**追加の設定移行処理の検証を意味しません**。

新規の`sandbox/scripts/oc2_assets.py`は、Hostの`dotfiles-ai`から以下の**固定許可リスト**だけをUTF-8テキストとして読みます。

- `global-rules/AGENTS.global.md` → `$XDG_CONFIG_HOME/opencode/AGENTS.md`
- `global-rules/{DOCS_STYLE,GIT_STANDARDS,MARKDOWN,META_PROMPT,SHELL,STACKED_PR_WORKFLOW}.md` → `$XDG_CONFIG_HOME/opencode/rules/`
- `agent-commands/build-skill.md` → `$XDG_CONFIG_HOME/opencode/commands/build-skill.md`（v1専用の`agent`/`model`フィールドを除去）
- `agent-skills/custom/{agent-skill-architect,config-modernizer}/SKILL.md` → `$XDG_CONFIG_HOME/opencode/skills/<id>/SKILL.md`
- `opencode/tui.jsonc`の`theme`のみ → v2の`cli.json.theme.name`へ変換

JSONに`files`とSHA-256を格納し、Host全体のSHA-256でも固定します。guest側は**独立の許可リスト**に一致する項目だけを検証してから書き込みます。SSH/Git認証情報、`.env`、既存のHost OpenCode auth、MCP、Provider、TUI plugin一覧は読み取りません。出力内容が異なる場合は、新しいRuntime IDを使用し、既存Runtimeを上書きしません。

`opencode.jsonc.instructions`は、Sandbox内に配備した補助ルール6件の絶対パスを参照します。Global `AGENTS.md`はOpenCode v2の自動読み込み対象であり、重複を避けて`instructions`には入れません。

**今後の移行対象**: 必要時のみ独立設計するV2ネイティブAgent、Akane/Sibyl（バージョン・ロード契約確認）、外部Skills、その他Commands（副作用とモデルピンのレビューが必要）、LLM用Host BrokerとMCP。

### このrevisionの確認

```sh
python3 -m unittest discover -s sandbox/tests -p 'test_oc2.py' -v
python3 -m py_compile sandbox/scripts/oc2.py sandbox/scripts/oc2_guest.py sandbox/scripts/oc2_assets.py
./bin/oc2 --dry-run
./bin/oc2 --prepare-only
```

`OC2_ASSETS_VERIFIED`と`OC2_PREPARED`を確認してから`./bin/oc2`でTUIを起動してください。この段階でモデル推論や外部サービスへの接続は行いません。修正対象はfeatureブランチだけで、Host OpenCode v1や`oc-v2-poc`の既存設定は変更しません。

## 2026-11-03 — Scope correction: OmO excluded

OmOはOpenCode V2移行の対象外とする。過去のR2 Agent/Category・モデル候補
抽出コードは削除し、`opencode/omo.jsonc`を`oc2`から読み込まない。
既存OpenCode V1用の設定原本自体は変更・削除しない。

`oc2`の移行対象はGlobal Rules 7件、Command 1件、Skills 2件、
TUIテーマ1件のみ。V2の組込みAgentを使用し、カスタム`agents`、
`default_agent`、`model`、Provider、Fallback、認証情報は生成しない。
独自Agentは使用目的と権限を確定した後の別タスクとする。

Host/Sandbox隔離、Default Deny、CLIバージョン固定、HASH検証、
既存Runtime非上書きは維持する。Asset SHAが変わるため新しいRuntime
Identityで準備されることを想定し、古いR2 Runtimeは変更しない。

### オフライン検証

~~~sh
python3 -m unittest discover -s sandbox/tests -p 'test_oc2.py' -v
python3 -m py_compile sandbox/scripts/oc2.py sandbox/scripts/oc2_assets.py \
  sandbox/scripts/oc2_guest.py
./bin/oc2 --dry-run
~~~

その後、Human Operatorが隔離されたHostで`./bin/oc2 --prepare-only`、
OpenCode V2.1.4の`debug config`と`debug agents`を実測する。
CLIによる実機PASS、Cloud LLM通信、完全な新規Sandbox一発構築は未確認。
