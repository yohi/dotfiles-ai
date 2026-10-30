# P6-5 — OpenCode v2.1.4 通常Plugin登録・Sidebar実機検証

**Status: IMPLEMENTED / GUEST RUNTIME NOT YET VERIFIED**

第4段で用意したSandbox専用OpenCode実行環境が実際に正常動作するかを確認するための手順。
ここに記載した手順は **2026-10-30時点で実際の oc-v2-poc では未実行**。

## Stacked Branch

1. feature/sandbox-runtime-scaffold-20261030 — 設定雛形
2. feature/sandbox-config-exporter-20261030 — SSOTから最小設定の抽出
3. feature/sandbox-snapshot-stage-20261030 — 明示的なsbx cp
4. feature/sandbox-opencode-runtime-20261030 — ゲスト専用設定とランチャー
5. feature/sandbox-opencode-v2-live-validation-20261030 — この段階

第5段の親は第4段のHEAD。前段・masterに変更しない。

## 前提

- ホストのOpenCode v1・既存設定・既存ソースリポジトリは変更しない。
- Docker Sandbox名は oc-v2-poc、ゲストのワークスペースは /home/agent/workspace。
- ホストの作業ツリーをマウントしないSandboxであることを作業者が確認する。
- OpenCode v2.1.4、akane@3.0.0-alpha.2、sibyl@3.0.0-alpha.1のビルド成果物がゲストに存在。
- 第2段の設定Bundle、第3段で配置した3ファイル、第4段で作成した独立runtimeを使用。
- モデルAPI呼び出し、ネットワーク許可、ホストへの自動書戻しはしない。

## 1. Runtime設定の静的検証

第5段の sandbox/scripts/verify_opencode_v2_runtime.py と第3段の
sandbox/scripts/stage_opencode_v2.py は、同じディレクトリへ配置する。
ホストからコピーする場合は sbx cp を使うユーザーから読める安全な一時受渡し領域を使い、
y_ohi と sbx-poc のユーザー間権限を緩めない。

以下はゲスト内で実施。BUNDLEを実際の第3段ステージング先へ置き換える。

~~~sh
BASE=/home/agent/workspace
BUNDLE="$BASE/sbx-config-REPLACE_WITH_ACTUAL_NAME"
RUNTIME="$BASE/opencode-v2-runtime-1"
OC="$HOME/.local/opencode-v2/node_modules/.bin/opencode"

# OpenCodeプロセスの起動なし。設定とハッシュを確認。
python3 "$BASE/verify_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" \
  --runtime-dir "$RUNTIME" \
  --require-both
~~~

snapshot_valid、runtime_integrity、akane_configured、sibyl_configured が全て true で
設定準備の整合性のみPASS。setupや描画までは確認したことにならない。

## 2. CLI実体と統合設定の確認（明示指定）

~~~sh
python3 "$BASE/verify_opencode_v2_runtime.py" \
  --bundle "$BUNDLE" \
  --runtime-dir "$RUNTIME" \
  --require-both \
  --probe-cli \
  --opencode-bin "$OC"
~~~

--probe-cli は、環境変数を限定して opencode --version と
opencode debug config を実行する。取得した設定はそのまま出力・保存せず、
v2.1.4、Server側Plugin一覧、追加MCPの不存在を照合する。
**Plugin setup が実際に動いた証拠ではない**。
OpenCodeによるキャッシュ・ローカル状態変更はあり得るので、ゲスト内のみで実行。
ネットワークはDefault Denyを維持する。

追加MCP、想定外Plugin、別バージョン、曖昧な形式では停止する。
システム共通設定や自動検出Pluginがある場合も成功扱いせず、原因調査へ移る。
debug config の生の出力は、資格情報を含む可能性があるため共有しない。

## 3. TUIの目視確認（モデルへのPromptを出さない）

~~~sh
"$RUNTIME/run-opencode.sh" --standalone
~~~

実機の観測結果は別々に記録する。

| 項目 | 判定条件 |
| --- | --- |
| v2.1.4起動 | TUIが起動し操作可能 |
| Sibyl Sidebar | **検証用ラッパーなしの通常登録**でSidebarが表示 |
| Akane機能 | Watchdogイベントが実際に出た場合にのみ機能を判定 |
| Cleanup | Cleanupが実行された記録がある場合にのみPASS |
| Subagent | 実際の子エージェントを動かした場合のみ評価（この工程ではNOT_TESTED） |

TUI表示とSidebar描画は別観測。スクリーンショットに機密が写り込まないか確認。

## 4. 重要な留保

- 認証情報・Provider設定・外部MCPは転送しない。
- 空のMCP/Plugin配列は全設定ソースの完全な無効化保証にならない。
- TUIのcli.jsonとServerのopencode.jsoncは別の設定。
- ローカルパッケージのexports解決は実機動作で確認する。
- 静的検証とダミーCLIは実OpenCode互換性の証拠ではない。
- sbx execは停止中のSandboxを起動する可能性がある。操作は明示的に行う。

## 5. オフライン単体テスト

~~~sh
python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v
~~~

テストは一時ディレクトリ・ダミーCLIを使用し、実Docker/OpenCode/モデルへアクセスしない。

## 一次資料

- Server Plugin: https://dev.opencode.ai/v2/docs/plugins
- TUI Plugin: https://dev.opencode.ai/v2/docs/cli/plugins
- Plugin package parts: https://dev.opencode.ai/v2/docs/build/plugins/
- sbx cp: https://docs.docker.com/reference/cli/sbx/cp/
- sbx exec: https://docs.docker.com/reference/cli/sbx/exec/

実機で1〜3の証拠を取得するまでは **P6-5 LIVE_NOT_VERIFIED**。
