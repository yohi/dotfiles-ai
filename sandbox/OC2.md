# oc2 — Host から Docker Sandbox 内の OpenCode v2.2.5 を起動

`oc2` は Host 側のランチャーです。Clone mode の Git 検査を通過した Workspace
から新しい shell Sandbox を作り、OpenCode v2.2.5 を起動します。

## 起動

```sh
oc2 --version
oc2 --dry-run --workspace "$HOME/path/to/oc2-safe-test-repo"
oc2 --workspace "$HOME/path/to/oc2-safe-test-repo" --sandbox oc2-phase1-test
```

- `--workspace PATH`: Clone mode で使う Git Repository（既定値は現在のディレクトリ）
- `--repo-root PATH`: `apm.yml` を持つ dotfiles-ai のルート
- `--sandbox NAME`: 作成する Sandbox 名
- `--dry-run`: Sandbox コマンドを実行せず、予定を表示
- `--version`: ランチャーと固定 OpenCode CLI のバージョンを表示

Sandbox 名がすでに存在する場合、再利用・再構築せず停止します。

## 処理内容

通常起動は次の順で行います。

1. Workspace の安全走査を行います。安全走査で除外されるファイルやディレクトリ、特殊ファイル、シンボリックリンク、認証情報らしい内容、OpenCode プロジェクト設定を検出した場合は停止します。`.git` 内のテキストメタデータと展開した Git オブジェクトも検査します。
2. Workspace が Git Repository のルートであること、Docker Sandboxes CLI のバージョンと `--clone` 対応、Sandbox 名の未使用を確認します。
3. `sbx create --clone --name NAME shell WORKSPACE` で新しい Clone-mode Sandbox を作成します。
4. Sandbox 内の固定 CLI を確認し、存在しなければ `@opencode/cli@2.2.5` を導入してバージョンを再確認します。
5. Guest の作業ディレクトリが Clone のルートであることを確認し、Sandbox 専用 Home/XDG 領域から OpenCode を起動します。

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
python3 -m unittest discover -s sandbox/tests -p 'test_oc2.py' -v
python3 -m py_compile sandbox/scripts/oc2.py \
  sandbox/scripts/oc2_workspace.py sandbox/scripts/oc2_workspace_ops.py \
  sandbox/scripts/oc2_session.py sandbox/scripts/oc2_guest.py
```

テストは FakeRunner と一時ディレクトリを使い、実 Sandbox、sudo、ネットワーク、モデル推論を行いません。
