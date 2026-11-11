# OpenCode Sandbox runtime — 設定と開発環境

> **Status: PHASE1_LIVE_PASS**
>
> このディレクトリは、ホスト管理・Sandbox実行に向けた設定雛形と、読み取り主体の限定的な設定エクスポーターです。
> `oc2`実行時は検査済みSnapshotだけを転送する新しいmountless Sandboxを作成します。既存Sandboxの再構築・削除、`sbx policy`変更、
> ホストOpenCode v1の更新、認証情報の転送は自動で行いません。
> `sandbox/` 配下のYAMLは、Docker Sandboxes公式スキーマではなく独自の設計用メタデータです。

## 責務と正本

- **Host**: `dotfiles-ai` の `apm.yml` を設定SSOTとし、プロジェクトのGitリポジトリを正本として保持する。
- **Sandbox**: `oc2`はOpenCode v2.2.5のTUIと、APMから選別したProvider設定を
  扱う。Docker Credential MixinでHost側Provider認証を仲介する。MCPとPluginは扱わない。
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

`sandbox/scripts/prepare_opencode_v2.py` は `apm.yml` の `opencode_v2` と
Provider定義を読み取り、許可された OpenAI と Cloudflare Custom Provider の設定だけを
OpenCode V2用に変換します。OpenAIを既定Providerとし、Cloudflareは既存の`/compat`
経路を使います。baseURL、Header、Guest auth、Provider policyはExporter、Stage、Guestの
各検証層で照合します。資格情報となる値は出力せず、Host側Docker Credential Proxyが
管理する固定placeholderだけを参照します。

生成ファイル：

- `opencode.jsonc`: OpenAIとCloudflare Custom Providerを含むOpenCode V2.2.5設定、deny-first Provider policy
- `cli.json`: 最小TUI設定、`plugins: []`
- `export-manifest.json`: ソース・出力ファイルのSHA-256、OpenCode固定バージョン

**対象外・未検証:** Plugin登録、MCP移植、Secrets Broker、Claude Agent。OpenAI ChatGPT OAuthの
Docker Sandbox上での交換・更新と、Provider設定の実OpenCode V2実行は未検証です。

外部の一時ディレクトリへ手動で出力する場合：

```sh
python3 -m pip show PyYAML  # 依存が既存環境にあることを確認（インストールしない）
OUT="${TMPDIR:-/tmp}/opencode-v2-export-20261030"
python3 sandbox/scripts/prepare_opencode_v2.py --out "$OUT"
python3 sandbox/scripts/prepare_opencode_v2.py --out "$OUT" --check
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
# --bundle には一時ディレクトリ内の生成名だけを指定する
python3 sandbox/scripts/stage_opencode_v2.py --bundle opencode-v2-export-20261030

# 既存のmountless Sandboxにだけ、明示的な適用オプションで転送（この例は実行しない）
python3 sandbox/scripts/stage_opencode_v2.py \
  --bundle opencode-v2-export-20261030 \
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

これまでと同様、ホスト設定・ソースの正本、MCP設定、CloudflareのCustom Provider定義は
変更しません。Provider設定は`apm.yml`から選別してGuestへ配置します。
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
[OpenCode V2のProvider導線に関する英語の正本](../docs/opencode-v2-provider-routing.md)を使う場合は参照してください。
初回だけ、リポジトリのルートでリンクしてください。

```sh
mkdir -p "$HOME/.local/bin"
ln -s "$PWD/sandbox/scripts/oc2.py" "$HOME/.local/bin/oc2"
```

`$HOME/.local/bin` がPATHに含まれていることを確認してください。起動前にDocker Sandboxes CLIの
インストール済みバージョンと `sbx create --help` の `--kit` 対応を確認します。
Sandbox名が既に存在する場合は、通常起動では再利用・再構築せず停止します。Cloudflare credential確認に失敗した作成済みSandboxは、同じWorkspaceとSandbox名で`--resume`を指定するとSession receiptを照合して再開できます。

通常起動はHost Workspaceをmountせず、検査済みSnapshotだけをGuestへコピーします。
`.git`、認証情報を含むファイル、symlink、特殊ファイル、未承認のOpenCode設定は転送しません。
残ったファイルにCredential検出が一致した場合はSandbox作成前に停止します。

Workspace originが正確に `yohi/dotfiles-ai` の場合だけ、Workspace Safe Transfer Profile R1を適用します。
R1の除外は他のRepositoryには適用されません。一般的な秘密ファイル・Credential検査は全Repositoryで実施します。

- 検査を通過した`apm.yml`はSnapshotに含まれ、Guestへ転送されます。OpenCode V2設定の生成にはHost側SSOTも使用します。
- Guestでの`apm.yml`編集・新規作成はサポート対象外です。Guestで作った`apm.yml`はcollect/apply対象になりません。
- `_docs/aws-resource-inventory.md`、`_scripts/generate_atlassian_auth.py`、
  `.agents/skills/claude-api/csharp/claude-api/README.md`、
  `sandbox/tests/test_v2_provider_security.py`もGuestへ転送しません。
  内容の安全性を確認したという意味ではありません。
- ローカル生成物、明示したWorkspace固有ファイル、およびSSOTへのsymlink adapterは転送しません。
  それ以外のsymlinkやCredential検出対象は引き続きFail-Closedです。

実機確認では、**新規の無害なテスト用Git Repositoryだけ**を使ってください。
実プロジェクトへの適用は、個別の受入確認が終わるまで行わないでください。

```sh
oc2 --version
oc2 --dry-run --workspace "$HOME/path/to/oc2-safe-test-repo"
cd "$HOME/path/to/oc2-safe-test-repo"
oc2 --allow-paid-inference
```

このAPM設定は外部Providerを選択するため、通常起動には
`--allow-paid-inference`による起動ごとの明示承認が必要です。
未指定の場合はSandbox作成前に停止します。

通常起動はDockerのv3 shell workloadとCredential Mixinを使って、新規のmountless Sandboxを作成します。
Credential MixinはHost側の認証仲介を担当します。OpenCode v2.2.5 standalone BinaryはHostが公式GitHub Release APIから取得し、
APIのサイズ・固定SHA-256・Archive構造を検証した後に`sbx cp`でGuestへコピーします。
Host PATHへはインストールせず、Guest内の`npm install`やKit build時のnpm Registry接続も行いません。
新しいSandboxを作るたびに約119 MBの公式AssetをHostから取得します。Docker Hubのshell workload取得は別途必要です。
Hostの環境変数は継承せず、Sandbox専用のHome/XDG領域を使います。Provider設定と一時
Docker Credential Mixinを配置します。実CredentialはGuestへコピーせず、DockerのHost側
Proxyと対話型Credential Bindingで扱います。OpenAI ChatGPT OAuthの実Sandbox上の交換・
更新は未検証です。実行前に案内を確認してください。MCP、Plugin設定は渡しません。
Workspace Snapshot、Manifest、ACLによる限定転送を行います。Guestでの作業をHostへ反映する場合は、
Session receiptに基づくcollectと明示的なapplyが必要です。Profileで除外したパスは書戻し対象になりません。
Sandbox作成後に失敗しても、自動削除しません。

Docker Sandboxesはv3形式の公式Shell workloadを使います。OpenCode `v2.2.5`は公式Linux x64 Release
AssetからHostのprivate temporary directoryへ取得し、GitHub Release APIのサイズとSHA-256で検証します。
Hostへのインストールやnpm Registry利用は行いません。Kitから起動する前に実行ファイルの`--version`を確認します。

実証Repositoryは実プロジェクトと独立した新規ディレクトリで作成します。検査で拒否された場合は
回避せず、安全なテストRepositoryを作り直してください。Sandbox名が存在する場合は別名を指定します。

```sh
test_repo=$(mktemp -d)
git -C "$test_repo" init
printf 'print("safe sandbox fixture")\n' > "$test_repo/main.py"
git -C "$test_repo" add main.py
git -C "$test_repo" -c user.name='OC2 Test' -c user.email='oc2-test@example.invalid' commit -m fixture
cd "$test_repo"
oc2 --repo-root "$HOME/dotfiles/components/dotfiles-ai" --sandbox oc2-phase1-test \
  --allow-paid-inference
```

TUIの操作確認後は `Ctrl+C` で終了します。Sandboxは残ります。既存Sandboxの再利用・削除が必要な場合は、
対象を確認したうえでHuman Ownerが別途判断してください。この実機テストはDocker Sandboxes `v0.49.2`の
検査済みSnapshotの転送とOpenCode `v2.2.5`の起動を確認し、実プロジェクトでの機密ファイル非露出を保証しません。

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
