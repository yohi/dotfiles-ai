# OpenCode v2.1.4 — 隔離Sandbox実行設定（第4段）

**Status: IMPLEMENTED / NOT_LIVE_TESTED / NO_DEPLOYMENT**

## Stacked branches

1. feature/sandbox-runtime-scaffold-20261030 — 設定雛形
2. feature/sandbox-config-exporter-20261030 — 限定的な設定エクスポーター
3. feature/sandbox-snapshot-stage-20261030 — 明示的なsbx cpと整合性検証
4. feature/sandbox-opencode-runtime-20261030 — このブランチ。Sandbox内での隔離設定・ランチャー生成

それぞれ前段のHEADから分岐しています。masterへの変更、PR作成、マージは行いません。

## 対象と非対象

ホストのdotfiles-ai/apm.ymlをSSOTとし、ホスト側OpenCode v1や各開発リポジトリは変更しません。
第3段で作った3ファイルのスナップショットを受け取り、Sandboxのゲスト環境にだけ新しい実行領域を作ります。

- デフォルトはDRY RUN（検証と計画出力のみ）。
- --writeを明示したときだけ新しい実行領域を作ります。既存の領域の上書きは禁止。
- OpenCode、Docker Sandbox、モデルAPI、ネットワークにスクリプト自身はアクセスしません。
- --akaneと--sibylは任意であり、指定されたローカルディレクトリのpackage.jsonの名前と固定バージョン、エントリポイントを検査します。
- akaneはServer設定のpluginsに、sibylはTUI設定のcli.jsonのpluginsに記載します。
- 固定バージョン：akane 3.0.0-alpha.2、sibyl 3.0.0-alpha.1、OpenCode 2.1.4。
- ランチャーは隔離したXDG_CONFIG_HOME / XDG_DATA_HOME / XDG_CACHE_HOMEで起動します。env -iにより既存の環境変数を引き継ぎません。
- /etc/opencode 等のマシン全体の設定や、Sandbox内の別プロセスとの完全な分離を保証しません。
- Pluginのメタデータを認識できることと、通常のローダー経由で機能が起動することは別です。後者は実機未検証です。

## Sandbox内での実行手順例（未実施）

前段の第3ブランチで得たステージング先を必ず確認し、以下のBUNDLEを実際のパスに置き換えてください。
以下はゲストのagentユーザーが、ホストをマウントしないoc-v2-pocを操作する場合の例です。

事前に第3段のstage_opencode_v2.pyと第4段のprepare_opencode_v2_runtime.pyをゲスト内の
ゲストユーザーの $HOME/workspace/ へコピーし、同じディレクトリに配置します。ホストでのコピー例：

~~~sh
GUEST_USER=agent
sbx cp sandbox/scripts/stage_opencode_v2.py "oc-v2-poc:/home/${GUEST_USER}/workspace/stage_opencode_v2.py"
sbx cp sandbox/scripts/prepare_opencode_v2_runtime.py "oc-v2-poc:/home/${GUEST_USER}/workspace/prepare_opencode_v2_runtime.py"
~~~

ゲスト内：

~~~sh
BASE="$HOME/workspace"
BUNDLE="$BASE/sbx-config-REPLACE_WITH_ACTUAL_NAME"
RUNTIME="$BASE/opencode-v2-runtime-1"
OC="$HOME/.local/opencode-v2/node_modules/.bin/opencode"

# 1. 変更なし。Snapshotの内容・Pluginパッケージを検証する
python3 "$BASE/prepare_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" \
  --runtime-dir "$RUNTIME" \
  --opencode-bin "$OC" \
  --akane "$BASE/p5/akane" \
  --sibyl "$BASE/p5/sibyl"

# 2. 意図的に、ゲスト内に隔離設定を作成する（新規ディレクトリのみ）
python3 "$BASE/prepare_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" \
  --runtime-dir "$RUNTIME" \
  --opencode-bin "$OC" \
  --akane "$BASE/p5/akane" \
  --sibyl "$BASE/p5/sibyl" \
  --write

# 3. ここから先のOpenCode起動は別操作。モデルプロンプトは送らない。
"$RUNTIME/run-opencode.sh" --version
"$RUNTIME/run-opencode.sh" debug config
# 必要であればTUIを手動で起動し、終了してSidebarを確認する。
# "$RUNTIME/run-opencode.sh" --standalone
~~~

注意：起動時のOpenCodeがモデルプロバイダーや外部リソースに問い合わせる可能性があります。
ネットワークDefault Denyのまま行い、許可の追加は別途明示承認とします。

## 設定の検証方法

OpenCode v2の公式ドキュメント：
- Server plugin registration: https://dev.opencode.ai/v2/docs/plugins/
- TUI-only plugin registration: https://dev.opencode.ai/v2/docs/cli/plugins/
- Global cli.json path: https://dev.opencode.ai/v2/docs/cli/config/

OpenCode v2はServerのopencode.json(c)とTUI専用のcli.jsonでPlugin登録を分けています。
今回の設定はServerのakaneとTUIのsibylをそれぞれローカルディレクトリとして指定します。
実際のPlugin初期化、Sidebar表示、cleanupは、実機で改めて確認が必要です。
以前のラッパー試験ではopencode plugin listが初期化成功を反映しなかったため、
plugin listのみでPASS判定しないでください。

## オフライン単体テスト

~~~sh
python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v
~~~

単体テストは一時ディレクトリとダミーバイナリだけを使用します。
Docker SandboxやOpenCodeの実プロセスには接続しません。
