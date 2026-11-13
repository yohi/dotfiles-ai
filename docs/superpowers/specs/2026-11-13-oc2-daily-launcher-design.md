# OC2 Daily Launcher — Design R0.1.3

- Date: 2026-11-13
- Repository: `yohi/dotfiles-ai`
- Baseline: `master` at `e79573903f1a2b550e32bc6022d91c43fdcccbb4`
- Status: **R0.1.3 F-004 Guest Writer cgroup Freezer limited design clarification; full design adoption and implementation remain pending Human Owner decision**
- Scope: **Design only**. This document does not authorize implementation, Sandbox changes, Credential changes, PR creation, or Merge.

## 1. 背景と目的

Phase 5で実装したOpenCode v2 Runtime、APM Full SSOT、Superpowers、Akane、Sibyl、MCP、Host Credential Proxyを活用し、日常の開発を`oc2`だけで開始できるようにする。

ユーザーはGitリポジトリのルートから`oc2`を起動する。Launcherは正しいOpenCode v2のバージョン、APM Runtime設定、認証、既存Sandbox、Workspace同期状態を自動選択する。AIの変更はSandboxに隔離し、終了時に差分とCommitを収集して、Human Ownerの**1回の承認**でHostへ反映できるようにする。

隔離性だけを追求して日常操作を複雑にしたり、使いやすさのためにHostのソースや`.git`を無条件に書き換えたりしない。

## 2. 既存実装と変更境界

`master`の既存資産を再利用する。

- `sandbox/scripts/oc2.py`: Host Launcher、固定CLI検証、Sandbox起動、Provider認証。
- `sandbox/scripts/oc2_native.py`と`prepare_opencode_v2.py`: APMの検証・Runtimeへの設定反映。
- `sandbox/scripts/oc2_guest.py`: Guest側の設定・Asset・Plugin検証。
- `sandbox/scripts/oc2_workspace.py`と`oc2_workspace_ops.py`: Snapshot、変更検出、衝突検出・限定適用。
- `sandbox/scripts/oc2_session.py`: Workspaceごとの転送Receipt。
- `apm.yml`: User-configurable Runtime設定のSSOT。

現在の通常起動は固定バージョン`2.2.5`、既定Sandbox名`oc2-v2`、既存Sandbox名の再利用拒否、およびMountless Snapshot転送を前提としている。PATH登録は手動であり、Workspaceの自動再同期、Git履歴のGuest利用、終了時の自動Collect/Apply導線は日常利用に不足している。

これらの**起動・同期・セッション管理**を拡張する。既存Phase 5 Runtimeや安全境界を全面的に再実装しない。

## 3. アプローチ比較と採択

| 方式 | 利点 | 制約 | 判定 |
| --- | --- | --- | --- |
| A. Mountless + Snapshot自動同期 + 選択的Git Bundle | Hostへの直接書込みを防ぎ、既存の安全機構を活用できる。Git履歴と未Commit状態を扱える。 | 安全な同期・履歴転送・競合処理の実装が必要。 | **採用** |
| B. Docker Clone Mode + Git同期 | Git履歴を自然に利用できる。 | HostのGit内容の公開範囲、Worktree、未追跡ファイル、同期運用が制約となる。 | 非採用 |
| C. Direct Mount | 編集結果がHostへ即時反映され操作は簡単。 | Hostのファイル・Gitへの誤編集と多重起動競合を防ぎにくい。 | 非採用 |

Git履歴が使えないSnapshot+`git init`のみの方式も、普段の開発に必要な`git log`やCommit継続性を満たさないため採用しない。

## 4. 通常の操作とCLI契約

```sh
cd ~/program/nexus
oc2
```

- `oc2`: カレントGitリポジトリのルートをWorkspaceにし、互換性のある未使用Sandboxを選択してTUIを起動。
- `oc2 --new`: 既存Sandboxを破壊せず新規Sandboxを選択。
- `oc2 --status`: Workspaceに紐付くSandbox、占有、同期・未反映変更、Runtime IdentityをSecretなしで表示。
- `oc2 --dry-run`: 設定と選択予定を検証・表示し、Sandbox作成、Credential変更、推論、ファイル同期を行わない。
- `oc2 --version`: APMで選択されたOpenCodeバージョンを表示。

`oc2`のPATH設定は初回に標準化する。通常使用では`--workspace`、`--sandbox`、手動`sbx cp`、手動Collect/Applyを要求しない。診断・保守用の明示オプションを残してよい。

## 5. APM SSOTとOpenCode Version — F-001限定訂正

ユーザー指定バージョンは既存`apm.yml`の`x-oc2-runtime.opencode.version`を唯一の選択元とする。他の既存Runtime設定は維持する。

```yaml
x-oc2-runtime:
  enabled: true
  opencode:
    version: "2.2.5"
  theme: tokyonight
  # 既存watchdog / sibylObserver等は保持
```

### Version Lockの所有・保存・検証

- **APM = 選択の正本、Version Lock = 実行可能Artifactの信頼済み許可リスト。** 両者を同一視しない。
- リポジトリ管理のLockパスは`sandbox/locks/opencode-cli-v2.json`とする（実装時に新規作成）。JSON UTF-8、重複キー拒否、余剰キー拒否。トップレベルは`{"schema":"dotfiles-ai/oc2-cli-lock/v1","entries":[...]}`。
- `entries`の各要素は**厳密に**`version`（SemVerの`MAJOR.MINOR.PATCH`）、`os`（現段階は`linux`のみ）、`arch`（`x86_64`のみ）、`asset_url`（公式`github.com/anomalyco/opencode` ReleaseのHTTPS固定URL）、`archive_size`（正整数）、`archive_sha256`（64桁hex）、`member_path`（`opencode`固定）、`binary_size`（正整数）、`binary_sha256`（64桁hex）を持つ。(`version`,`os`,`arch`)は一意、ソート順を検証する。
- Host上の**承認済みLock Digest**を`$XDG_STATE_HOME/oc2/trust/approved-cli-lock-sha256`（`XDG_STATE_HOME`未指定時は`~/.local/state/oc2/trust/approved-cli-lock-sha256`）にユーザー所有、ディレクトリ0700・ファイル0600で保存する。DigestはLockファイルの**生バイト**SHA-256であり、APMまたはGuestから変更できない。初期承認値も明示的なOwner操作で設定する。値がない・一致しない場合は起動しない。
- Ownerによる新バージョン登録は、公式Releaseの取得元・Archive Size/SHA-256・展開MemberとBinary Size/SHA-256を独立に確認した後、LockをGit上で変更し、**別途Host信頼Digestの更新を明示承認**する二段階とする。通常の`oc2`起動、Guest、AIのCommit、GitのMergeだけでは承認Digestを変更できない。旧Digestでの検証なしに自動信頼更新しない。
- Launcherは`apm.yml`のVersion、Host Platform、承認済みLockを照合してからダウンロード／再利用し、ArchiveのURL（redirect先ホストも許可リスト）、Size、SHA-256、Member構造、展開済みBinaryのSize・SHA-256を確認する。Guestは受領した検証済みVersion/Platform/Binary Identityと実行する固定パスを照合する。バージョン文字列の`--version`結果**だけ**をArtifact同一性の証拠としない。
- Version/OS/Arch/Lock Digest/Artifact Digestを検証済みHost→Guest ManifestおよびRuntime Identityへ反映し、Launcher、Exporter、Guestで完全一致させる。別々の固定Version定数を独立した設定として残さない。
- 未登録Version、未承認Lock、Platform不一致、Asset転送元不一致、Archive/Binary Digest不一致、Host/Guest Version不一致、Manifest不一致は**Fail-Closed**。代替Version・最新Version・Providerへの自動Fallbackなし。

### 既存v2.2.5からの移行

現行`oc2.py`の`VERSION`・固定Asset URL/Size/SHA-256、`prepare_opencode_v2.py`の`OPENCODE_VERSION`、`oc2_guest.py`の固定Version、`oc2_native.py`の固定許容キーを、同一の検証済みLock選択経路へ置換する。既知のArchive値は既存固定値と照合して初期Lockへ転記する。**Binary SHA-256は、正しいArchive SHA-256を検証した公式配布物から算出・照合すること**（既存R5の観測Hashを無根拠に期待値として採用しない）。初期Lockと信頼Digestの承認が完了するまで新経路を有効化しない。旧SandboxはVersion/Artifact Identityが一致したときだけ再利用可能とし、自動書換えを禁止する。

Models/Providers/Agents/Plugin/MCP/Rules/Commands/Skills/Theme/Timeout/Akane・Sibyl Optionsは既存Full SSOTの契約を継承する。

## 6. Sandbox自動選択・多重起動 — F-002限定訂正

### 識別子とHost永続レイアウト

- `WorkspaceID`: `sha256(uid || NUL || canonical_host_git_root)`の先頭32桁hex。Host上の解決済みGitルートに紐付け、任意の作業ディレクトリ名だけで同一視しない。
- `SandboxID`: Dockerが返すUUID。Sandbox名とは独立して検証する。
- `SessionGeneration`: 起動・同期のたびに生成するUUID v4。Hostが生成し、同一Workspaceの複数Sandboxでも一意。
- `SessionKey`: (`WorkspaceID`,`SandboxID`,`SessionGeneration`)の組。Baseline、差分、Git収集、承認、LeaseはこのKeyへ帰属させる。

永続状態Rootは`$XDG_STATE_HOME/oc2`（未指定時`~/.local/state/oc2`）。Workspace外・ユーザー所有・0700、各ファイル0600、symlink/所有者不正を拒否する。

```text
$XDG_STATE_HOME/oc2/
  workspaces/<workspace-id>/
    inventory.json
    lock
    leases/<sandbox-id>.json
    sessions/<session-generation>/
      receipt.json
      baseline.json
      git-baseline.json
      collection/              # immutable after collection
      apply-journal.json       # created only when applying
  trust/approved-cli-lock-sha256
  policy/inference-v1.json
```

- `inventory.json`は`WorkspaceID`、canonical path、Sandboxの(`name`,`id`,Version/CLI/Runtime Identity,Generation,状態)を記録する。
- `receipt.json`はschema `dotfiles-ai/oc2-session/v3`、SessionKey、Remote Project Path、Baseline Digest、Sandbox/Runtime Identity、状態遷移を格納する。状態は`PREPARING → READY → RUNNING → COLLECTED → APPLIED`、または`PENDING`/`RECOVERY_REQUIRED`。戻り遷移と重複Applyは拒否する。
- `baseline.json`はWorkspace Snapshotの基準、`git-baseline.json`は§7-8のGit基準、`collection/`はGuest成果。既存Receipt固定名をWorkspace直下で共有しない。
- LeaseはSandboxIDごとに保持し、Owner UID、Launcher PID＋開始時刻、SessionGeneration、SandboxID、取得時刻、状態を記録する。PIDが存在するだけでは生存の証拠としない。

### 選択・占有と異常終了

1. Workspace単位のHost `flock`で、Inventory検証→Sandbox選択→Lease割当→Session v3作成を**排他的**に処理する。同時起動は別Generationとなる。
2. 互換性判定はWorkspaceID、SandboxID、Mountless/Runtime Mountなし、Version/Artifact/Runtime Identity、既存Guest Project/Session receipt整合、未反映変更の有無を含む。
3. 空き・整合済みSandboxのみ再利用する。使用中なら別Sandboxを作る。Sandbox作成途中に失敗した場合も不完全状態を残し、同一名の別実体を誤再利用しない。
4. TUI終了時、まず差分を収集・確定してからLeaseを解放する。未反映変更があるSandboxは`PENDING`とし、**自動再利用対象から外す**。HostへのApply前に別`oc2`を開始する場合は、安全な独立Sandboxを選択する。
5. Launcher異常終了時、次回はHost PID＋開始時刻、Docker Sandbox ID、Guest実行プロセス/Receiptを照合する。生存/状態の判別不能時はLeaseを自動回収せず`RECOVERY_REQUIRED`で隔離。明確に停止済み・Guest成果保全済みと確認できた場合だけOwnerの確認を伴う回収経路で復旧する。孤立Sessionを削除しない。

### Session Writer実行境界（F-004）

- 各`SessionKey`に属するGuest開発作業の全Writer（OpenCode本体、Plugin/MCP、Spawnされた子孫、Background Job）は、実行開始時から同じSession専用のcgroup v2 Writer Groupに閉じ込める設計とする。別SessionのcgroupやHost側Workspace/Apply Gateを兼用しない。後から既存PIDを移送するだけの方法は、移送前の書込み・子孫の取り残しを排除できないため、本番の完全性保証には用いない。
- Guest Supervisor/CollectorはWriter Groupの外側に置き、Launcherが`SessionKey`、Sandbox ID、Writer Group Identity、Leaseと対応を検証する。Collectorは収集元のGuest Git Repository/Working Treeを変更できない読取り専用境界を必要とし、成果の出力先はSession専用の別領域に限定する。
- Writer Group外から同じ収集元を書き換えられるGuest主体、権限昇格・cgroupからの移動、Supervisor/Collectorによる再起動・書込みなどを禁止・検出できる制御境界が確立できなければ、**通常の自動Collect/Collection確定を有効化しない**。専用cgroupの作成と`frozen 1`だけを、全Writer封じ込めの証拠にしてはならない。
- Guest Writer境界とHost Apply復旧のWorkspace Gateは別の条件であり、双方がPASSした場合だけ収集・適用を進める。

### Workspace復旧中の全Session遮断（F-004）

Workspace全体のHost Apply状態（`HostApplyGate`）は、全SessionGenerationの`apply-journal.json`とWorkspace単位のApply排他ロックを根拠に判定する。**`PREPARED`・`APPLYING`・`RECOVERY_REQUIRED`のJournal、または終端を検証できないJournalが1件でも存在する間は、同一Workspaceについて既存・新規を問わず、いかなるSessionも新しいHost Snapshot/Baselineを採用してはならない。** `oc2 --new`で独立Sandboxを作成することも、この禁止を回避する手段にならない。読み取り専用の診断・復旧情報表示は許す。

- 起動直前にWorkspace排他ロック下で全Journalを照合する。Apply開始は同一ロックでGateを閉じ、新規Sessionとの競合を排除する。旧Sessionが`PENDING`であることだけを根拠にHost Applyが進行中とは判定しない。
- **Guest PENDINGのみ・Host Apply Journalなし／正常終了・Host状態検証PASS:** 既存Sandboxの未反映成果は保全し、Hostの安定状態を基準にした別Sandboxの新規Sessionは許可する。
- **Host Apply途中停止・復旧要求・Journal状態不明:** Workspaceを`HOST_RECOVERY_BLOCKED`扱いとして全新規Session/Host Snapshot採用/Applyを禁止する。Guest PENDINGや別Sandboxの利用可否とは独立したWorkspace全域のGateとする。
- Gate再開は、Undo Journalの復旧手続きでHost HEAD/Index/Working Tree・未追跡ファイルの整合を検証し、Journalを`APPLIED`または復旧完了の終端状態へ永続化した**後だけ**許す。復旧不能なら禁止を維持し、原本・Journal・Collectionを保護する。単なるPID消滅、Sandbox停止、Journal削除は復旧完了の証拠にならない。

**旧v2 Receipt移行:** 従来の`workspaces/<workspace-id>/baseline.json`/`receipt.json`相当のWorkspace単位Session v2は読み取り専用Legacyとして保護し、v3へ暗黙変換・上書きしない。Legacyに未回収・未適用変更がある場合はそのSandboxの通常再利用を停止し、独立Sandboxへ分岐またはOwnerに判断を求める。旧状態の移送が必要な場合はOwner承認の明示操作とする。

## 7. Workspace Snapshotと再利用時の同期 — F-003限定訂正

HostのWorkspaceディレクトリはGuestへ直接マウントしない。Gitルートはsymlinkでない正規化パスとし、Snapshotの前後で同一Identityを確認する。

### Git Baseline（Snapshotとは独立）

SessionGenerationごとに、以下を決定論的に記録し、全体SHA-256をReceiptに格納する。

- `head_oid`（40/64桁Git OID）、`branch_ref`（symbolic HEADの完全Ref）、`object_format`（SHA-1/SHA-256）、`index_oid`（生IndexバイトのSHA-256）、`index_entries`（`git ls-files --stage -z`の正規化レコード、mode/blob OID/stageを含む。**intent-to-addフラグはこのコマンドだけでは判定できない**）。
- `staged_delta`（HEAD→Index）、`unstaged_delta`（Index→Working Tree）、`untracked_files`（`git ls-files --others --exclude-standard -z`に相当する安全なファイルのPath/Mode/Size/SHA-256）。区分を混合しない。
- `working_manifest`（既存ファイルSnapshot Manifest）、`transfer_policy_id`、各差分のSHA-256。IndexとWorking TreeがGit HEADに対してdirtyかを別々に記録する。

**intent-to-addは現段階では未対応とし、検出したらGuest起動前にFail-Closedする（F-003方式B）。** 判定は`git ls-files --stage -z`の結果から推測しない。Hostで`git -C <canonical_host_git_root> rev-parse --git-path index`によりIndexパスを解決し、読み取り専用の厳密なGit Index ReaderでIndexヘッダー、エントリ、通常フラグ、拡張フラグ（`CE_INTENT_TO_ADD`）とChecksumを検証する。サポート対象は検証可能なIndex v2/v3とし、intent-to-addの存在、未知のEntry/Extension、v4、Split/Sparse Index、検証不能なIndex形式、Indexパスの不正・読み取り失敗時は**拒否**する。ReaderはIndexの正規化・書き換えを行わず、読み取ったIndex生バイトSHA-256を`index_oid`と照合する。取得コマンドと検査方法はImplementation Planでこの境界のまま具体化し、未対応状態を正常なStaged状態に変換しない。

`git diff --cached`と`git diff`、Index entries、Snapshotの結果が同一瞬間を示すまで再照合する。衝突状態のIndex（stage 1/2/3）、unborn HEAD、Submodule、Git Object代替格納など現段階で復元を検証できないケースはGuest起動前にFail-Closedする。Ignored/除外/Secretファイルは転送しない。対象外ファイルはGuestに存在するかのように再現せず、部分的なGit状態であることを明示する。

### Guest復元と三者比較

1. 許可済みGit BundleをGuestの独立Repositoryへ取り込み、同じHEAD OID/Branchから開始。
2. Guest IndexをHostのStaged状態へ再構成し、その上にUnstaged変更と安全なUntrackedファイルを適用する。結果のHEAD/Index entries/Staged delta/Unstaged delta/Untracked ManifestをHost Baselineと比較し、不一致なら起動しない。
3. Sandbox再利用時には**Base（前回正常同期時）、現在のHost、現在のGuest**をHEAD・Index・Working Tree・Untrackedの各層で比較する。Guestの未反映変更があれば自動上書きせず`PENDING`扱いにする。Hostのみ変更された場合に限り、差分を安全に同期して新GenerationのBaselineへ更新する。
4. HostとGuestがともに変更されている場合、経路ごとのファイルHashが一致してもGit層（Stage/Commit）の競合があれば停止し、Owner承認なしにMerge/Rebase/Resetしない。

GuestのCommitは**Session開始後のCommit OID集合とParent関係**でHostから転送した履歴と区別する。Host由来の未Commit変更がGuest Commitへ含まれた場合、それを再びUncommitted差分として二重適用しない。Guest最終状態は`base HEAD → Guest commits → Guest final Index/Working Tree`の単一状態として計算する。Host baselineがdirtyの場合のCommit取込みの保留条件は§10に従う。

## 8. Sandbox内のGit履歴・Commit — F-003限定訂正

Mountlessを維持したまま、**選択的Git Bundle**からGuest内に独立したGit Repositoryを構築する。

- Hostの`.git`はマウント・丸ごとコピーしない。GuestにはHostのSSH Agent、Git Credentials、Remote Push権限、任意の外部Remoteを与えない。
- Bundleで転送するRefは**Session開始時の検証済み`HEAD`のCommit OIDのみ**とし、必要な祖先とTree/Blob到達Objectだけを含める。Remote-tracking Ref、Tag、無関係なBranch、Stash、Reflogの輸送を禁止する。
- Git Bundleの`list-heads`、`verify`、Object整合検証に加え、転送可能なReachable Objectの全量・サイズと履歴中のBlobに対するSecret/除外ポリシーを検査する。**現在のWorking Treeが安全でも過去のCommitが安全とは限らない。** 完全に検査できない場合は履歴転送を停止し、密かに非Gitモードへ退避しない。
- Host SnapshotとGit Bundleは別々に転送・Digest照合する。GuestのHEAD/Branch/Index/Working Treeの一致が取れるまではTUIを起動しない。
- Guest内で`git status`、`git diff`、`git log`、Branch作成、`git commit`を利用可能とする。Guestが別Branchに移った場合や非Fast-forward Commitを作った場合もCommitは収集対象に残し、Hostへ無断で反映しない。
- Collectでは、Host由来の転送済みCommitとGuest新規CommitをOIDとParent関係で識別し、Guestが最終HEADに含めたHost未Commit内容と残存Unstaged差分を**二重計上しない**。Guestに複数の未統合Branchがあれば明示的に収集候補を表示し、現在HEAD以外を無条件にApplyしない。

Commitを取り込める条件、Dirty Baselineでの保留、Hostへの順序は§10で固定する。

## 9. 認証とProvider — F-005限定訂正

`apm.yml`はモデルとProviderの**設定選択**のSSOTであり、課金可能な外部推論の**操作許可**は別権限とする。Host Credential ProxyとDocker Credential Bindingを維持し、OpenAI OAuthおよびCloudflare AI GatewayのSecretをGuest設定・Git・Snapshotへ平文転送しない。

### Host継続許可ポリシー

- 保存先: `$XDG_STATE_HOME/oc2/policy/inference-v1.json`（未指定時は`~/.local/state/oc2/policy/inference-v1.json`）。`schema=dotfiles-ai/oc2-inference-policy/v1`、Host Launcherのみが作成・変更し、所有者UID一致、ディレクトリ0700・ファイル0600、symlink/不明Schema/不正値は拒否する。
- 1 Grantの厳密なスコープは**Host UID、WorkspaceID＋正規化Host Path、Provider ID、非Secret Account IdentityのFingerprint、明示的なModel ID集合、承認時刻、失効時刻（UTC）、grant_id**。Credential本文/Tokenを保存しない。
- 初回は`oc2`のTUI起動前に、APMで実際に選択されたProvider/Modelごとの対象と外部推論・課金の可能性を表示し、端末で明示承認する。承認されるまで当該Providerを使うRuntimeを起動しない。非対話・拒否の場合は`INFERENCE_NOT_AUTHORIZED`で停止する（推論・課金なし）。
- Grantは**30日以内**の有効期限を持つ（初回既定30日、長期無期限は不可）。承認済みの同一スコープでは後続の通常`oc2`は再質問しない。失効・明示取消・Account/Workspace/Provider/Model許可範囲変更時は再承認が必要。
- 取消操作は明示的なHost CLI `oc2 --revoke-inference`とし、対象WorkspaceのGrantを無効化する。期限・取消・破損は次回Launcher起動時にFail-Closed。既に動作中の推論を即座に強制停止する機構ではないことを明示する。
- Provider一覧への登録、Credentialの存在、Docker Brokerの利用可能性は推論許可ではない。`apm.yml`の選択と有効Grantの**積集合のみを通常のOpenCode Runtimeのモデル選択候補へ公開**する。許可外Provider/Modelが通常のTUI/設定経由で選択可能になる場合はRuntime起動を拒否する。APM追加だけで既存Grantを拡張しない。**HTTP通信中のModel ID強制認可まで保証するものではない**（責務と残余リスクは以下）。
- Cloudflare AI GatewayはAPM選択に従って自動解決し、別途`--use-cloudflare-ai-gateway`の常用を不要にする。Account識別子・SecretのHost ScopeとProxy Bindingを照合する。欠損・期限切れ・不整合時に別AccountやOpenAIへFallbackしない。
- 既存`--allow-paid-inference`の起動単位許可は新ポリシーへ自動移行せず、移行後の通常`oc2`は本Grantを使う。明示的な互換オプションを残す場合も範囲外の権限昇格を許さない。
- OpenCode v1の認証情報、設定、利用許可には影響しない。

### Grant Enforcementの責任主体・保証範囲（F-005）

| 境界 | Owner | 強制内容 | 保証しないこと |
| --- | --- | --- | --- |
| 起動前のGrant認可 | **Host Launcher（許可判定のAuthority）** | 保存されたGrantの期限・取消・UID/Workspace/Account/Provider/Model集合を検証し、不許可時は推論可能なRuntimeを開始しない | 起動後の任意HTTP RequestのModel ID解析 |
| 通常のモデル選択 | **OpenCode Runtime/Provider設定エクスポータ（通常UIのEnforcer）** | APMと有効Grantの積集合だけを構成・モデル一覧に採用し、未承認Provider/Modelが通常UI/設定経由で利用できる場合はFail-Closed | Pluginが独自HTTP Clientを使う場合の通信内容 |
| Credential・送信先 | **既存Credential Proxy/BrokerおよびDocker Network Policy** | 承認されたCredential Bindingと通信可能Host/Domainを制御 | リクエストBodyのModel ID、許可済みHost内の別Modelへの振替 |
| Trusted Plugin | **既存Phase 5のPlugin権限境界** | 既存のPlugin許可・実行制約を維持 | Pluginが通信権限を使ってOpenCodeの通常モデル選択を迂回する可能性 |

**採択済み保証:** 通常のOpenCode TUIと生成Runtimeのモデル選択では未承認Provider/Modelを利用させない。Host LauncherはGrant失効や構成不一致を起動時にFail-Closedする。一方、**Credential Proxy/Network PolicyはModel-awareの通信Enforcerではない**。許可済みDomainを使うTrusted Pluginや他のGuestプロセスが独自HTTP要求を送れる場合、許可外のModel IDをリクエストする可能性を完全には排除できない。認証情報が直接渡らない通信経路は保護されるが、許可済みProxy経由の任意Payloadに対するModel ID検査は保証しない。

**設計境界と残余リスク:** 現行のHost Launcher＋生成Runtime＋Credential/Network境界による保証は、**通常UI/設定に限定**する。全Guest通信に対するProvider/Model単位の強制認可・稼働中Grant取消・課金上限保証は未達成・未検証と記録する。既存Phase 5 Trusted Pluginの通信権限を事実に反して制限済みとは扱わない。これを満たすためのModel-aware Proxy/Gateway追加、Plugin無断削除・権限変更は**未採択**であり、必要時はHuman Ownerの別途判断を要する。意図しない推論・課金が起こり得る残余リスクをOwnerに明示し、未承認モデルが通常のOpenCode操作から選択可能となる構成は採用しない。

継続Grantは起動操作を簡素化するものであり、外部送信・課金ゼロや予算上限を自動保証するものではない。

## 10. TUI終了後のCollect / Preview / Apply — F-004限定訂正

TUI終了時にCollectとPreviewを自動実行するが、**Host ApplyはHuman Ownerの承認まで絶対に実行しない**。対象はSessionKeyで固定したGuest最終HEAD、Guest新規Commit OID群、最終Index/Working Tree/Untrackedの集合であり、最新状態を再取得して黙って差し替えない。

### 10.1 収集と候補の固定

**採用候補Mechanism（F-004）:** **Session専用cgroup v2 FreezerによるGuest Writer凍結＋独立Collectorによる読取り専用回収**を限定設計として選択する。TUI終了は必要条件だが十分条件ではない。Sandbox全体を`sbx stop`してから`sbx cp`する方式は採用しない（Docker Sandboxes v0.51.0/v0.53.0で、停止中`sbx cp`がSandboxを起動することを実測）。Freezerで全Writerを確実に覆えるか、Collectorの読取り専用境界が成立するかは**本番未検証**であり、成立するまで通常の自動CollectとHost ApplyをHOLDする。

**限定PoCの証拠範囲（2026-11-13）:** v0.53.0の使い捨てMountless Sandboxでは、専用子cgroupに所属させた単一テストWriterが`frozen 1`となり、凍結中の`sbx cp`成功、HEAD/Index/Working Tree/UntrackedのManifest一致（`DIFF_EXIT=0`）および`git fsck`成功を観測した。これは**テストWriterに限るPASS**であり、OpenCode/Trusted Plugin/MCP/任意Background Writerの封じ込め、Root権限からの脱出防止、Collection確定・Host Applyの安全性を証明したものではない。

**責務と強制境界:**
- **Host Launcher（Authority）:** SessionKey/Lease/Sandbox ID/Runtime Identityに結び付いたWriter GroupとCollectorの分離を起動前に検証し、未構築・不一致なら推論可能なTUIと自動Collectを開始しない。別SessionのWriter Groupを流用しない。
- **Guest Supervisor（Writer管理）:** OpenCode・許可済みPlugin/MCP・子孫・Background Jobの全てを**初回Spawn前**からWriter Groupへ所属させ、Group外への生成・移動・脱出・再Spawnを禁止できる境界を保持する。特権プロセスや任意Guest HTTP Clientが収集対象へ書き込める状態も見逃さない。全Writerの封じ込めを証明できない場合はFail-Closedする。
- **Guest Collector（非Writer）:** Writer Groupの外側で稼働し、収集元のGit Objects/HEAD/Index/Working Tree/Untrackedに書き込まない。Bundle/Manifest生成は別の専用ステージング領域へ行い、Git読取り処理が元RepositoryにLock・Index更新・Cleanupなどの副作用を残さないことを検証する。書込み不能・Group外Writer不存在の保証がない場合はCollectを確定しない。
- **Host Collector:** `sbx cp`でSandbox稼働中に収集物をHostのWorkspace外・Session専用私有領域へ移し、Digest/Identity/Commit到達性/Manifestを検証してから不変Collectionを確定する。Guestの生Credential・禁止Objectを輸送しない。

**状態遷移・実行順序（以下の順序を変更しない）:**
1. TUI終了を確認し、Supervisorが同Sessionの追加Spawn・再起動経路を遮断する。Writer Group全体に属するプロセス/子孫と、Group外から収集元を書き換えられる主体の不存在を確認する。確認不能なら以後の確定手順へ進まない。
2. SupervisorがSession専用`cgroup.freeze=1`を設定し、`cgroup.events`の`frozen 1`を確認する。単なるPID消滅、一定時間のHash一致、`sbx stop`、`cgroup.freeze`への書込み成功だけでは静止の証明としない。
3. Collectorが非Writer側の独立境界から、Git HEAD/Branch/Commit OID/Index生バイト、Staged/Unstaged/Untracked、File Manifestを読取り専用に記録する。必要な選択的Git Bundleは専用ステージング領域で生成・検証し、収集元への副作用とSecret/除外Objectを拒否する。
4. 凍結状態とWriter Group Identity/所属・外部Writer不在が維持される間だけ、稼働中Sandboxから`sbx cp`でステージング成果をHostへ回収する。`sbx cp`の前後とCollection確定直前に`frozen 1`および実行境界を再検証し、回収前後のHEAD/Index/Working Tree/Untracked Manifest・Bundle/Commit整合性を照合する。再起動・解凍・新たなWriter・Digest不一致があれば失敗とする。
5. Guest CommitのParentがHost Baseline HEADへ連続するか、最終Guest HEADが選択Branchに属するか、Commit済み内容と未Commit内容が二重計上されないかを確認する。全検査がPASSするまではCollection Digestを確定せず、ApplyAuthorizationを発行しない。
6. Writerを無条件に解凍して再利用せず、Supervisorが全Writerプロセスの終了と再Spawn防止を確認する。手順1〜4の全検査、Commit整合性検査、プロセス終了・再Spawn防止検査が全てPASSした場合に限り、HostのSession `collection/`にGuest Commit（BundleとOID）、最終Index/Working Tree/Untracked、最終File Manifestを保全し、全ファイルSHA-256と`collection_digest`を**最後に**確定する。成果はそのSessionGenerationに固定・不変とし、最新Guest状態で黙って置換しない。Owner PreviewにはWorkspace/Branch、SessionKey、Baseline、Guest HEAD、Commit OID、Staged/Unstaged/Untracked差分、確定したCollection Digest、保留理由を示す。
7. Digest確定後にLease解放・Sandbox再利用可否を判定する。いずれかの検査失敗・判定不能時は**`PENDING`（理由`GUEST_QUIESCENCE_UNVERIFIED`）**としてGuest原本、部分収集物、Journal/Receipt、Sandbox Identityを保全し、`collection_digest`の最終確定・ApplyAuthorization発行・Host Applyを禁止する。凍結解除、Sandbox削除、別方式への自動Fallbackをしない。既存の安全な別Session開始条件は§6に従う。

既存のOwner承認は`ApplyAuthorization` = (`SessionKey`, `collection_digest`, `host_baseline_digest`, `expected_host_head`, `expected_index_digest`, `expected_worktree_digest`, `target_result_digest`, `approved_at`)の**1回限りの同意**であり、候補に変化があれば再利用しない。Hostへの無承認書込み・部分適用を認めない。

### 10.2 Apply可否の一意な条件

- Workspace Gate: §6の`HostApplyGate`が回復済みで、全Sessionの非終端Apply Journalが存在しないことを、新規Session/Snapshot採用時だけでなく**Apply開始時**にもWorkspace排他ロック下で確認する。Collectionの静止確認が未完了ならApplyを許可しない。
- 共通前提: Host Workspace/BranchがBaselineと同じ、HEAD OID・Index Digest・Working Tree/Untracked Manifestが**Baselineから不変**、対象ファイルのsymlink/permission/secret検査PASS、Guest Collection Identity一致、他のApplyが非稼働、既存未完了Journalがない。
- **Guest新規Commitなし:** HostのBaselineがDirtyでも、Index（staged状態）とWorking Tree（unstaged/untracked状態）をBaseから最終Guest状態へ安全に再現できる場合に限り適用可能。Hostの既存変更を上書きせず、三者の前提一致を必須とする。
- **Guest新規Commitあり、Host BaselineがClean:** Guest HEADがHost HEADのFast-forward先で、Guest残存差分を二重計上せず再現できる場合に限り、Commit履歴と最終Index/Working Treeを一括適用可能。
- **Guest新規Commitあり、Host BaselineがDirty:** Hostが不変でも、既存のStaged/Unstaged/UntrackedとGuest Commitの整合を自動証明できないため、**通常Apply全体を保留**する。CommitをHost側の隔離Ref/Bundleに保持し、Hostの作業状態を変更しない。Ownerが別途手動整理するまではFile差分だけ先行適用して後からCommitを二重取込みしない。
- **Host HEAD分岐、Index/Working TreeのBaseline逸脱、Guest非Fast-forward:** 通常Apply全体を保留する。Commitは`refs/oc2/pending/<workspace-id>/<session-generation>`へ検証済みの隔離Refとして保存し、Worktree/Index/現在Branch Refは変更しない。隔離Refを保存できない場合もCollection Bundleを保持し、削除しない。
- **部分適用は禁止**。対象Commit・Index・Working Treeを同一Owner承認の1トランザクションとして扱い、成功を偽装しない。新しいCommitを取込まない一部ファイルのApply、暗黙Merge/Rebase/Reset、Force Pushは行わない。

### 10.3 更新順序とクラッシュ復旧

Git Ref・Index・Working Treeは単一の原子更新単位ではないため、**事前準備＋Undo Journal＋CAS Ref更新**を規定する。

1. Host側Workspaceの排他Applyロックを保持し、承認対象の固定Collection、現行HEAD/Index/全対象Working Tree/Untrackedを再検証する（検査後に外部プロセスの競合が検出されたら停止）。
2. 現行HEAD/Index原本・対象ファイルの原本/Mode/不在状態をWorkspace外の私有復旧領域へ永続バックアップし、所望の新IndexとWorking Treeファイルを一時領域で全量準備・検証する。承認前のHost Ref/Index/Working Treeは書き換えない。
3. `apply-journal.json`へ`PREPARED`をfsyncしてから、同一データを参照する`APPLYING`を永続化する。以後は再入時にも復旧判定を優先する。
4. 再検証後から対象Working TreeとIndexの更新完了まで、対象への外部書込みを排除する境界を確立・維持する。境界を確立できない、または維持を確認できない場合はファイル更新を行わずApplyを保留する。既に永続化したJournalは削除・終端扱いにせず、更新を開始していない事実と保留理由を記録して既存の復旧Gateとの整合を保つ。境界を確立・維持できる場合に限り、用意したWorking TreeとIndexの更新を行い、**最後に**Fast-forward対象BranchのRefを期待旧OIDから期待新OIDへCAS更新する。各段階の実行結果・HashをJournalへ記録する。Ref変更なしの場合は新しいIndex/Working Tree検証だけで完成判定する。
5. 全部一致したときのみ`APPLIED`を永続記録し、承認を消費する。書込み途中の失敗やRef CAS失敗時は、JournalとバックアップからHostの元状態へ戻す。Rollbackの各対象も現在内容を確認してから復元し、外部変更を上書きしない。
6. 異常終了からの再起動時、Refが旧OIDならBackupと書込み済みファイルを照合して安全にRollbackする。Refが新OIDかつ最終Index/Worktreeが期待値ならCommit済みとして完了記録する。どちらとも判定できない、外部書換えがある、Rollback失敗時は`RECOVERY_REQUIRED`として**同じWorkspaceの全新規Session・Host Snapshot採用・自動Apply・Sandbox再利用・削除を停止**し、原本・Journal・Collectionを保全する。復旧の整合検証と終端Journalの永続化が済むまで、別SandboxのBaselineとしてHostの部分更新状態を転用しない。

この方式でも他のHostプロセスから途中状態が一時的に見える可能性は残る。**完全な原子性を主張しない**。各段階の書込み・RenameとRef更新の整合性を照合し、Hostの既存データを失わないことを最優先とする。

## 11. エラー・保全条件

- Mount、Sandbox ID、Artifact、Version Lock、Runtime、Session v3 Receipt、Git Baseline、Collection、Credential、推論Grant、Workspace Manifestの不一致はFail-Closed。個別の不一致を自動で同一視・修復しない。
- 同時起動時のLease重複、Guest PENDING、同期競合、Secret検出、Legacy v2状態、Git Ref分岐では既存データを保持する。**Guest PENDINGのみでHost状態が正常かつ全Journalが終端なら別Sandboxで新規Sessionを許可**する。**Host Apply JournalがPREPARED/APPLYING/RECOVERY_REQUIREDまたは終端不明の場合はWorkspace全体を停止し、別Sandboxを作成しても新たなHost Snapshot/Baselineを採用しない**。
- `sbx exec`に加え、v0.51.0/v0.53.0で停止中の`sbx cp`がSandbox起動を伴うことが観測されたため、`sbx stop → sbx cp`をGuest静止/回収Mechanismに採用しない。`--dry-run`や情報表示の経路で副作用のある検査をしない。
- Freezer未対応、Writer Group外のWriter、権限境界未確立、`frozen 1`未確認/解除、Collectorの書込み副作用、回収失敗・Digest不一致は`GUEST_QUIESCENCE_UNVERIFIED`としてCollection確定・Applyを拒否し、Guest/Hostの原本と証拠を保全する。
- Sandbox削除、作業データ破棄、Host Gitの無断Merge/Rebase/Reset、Credential更新、外部Git Push、信頼済みLockの更新、推論Grantの拡張は通常`oc2`操作に暗黙に含めない。
- Host側状態はWorkspace外に0700/0600で保存し、symlink・所有者・重複Identityを拒否する。デバッグログやReceiptにToken、認証DB、Secret本文を記録しない。
- 異常停止時は観測済みFailureと未実行・不明を区別する。Guest/Host成果が残るときは削除せず`PENDING`/`RECOVERY_REQUIRED`として可視化する。

**非機能契約:** 起動・同時起動・同期・ApplyはWorkspace/Session単位の排他制御を持ち、Secret出力を抑止する。設定・Identity・Receiptは決定論的に検証可能とし、通常経路に無制限の自動Retryや追加ネットワーク取得を組み込まない。

## 12. 受入条件・テスト境界

1. Gitリポジトリのルートで`oc2`のみを実行して、APM指定バージョンのOpenCode TUIを起動できる。
2. 承認済みVersion Lockだけが実行され、未登録Version、未承認Lock、Platform/Archive/Binary Digest/Host・Guest Identity不一致をFail-Closedできる。
3. 空きSandboxは正しいWorkspace/SandboxID/Generation/CLI/Runtime Identityで再利用、同時起動は別Sandboxと別Session Receiptを使用する。
4. Host/Guest Baseline、Lease、Collect、Apply JournalはSessionGeneration単位で隔離され、異常終了でも互いの成果を上書きしない。旧v2 Receiptも保護する。
5. HostのGit HEAD、Staged、Unstaged、UntrackedをGuestで区別して再現し、Indexのintent-to-add検出時は誤復元せずFail-Closedする。履歴中のSecret/除外Objectが検出された場合はBundle転送せず停止する。
6. GuestのBranch/Commit/未Commit編集を収集し、Host由来の未Commit内容を二重適用しない。
7. TUI終了後、OpenCode/Plugin/MCP/子孫/Background JobをSession Writer Groupへ初回Spawn前から封じ込め、Group外からの書込み・脱出/再Spawnを防止したうえでcgroup v2 Freezerの`frozen 1`を保持し、独立Collectorが読取り専用で回収・前後照合できた場合のみCollectionを最終確定する。保証不能なら`PENDING`/`GUEST_QUIESCENCE_UNVERIFIED`で保全する。固定CollectionをPreviewし、Ownerが1回承認した同じIdentityだけをHostへ適用できる。変更された候補や再承認なしの再適用は禁止。
8. Clean Baseline＋Guest Fast-forward Commitは履歴保持で反映でき、Dirty Baseline＋Guest CommitはCollection/隔離Refを保全して全体保留する。Guest CommitなしのDirty BaselineはStaged/Unstagedの独立状態を安全に反映できる。
9. Host HEAD/Index/WorktreeのBaseline逸脱、Ref分岐、途中クラッシュ、Rollback不能を再現し、データ消失・Partial Successなしで`RECOVERY_REQUIRED`または保留へ移行できる。Host Apply中は`--new`を含め新規Session/Snapshot採用を全て拒否し、Guest PENDINGのみの場合と区別できる。
10. 初回のみ有効期限付き推論Grantを承認し、同一スコープで`oc2`だけの継続起動ができる。未承認・期限切れ・取消・Provider/Model/Account/Workspaceの変更はRuntime起動前に停止する。通常のOpenCodeモデル選択には承認済みProvider/Modelだけが現れ、独自HTTP要求のModel ID制御は保証外として明示する。
11. OpenAI OAuth、Cloudflare Credential BindingとAPM Provider選択を維持し、OpenCode v1やHostのCredentialを変更しない。
12. 既存OC2 Phase 5のPlugin/MCP/Runtime検証、Mountless隔離、固定Artifact境界を回帰させない。

テストは**オフライン単体・統合検証を先行**し、Version Lock/Schema異常、2つの並行Session、Lease Crash、Stage/Unstage/Untracked、**intent-to-add検出と未知Index形式の拒否、Guest Quiescence未確認、Host APPLYING/RECOVERY_REQUIRED時の新規Session遮断と復旧解除、通常モデル選択のGrant投影とTrusted Plugin独自HTTPの非保証境界**、Git履歴Secret、Fast-forward/分岐、Apply Fault Injection、Grant失効/取消を決定論的なFixtureで検証する。F-004では特に、初回Spawn時のWriter Group所属・Plugin/MCP子孫とBackground Jobの捕捉、Group外Writer/権限昇格/再Spawnの拒否、`frozen 1`到達と解除・失敗時のPENDING、Collectorの読取り専用性、凍結中のBundle/Manifest生成と`sbx cp`、回収前後のGit全層整合・Digest、Collection確定順序を検証する。2026-11-13の単一Writer限定PoCを本番全Writer保証のPASSに昇格させない。Sandbox・実際の推論・Credential操作による本番実機受入は、実装とは別途Human Ownerの承認がある場合だけ行う。未実行をPASS/FAILと混同しない。

## 13. 非目標・停止条件・後続判断

**非目標:** Direct Mount化、既存Runtime全面再実装、OpenCode v1改変、任意Plugin/MCPの解禁、任意未検証CLI起動、無承認Git Push、無断Host書込み、既存Sandboxの自動破棄。

**今回の限定訂正の完了条件:** R0.1.2で整理済みのF-001/F-002/F-003/F-005とWorkspace復旧Gateを保持し、F-004についてcgroup v2 Freezer候補、全Writer封じ込めの条件、Collector分離、凍結からCollection Digest確定までの順序、保証不能時のPENDINGを一意に記載すること。既存のMountless/Snapshot/選択的Bundle/APM SSOT/Owner Apply承認を変更しない。限定PoC PASSは本番成立性の承認ではない。

**承認境界:** R0.1の既存アーキテクチャはHuman Owner採択済み。R0.1.1のF-001/F-002、R0.1.2のF-003/F-005解決を維持し、2026-11-13の限定PoC結果を根拠にF-004だけをOwner承認の文書限定訂正として記録する。**Design R0.1.3最終採択・残余リスク受容・Implementation Plan作成・実装開始の承認を意味しない**。本番の全Writer封じ込めとCollector非書込み性は未検証で、成立するまで自動Collect/Host ApplyはHOLDする。

**停止条件:** 本Design R0.1.3と対応するF-004 Feasibility Planの文書限定訂正をGitHubへ反映した後は終了する。追加のImplementation Plan、実装、独立レビュー、PR、Merge、Sandbox/Runtime実機操作、Credential変更は、別途Human Ownerが承認するまで自動開始しない。
