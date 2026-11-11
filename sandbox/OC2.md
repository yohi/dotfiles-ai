# oc2 — Host から Docker Sandbox 内の OpenCode v2.2.5 を起動

**Status: ONE_COMMAND_TUI_LIVE_PASS (historical) / OMO_REMOVAL_PATCH_READY / LIVE_RETEST_PENDING**

`oc2` は Host 側のランチャーです。Clone mode の Git 検査を通過した Workspace を
衛生化したスナップショット経由で新しい shell Sandbox に見せ、OpenCode v2.2.5 を起動します。
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

- `--workspace PATH`: Clone mode で使う Git Repository（既定値は現在のディレクトリ）
- `--repo-root PATH`: `apm.yml` を持つ dotfiles-ai のルート
- `--sandbox NAME`: 作成する Sandbox 名
- `--dry-run`: Sandbox コマンドを実行せず、予定を表示
- `--version`: ランチャーと固定 OpenCode CLI のバージョンを表示
- `--prepare-only`: APM V2 設定の生成と検証のみを行い、Sandbox コマンドを実行しない
- `--allow-paid-inference`: 外部 Provider への推論をこの起動に限り明示的に承認する（未指定で Provider 設定がある場合は停止）
- `--use-cloudflare-ai-gateway`: Cloudflare AI Gateway を有効にし、Sandbox Secret の scope を確認する。未登録の場合は対話端末で Sandbox scope に登録して検証する

Sandbox 名がすでに存在する場合、再利用・再構築せず停止します。

## 処理内容

通常起動は次の順で行います。

1. Workspace の安全走査を行います。安全走査で除外されるファイルやディレクトリ、特殊ファイル、シンボリックリンク、認証情報らしい内容、OpenCode プロジェクト設定を検出した場合は停止します。`.git` 内のテキストメタデータと展開した Git オブジェクトも検査します。
2. Workspace が Git Repository のルートであること、Docker Sandboxes CLI のバージョン、`--clone` と `--kit`（credential Mixin）対応、Sandbox 名の未使用、Git リモート URL に資格情報が含まれないことを確認します。
3. `apm.yml` から OpenCode V2 設定を生成・検証します。外部 Provider を選択している場合、`--allow-paid-inference` による明示的承認を求めます。Cloudflare Custom Gateway は`--use-cloudflare-ai-gateway`を指定した場合だけ有効にし、Host 側の検証済み識別子を使います。
4. Workspace の内容を `XDG_STATE_HOME/oc2/clone-sources` 配下の専用ディレクトリへ、実行中の変更を追跡する安全なコピーとして取り込み、衛生化したスナップショットとして Git commit します。Sandbox 作成が不確定に失敗した場合でもスナップショットは保持されます。
5. `sbx create --clone --name NAME --kit MIXIN shell CLONE_SOURCE` で新しい Clone-mode Sandbox を作成します。MIXIN は Host 側 Proxy 経由の Credential バインディングを宣言し、実 Credential は Guest にコピーしません。作成後、一時 Mixin ディレクトリは削除されます。
6. Sandbox 内の固定 CLI を確認し、存在しなければ `@opencode/cli@2.2.5` を導入してバージョンを再確認します。
7. Cloudflare が有効な場合は、既存の Sandbox/global Secret を確認します。なければ対話端末が必要です。Sandbox scope に登録し、登録後もscopeを検証します。
8. Guest の作業ディレクトリが Clone のルートであることを確認し、Sandbox 専用 Home/XDG 領域から OpenCode を起動します。起動前に Guest 内で OAuth 仲介ヘルパーを実行します。

Sandbox 作成後に失敗しても、自動削除しません。Host の環境変数、Provider 認証、MCP、Plugin 設定は渡しません。

## Host Repository と Workspace の範囲

Clone mode では Host の Git Repository が Guest から Read-only source として見え、Guest はその Clone を作業場所にします。Repository 全体が公開元に含まれるため、`.git`、`.env`、Git 除外ファイルも対象です。Host Repository のうち選別した一部だけを Guest に渡す方式ではありません。

そのため `oc2` は Sandbox 作成前に Workspace と Git メタデータを走査し、検査できないものや安全走査から除外される内容があれば停止します。`opencode.json`、`opencode.jsonc`、`cli.json` を含む Workspace も拒否します。実機確認には新規の無害なテスト用 Git Repository だけを使ってください。実プロジェクトには適用しないでください。

```sh
test_repo=$(mktemp -d)
git -C "$test_repo" init
printf 'print("safe sandbox fixture")\n' > "$test_repo/main.py"
git -C "$test_repo" add main.py
git -C "$test_repo" -c user.name='OC2 Test' \
  -c user.email='oc2-test@example.invalid' commit -m fixture
oc2 --workspace "$test_repo" --sandbox oc2-phase1-test
```

Docker Sandboxes `v0.49.2` の Clone mode と OpenCode `v2.2.5` の起動を確認対象とします。CLI が対応バージョンでない場合や固定バージョンを確認できない場合は停止します。実プロジェクトでの機密ファイル非露出を保証するものではありません。

## テスト

```sh
python3 -m unittest discover -s sandbox/tests -p 'test_oc2*.py' -v
python3 -m py_compile sandbox/scripts/oc2.py \
  sandbox/scripts/oc2_workspace.py sandbox/scripts/oc2_workspace_ops.py \
  sandbox/scripts/oc2_session.py sandbox/scripts/oc2_guest.py
```

テストは FakeRunner と一時ディレクトリを使い、実 Sandbox、sudo、ネットワーク、モデル推論を行いません。
