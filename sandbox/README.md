# OpenCode Sandbox runtime — 設定と開発環境

> **Status: PHASE1_LIVE_PASS**
>
> このディレクトリは、ホスト管理・Sandbox実行に向けた設定雛形と、読み取り主体の限定的な設定エクスポーターです。
> `oc2`実行時は新しいClone-mode Sandboxを作成します。既存Sandboxの再構築・削除、`sbx policy`変更、
> ホストOpenCode v1の更新、認証情報の転送は自動で行いません。
> `sandbox/` 配下のYAMLは、Docker Sandboxes公式スキーマではなく独自の設計用メタデータです。

## 責務と正本

- **Host**: `dotfiles-ai` の `apm.yml` を設定SSOTとし、プロジェクトのGitリポジトリを正本として保持する。
- **Sandbox**: Phase 1の`oc2`はOpenCode v2.2.5のTUI起動だけを行う。Provider認証、MCP、Pluginは扱わない。
- **受渡し**: 選別済み設定とレビュー済みソースのみを渡し、変更結果はホストでレビュー後に明示的に採用する。

既存の `make setup`、`make sync-opencode`、`make sync-mcp` には接続しません。
`opencode/opencode.jsonc` とルート`opencode.json`は生成物なので編集しません。

## スタック構成

1. `feature/sandbox-runtime-scaffold-20261030` — 設定テンプレート・原則
2. `feature/sandbox-config-exporter-20261030` — エクスポーター・単体テスト
3. `feature/sandbox-snapshot-stage-20261030` — Sandboxへの明示的な転送・整合性検証
4. `feature/sandbox-opencode-runtime-20261030` — OpenCode v2の隔離ランチャーとPlugin登録雛形
5. `feature/sandbox-runtime-validation-20261030` — 設定・パッケージ整合性検証と実機確認手順（このブランチ）

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

**注意:** 生成結果で `plugins: []`・`mcp: {}` としているのは、**このエクスポーターがPlugin/MCPを出力しない**という意味です。OpenCodeの他の設定ソースや自動検出Pluginを無効化する保証ではありません。実Sandboxの有効設定は別途確認してください。

## 第3段：Sandboxへ転送する前の検査と明示的なステージング

`sandbox/scripts/stage_opencode_v2.py` は第2段の生成物を検証し、デフォルトでは転送しません。
`--apply` を指定した場合のみ、ローカルのDocker Sandboxへ `sbx cp` で一意な作業用ディレクトリをコピーし、ゲスト側PythonでもSHA-256と許可フィールドを検証します。

```sh
# 第2段で作成したスナップショットを検証（sbxを起動・呼び出ししない）
python3 sandbox/scripts/stage_opencode_v2.py --bundle /tmp/opencode-v2-export-20261030

# 既存のmountless Sandboxにだけ、明示的な適用オプションで転送（この例は実行しない）
python3 sandbox/scripts/stage_opencode_v2.py \
  --bundle /tmp/opencode-v2-export-20261030 \
  --sandbox oc-v2-poc --apply

# CI/ローカルの模擬テスト。実際のsbxは呼び出さない
python3 -m unittest discover -s sandbox/tests -p 'test_*.py' -v
```

- `--apply` は**OpenCode設定の有効化を意味しません**。Sandbox内の専用ステージングディレクトリに配置・検証するだけです。
- `sbx exec` は停止中のSandboxを起動する可能性があります。実際のSandboxを指定するのはオペレーターの明示操作に限ります。
- Docker Sandboxesの利用者とSandbox名は適用時に確定します。ホストの別ユーザー (`y_ohi` / `sbx-poc`) の権限を変更しません。
- 配備先は**mountless Sandboxを前提**とします。現時点でスクリプトは既存Sandboxのマウント一覧を証明していません。host mountのあるSandboxへ適用しないでください。
- `sbx cp` はディレクトリ転送時にUID・パーミッションを維持し得るため、秘密情報を含まない構成のみ、ゲストから読めるモードで一時ステージングします。
- 検証用Pythonスクリプトは設定スナップショットの**隣接ファイル**に配置し、3ファイルの厳格な整合性検査を維持します。ゲスト内の既存プロセスが悪意を持ってステージング内容を置換するような脅威に対する完全な耐改ざん性は証明していません。
- ゲスト検証に失敗した場合、配置済みの一時ディレクトリは自動削除しません。作業者が確認するまで保持してください。

これまでと同様、ホスト設定・ソースの正本を変更せず、ネットワークポリシー、MCP、有料Providerの設定も変更しません。
OpenCode起動時の設定読み込みとPlugin実動作は後続の検証対象です。

## 第4段：隔離XDG設定によるOpenCode v2実行構成

`sandbox/scripts/prepare_opencode_v2_runtime.py` を追加しました。第3段のスナップショットをゲスト内で検証し、
`--write` を指定した場合のみ新規の実行領域にServer側`opencode.jsonc`、TUI側`cli.json`、専用ランチャーを作成します。

ローカルのakane/sibylパッケージを指定した場合、名前・バージョン・エントリポイントを検査したうえで
それぞれServerとTUIの設定に登録します。OpenCodeプロセスの起動は明示的な別操作です。
通常Plugin登録の動作、実Sandboxへの適用・起動はまだ検証していません。

**詳しい手順と注意点:** [RUNTIME_V2.md](RUNTIME_V2.md)

## 第5段：通常Plugin登録の検証準備（実機未実施）

`sandbox/scripts/verify_opencode_v2_runtime.py` とオフラインテストを追加しました。
第4段の生成済み設定・receipt・Plugin exportsを**読み取り専用**で検証します。
明示的な`--probe-version`のみ、隔離ランチャーの`--version`を起動します。

この検証が成功しても、akane/sibylの実際の`setup()`やSidebar描画は未証明です。
必要な実機コマンドと判定条件は [VALIDATION_V2.md](VALIDATION_V2.md) に記載しています。
ホストOpenCode v1や既存のSandboxは自動で変更しません。

## Host `oc2` workflow

`sandbox/scripts/oc2.py` はHost側ランチャーです。PATHへの登録は自動では行いません。
[Cloudflare AI Gateway RESTの正本となる英語の運用手順](../docs/cloudflare-ai-gateway-rest.md)を使う場合は参照してください。
初回だけ、リポジトリのルートでリンクしてください。

```sh
mkdir -p "$HOME/.local/bin"
ln -s "$PWD/sandbox/scripts/oc2.py" "$HOME/.local/bin/oc2"
```

`$HOME/.local/bin` がPATHに含まれていることを確認してください。起動前にDocker Sandboxes CLIの
インストール済みバージョンと `sbx create --help` の `--clone` 対応を確認します。
Sandbox名が既に存在する場合は、再利用・再構築せず停止します。

Clone modeはホストのGit RepositoryをRead-onlyでGuestから見える状態にし、Guest内の別Cloneで
作業します。Dockerの仕様上、`.env`やGit除外ファイルもRead-only sourceに含まれます。
そのため `oc2` は安全走査から除外されるファイル、特殊ファイル、symlink、認証情報らしい内容が
あるWorkspaceをSandbox作成前に拒否します。`opencode.json`、`opencode.jsonc`、`cli.json`も拒否します。
Phase 1の実機確認では、**新規の無害なテスト用Git Repositoryだけ**を使ってください。
実プロジェクトには適用しないでください。

```sh
oc2 --version
oc2 --dry-run --workspace "$HOME/path/to/oc2-safe-test-repo"
cd "$HOME/path/to/oc2-safe-test-repo"
oc2
```

通常起動は新規のClone-mode shell Sandboxを作成し、Sandbox内へ `@opencode/cli@2.2.5`を導入します。
Hostの環境変数は継承せず、Sandbox専用のHome/XDG領域を使います。Provider、認証、MCP、Plugin設定は
渡しません。Workspace Snapshot、Manifest、ACL、Seed、collect/applyは実行経路に含めません。
Sandbox作成後に失敗しても、自動削除しません。

Docker Sandboxes `v0.49.2`はClone modeを提供することを確認済みです。`v0.50.1`も公式リリースですが、
Host CLIの更新はこの手順では行いません。OpenCode `v2.2.5`は公式リリースで、npm package
`@opencode/cli@2.2.5`をSandbox内に固定導入します。起動前に実行ファイルの`--version`が一致しなければ停止します。

実証Repositoryは実プロジェクトと独立した新規ディレクトリで作成します。検査で拒否された場合は
回避せず、安全なテストRepositoryを作り直してください。Sandbox名が存在する場合は別名を指定します。

```sh
test_repo=$(mktemp -d)
git -C "$test_repo" init
printf 'print("safe sandbox fixture")\n' > "$test_repo/main.py"
git -C "$test_repo" add main.py
git -C "$test_repo" -c user.name='OC2 Test' -c user.email='oc2-test@example.invalid' commit -m fixture
cd "$test_repo"
oc2 --repo-root "$HOME/dotfiles/components/dotfiles-ai" --sandbox oc2-phase1-test
```

TUIの操作確認後は `Ctrl+C` で終了します。Sandboxは残ります。既存Sandboxの再利用・削除が必要な場合は、
対象を確認したうえでHuman Ownerが別途判断してください。この実機テストはDocker Sandboxes `v0.49.2`の
Clone modeとOpenCode `v2.2.5`の起動だけを確認し、実プロジェクトでの機密ファイル非露出を保証しません。

`sbx diagnose` が `/dev/kvm: permission denied` を示した場合は、起動を迂回せず停止します。
Human Ownerが権限変更を承認した場合に限り、管理者が `sudo usermod -aG kvm "$USER"` を実行し、
完全にログアウトして再ログインした後、`sbx diagnose` と `id -nG` で反映を確認してください。
Docker Sandboxesの更新が必要と判断した場合も、この手順とは別に承認を得てください。

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
