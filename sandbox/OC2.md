# oc2 — Host から Docker Sandbox 内の OpenCode v2.2.5 を起動

**Status: ONE_COMMAND_TUI_LIVE_PASS (historical) / OMO_REMOVAL_PATCH_READY / LIVE_RETEST_PENDING**

`oc2` は Host 側のランチャーです。検査済みWorkspace Snapshotだけを新しいmountless shell Sandboxへ転送し、OpenCode v2.2.5を起動します。
現行の OpenCode v2.2.5 Provider 経路と Credential Mixin の手順は
[Provider運用ガイド](../docs/opencode-v2-provider-routing.md)を参照してください。

## 起動

```sh
oc2 --version
oc2 --dry-run --workspace "$HOME/path/to/oc2-safe-test-repo"
oc2 --workspace "$HOME/path/to/oc2-safe-test-repo" --sandbox oc2-phase1-test
# Cloudflare を有効にする場合のみ追加
oc2 --workspace "$HOME/path/to/oc2-safe-test-repo" --allow-paid-inference \
  --use-cloudflare-ai-gateway
```

- `--workspace PATH`: Snapshotとして転送するGit Repository（既定値は現在のディレクトリ）
- `--repo-root PATH`: `apm.yml` を持つ dotfiles-ai のルート
- `--sandbox NAME`: 作成する Sandbox 名
- `--dry-run`: Sandbox コマンドを実行せず、予定を表示
- `--version`: ランチャーと固定 OpenCode CLI のバージョンを表示
- `--prepare-only`: APM V2 設定の生成と検証のみを行い、Sandbox コマンドを実行しない
- `--resume`: retained SnapshotとSession receiptが一致する既存Sandboxの作成後処理を再開する
- `--allow-paid-inference`: 外部 Provider への推論をこの起動に限り明示的に承認する（未指定で Provider 設定がある場合は停止）
- `--use-cloudflare-ai-gateway`: Cloudflare AI Gateway を有効にし、Sandbox Secret の scope を確認する。未登録の場合は対話端末で Sandbox scope に登録して検証する

Sandbox名がすでに存在する場合、通常起動では再利用・再構築せず停止します。作成後のCredential確認に失敗した場合は、同じWorkspaceとSandboxを指定して`--resume`を明示します。

## 処理内容

通常起動は次の順で行います。

1. Workspaceの安全走査と転送Manifest作成を行います。特殊ファイル、symlink、Credential内容、未承認OpenCodeプロジェクト設定を検出した場合は停止します。`.git`内のテキストメタデータと展開したGitオブジェクトも検査します。
2. WorkspaceがGit Repositoryのルートであること、Docker Sandboxes CLIのバージョンと`--kit`対応、Sandbox名の未使用、Git remote URLに資格情報が含まれないことを確認します。
3. `apm.yml` から OpenCode V2 設定を生成・検証します。外部 Provider を選択している場合、`--allow-paid-inference` による明示的承認を求めます。Cloudflare Custom Gateway は`--use-cloudflare-ai-gateway`を指定した場合だけ有効にし、Host 側の検証済み識別子を使います。
4. WorkspaceをprivateなSnapshotへmaterializeします。originが正確に`yohi/dotfiles-ai`の場合はR1を選択し、その検査済みファイルだけを含めます。検査を通過した`apm.yml`はSnapshotに含まれます。
5. HostでGitHub Release APIからOpenCode v2.2.5 Linux x64 assetを取得します。Release APIのassetサイズ、固定SHA-256、Archive内の唯一の実行ファイルを検証し、private temporary directoryに展開します。
6. `sbx create --name NAME --kit MIXIN shell`でmountless Sandboxを作成し、`sbx cp`でSnapshotを専用Workspaceへ転送します。ManifestのSHA-256を照合した後、Guest内でGit Repositoryを初期化し、安全なremote URLを設定します。Credential MixinはHost側Proxyを使用し、実CredentialをGuestへコピーしません。
7. 転送SnapshotとSession receiptを保持します。Cloudflare Credential確認が失敗した場合、`--resume`はreceiptとSandbox名を照合したうえで作成後の処理を再開します。
8. Cloudflareが有効な場合は既存Sandbox/global Secretを確認します。なければ対話端末が必要です。Sandbox scopeに登録し、登録後もscopeを検証します。検証成功後、Hostで検証済みのStandalone Binaryを`sbx cp`で固定Guest pathへコピーし、versionを確認します。
9. Guest作業ディレクトリが転送Workspaceであることを確認し、Sandbox専用Home/XDG領域を設定します。TUI起動の直前にGuest内でOAuth仲介ヘルパーを実行し、その後OpenCodeを起動します。Guest内の`npm install`は実行しません。

Sandbox 作成後に失敗しても、自動削除しません。Host の環境変数、Provider 認証、MCP、Plugin 設定は渡しません。

## Host Repository と Workspace の範囲

Host WorkspaceはGuestへmountされません。`oc2`は検査済みManifestのファイルだけをSnapshotへmaterializeしてGuestの作業ディレクトリへ転送します。`.git`、汎用除外ファイル、特殊ファイル、symlink、Credential検出対象は転送しません。

そのため`oc2`はSandbox作成前にWorkspaceとGitメタデータを走査し、検査できない内容やSnapshotから漏れる内容があれば停止します。`opencode.json`、`opencode.jsonc`、`cli.json`を含むWorkspaceも拒否します。実機確認には新規の無害なテスト用Git Repositoryだけを使ってください。実プロジェクトには適用しないでください。

```sh
test_repo=$(mktemp -d)
git -C "$test_repo" init
printf 'print("safe sandbox fixture")\n' > "$test_repo/main.py"
git -C "$test_repo" add main.py
git -C "$test_repo" -c user.name='OC2 Test' \
  -c user.email='oc2-test@example.invalid' commit -m fixture
oc2 --workspace "$test_repo" --sandbox oc2-phase1-test
```

Docker Sandboxes `v0.49.2`のmountless shell workload、Snapshot転送、OpenCode `v2.2.5`の起動を確認対象とします。CLIの必要機能や固定バージョンを確認できない場合は停止します。実プロジェクトでの機密ファイル非露出を保証するものではありません。

## テスト

```sh
python3 -m unittest discover -s sandbox/tests -p 'test_oc2*.py' -v
python3 -m py_compile sandbox/scripts/oc2.py \
  sandbox/scripts/oc2_workspace.py sandbox/scripts/oc2_workspace_ops.py \
  sandbox/scripts/oc2_session.py sandbox/scripts/oc2_guest.py
```

テストは FakeRunner と一時ディレクトリを使い、実 Sandbox、sudo、ネットワーク、モデル推論を行いません。
