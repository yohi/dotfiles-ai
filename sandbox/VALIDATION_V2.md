# P6-5 — OpenCode v2.1.4 実機ロード検証

**Status: STATIC_VERIFIER_IMPLEMENTED / LIVE_SANDBOX_NOT_TESTED**

この文書の目的は、P6-1〜4で組み立てた**通常Plugin登録経路**を実機で検証し、単なる設定ファイルの存在と、プラグイン実動作を区別することです。

## Stacked branch

- P6-1: feature/sandbox-runtime-scaffold-20261030
- P6-2: feature/sandbox-config-exporter-20261030
- P6-3: feature/sandbox-snapshot-stage-20261030
- P6-4: feature/sandbox-opencode-runtime-20261030
- P6-5: feature/sandbox-runtime-validation-20261030（このブランチ）

P6-5はP6-4のHEADから分岐。既存ブランチ、master、ホストOpenCode v1は変更しません。

## 2段階の検証

**Phase A — static/runtime version（自動化可能）**

- 第3段の3ファイルを再検証する。
- 第4段で生成したServer/TUI設定とreceiptのハッシュを検証する。
- Server設定にakane、TUI設定にsibylがそれぞれ1つずつあることを確認する。
- ローカルパッケージの名前・バージョン・exportsを確認する。
- MCP設定が空であることを確認する（他の設定ソースは検証外）。
- 隔離用XDGランチャーの存在を確認する。
- 明示指定時のみ、ランチャーの \`--version\` を実行する。
- **Phase AがPASSしても、実PluginロードやSidebar表示はPASSにしない。**

**Phase B — live OpenCode TUI（人間の確認が必要）**

- \`debug config\` で実際の有効設定を確認する。結果には環境情報が含まれる可能性があるので公開しない。
- 新しいランチャーからOpenCodeを起動する。
- akane / sibylのロード時エラーがないことを調べる。
- akaneが選択中のセッションに状態を書き出すことを確認する。
- sibyl Sidebarの描画を確認する。状態が存在しない場合は「未判定」とし、単純な「FAIL」と区別する。
- 終了後、Sandbox内の実行環境以外を変更していないか確認する。

## 事前条件

- Hostのdotfiles-ai checkoutは**このP6-5ブランチ**であること。既存ホスト用設定の同期コマンドは実行しない。
- 第2段の設定エクスポートと第3段のSandboxへのコピーが成功していること。
- 第3段のステージ先 \`/home/agent/workspace/sbx-config-...\` を**実測**して控えていること。
- Docker Sandboxは \`oc-v2-poc\`、ユーザーは \`agent\`、ホストマウントなし・ネットワークDefault DenyのPoC環境であること。
- \`/home/agent/workspace/p5/akane\` / \`p5/sibyl\` のコピーがあり、package.jsonとdistの内容が既存PoCと一致すること。
- **認証ファイル、環境変数トークン、GitHub PAT、AWS認証情報を渡さない。**

## A. ホストの sbx-poc 側

P6-5のチェックアウトから、変更したスクリプトだけをゲストのworkspaceに転送する。
既存の同名ファイルを上書きする可能性がある場合は、送信先名を変更する。

~~~sh
sbx cp sandbox/scripts/stage_opencode_v2.py oc-v2-poc:/home/agent/workspace/stage_opencode_v2.py
sbx cp sandbox/scripts/prepare_opencode_v2_runtime.py oc-v2-poc:/home/agent/workspace/prepare_opencode_v2_runtime.py
sbx cp sandbox/scripts/verify_opencode_v2_runtime.py oc-v2-poc:/home/agent/workspace/verify_opencode_v2_runtime.py
~~~

ここで送るのはPythonソースだけ。Hostの\`~/.config/opencode\`や\`.env\`はコピーしない。

## B. Sandboxゲスト側

\`BUNDLE\` にはP6-3で実際に出力されたディレクトリを入力する。
他の実行履歴を使い回す場合は、スナップショットとソースの整合性を再確認する。

~~~sh
BASE=/home/agent/workspace
BUNDLE="$BASE/sbx-config-REPLACE_WITH_VERIFIED_DIRECTORY"
RUNTIME="$BASE/opencode-v2-p6-5"
OC="$HOME/.local/opencode-v2/node_modules/.bin/opencode"

# 既存のruntimeとは独立した、新しい実行領域で確認する
python3 "$BASE/prepare_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" --runtime-dir "$RUNTIME" --opencode-bin "$OC" \
  --akane "$BASE/p5/akane" --sibyl "$BASE/p5/sibyl"

# ここから新規のSandbox内ディレクトリだけを生成
python3 "$BASE/prepare_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" --runtime-dir "$RUNTIME" --opencode-bin "$OC" \
  --akane "$BASE/p5/akane" --sibyl "$BASE/p5/sibyl" --write

# Plugin定義と設定の整合性のみチェック。OpenCodeは起動しない。
python3 "$BASE/verify_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" --runtime-dir "$RUNTIME"

# 明示指定した場合のみ、OpenCodeの--versionを起動する。
python3 "$BASE/verify_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" --runtime-dir "$RUNTIME" --probe-version
~~~

期待値は \`STATIC_VERIFIED_RUNTIME_UNPROVEN\` と \`OPEN_CODE_2_1_4_CONFIRMED\`。
**これはSidebar表示の証拠にはならない。**

## C. 通常のPluginローダーを実際に試す

~~~sh
# モデルへの指示は送らず、有効設定をゲストで確認（生の出力を公開しない）
"$RUNTIME/run-opencode.sh" debug config

# 対話型TUIのロードを目視で確認
"$RUNTIME/run-opencode.sh" --standalone
~~~

- 有効設定のServer pluginsにakaneのディレクトリ、TUI pluginsにsibylのディレクトリがあるか確認する。
- OpenCode起動時にPluginのimport/setupのエラーが出ていないか確認する。
- Sidebarを確認し、必要ならセッションを選択する。akaneの状態が未生成ならSidebarは非表示になり得る。
- \`opencode plugin list\`だけで、実行時のPlugin初期化を判断しない。
- ネットワークを許可しない。LLMを呼ぶセッション実行はこの段階の必須条件ではない。

**サイドバーが表示されない場合:** 静的チェックを通ってもPlugin runtimeでは失敗し得る。ゲスト内の起動エラー、パッケージ依存解決、選択セッションとAkane stateの有無を確認する。モデル通信や認証設定を増やして「動かす」ことはしない。

## PASSの定義

| 検証項目 | PASSとする条件 |
| --- | --- |
| 静的構成 | verifierが\`STATIC_VERIFIED_RUNTIME_UNPROVEN\`を出す |
| OpenCode実体 | 明示したversion probeが2.1.4を出す |
| Serverロード | 既存ラッパーを介さずakane setupが実行された証拠がある |
| TUIロード | 既存ラッパーを介さずsibyl setupが実行された証拠がある |
| Sidebar | 選択セッションのSidebarが実際に描画された |
| 隔離維持 | HostのOpenCode v1・Git正本・ネットワークポリシーに変更がない |

現時点では静的検証器とそのユニットテストしか追加していないため、**実機Phase BはNOT_EXECUTED**です。

## オフラインテスト

~~~sh
python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v
~~~

unittestはモックのPlugin配置とダミーOpenCodeバイナリを使用し、実Sandboxには接続しません。
