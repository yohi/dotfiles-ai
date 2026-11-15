# OC2 Daily Launcher — Design R0.2

- Date: 2026-11-13 (R0.2 revision: 2026-11-14)
- Repository: `yohi/dotfiles-ai`
- Baseline: `master` at `e79573903f1a2b550e32bc6022d91c43fdcccbb4`
- Status: **R0.2 F-004 design alignment to the feasibility-proven Alternative A (unprivileged Writer container, Trusted Supervisor, Read-only Git Collector, Proxy-only Relay). The R0.1.3 cgroup Freezer mechanism is withdrawn. Full design adoption and implementation remain pending Human Owner decision; Implementation GO, automatic Collect and Host Apply remain HOLD.**
- Owner decision: `ACCEPT_TASK3B1_WITH_LIMITATIONS_AND_AUTHORIZE_F004_DESIGN_ALIGNMENT`
- Scope: **Design only**. This document does not authorize implementation, Sandbox changes, Credential changes, PR creation, or Merge.
- R0.2変更点: R0.1.3のSession専用cgroup v2 Writer Group＋Freezer方式は、Guestの`agent`ユーザーがNOPASSWD sudoとdocker groupを持ちWriterがWriter cgroupから脱出できるため、成立性を否定された（Owner判断`F004_CURRENT_MECHANISM_FEASIBILITY_FAILED`）。§6・§9・§10〜§13のF-004記述をAlternative Aへ置換し、§10.4に証拠分類（実証済み・制約付き・未検証）を追加した。APM SSOT、SessionKey、HostApplyGate、Owner Apply承認の仕様は意味を変更しない。

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

### Session Writer実行境界（F-004 Alternative A）

R0.1.3のSession専用cgroup v2 Writer Group＋Freezer方式は**撤回**した（不採用の代替案としてのみ記録する）。Guestの`agent`ユーザーはNOPASSWD sudoとdocker groupを持つため、同ユーザー権限で動くWriterはWriter cgroupから脱出でき、Freezerで全Writerを覆えない。各`SessionKey`のGuest開発作業は次の主体に分離する。

- **Writer Container（非特権・非信頼）:** OpenCode本体、Plugin/MCP、Spawnされた子孫、Background Jobは全て、Session専用Writer Containerのプロセスツリーとして起動時から実行する。既存プロセスを後から移送する方式は使わない。必須構成は、非root UID/GID `10001`、`--cap-drop ALL`、`no-new-privileges`、read-only rootfs、`--pids-limit`、`--restart no`、`--network none`、docker.sock・containerd socketなし、sudo・setuid/setgidファイルなし、Credential環境変数なしとする。書込み可能なのはSession専用Guest Repository（このWriterにだけrw bind）とtmpfsに限る。別SessionのWriter Container、Repository、Relay Socketを兼用しない。
- **Trusted Supervisor（Writer外・信頼境界）:** Guestの`agent`権限（docker group・sudo）で動作し、Writer/Relay/Collectorの起動、Writer停止、停止検証、Relay Sessionの登録・失効、回収を所有する。Supervisorの権限と制御経路（docker.sock、管理Socket、Secret生成元）はWriterへ渡さない。Supervisorは制御用TCP Listenerを開かない（Guest INPUTがACCEPTのため、§10.4）。Writer-writableなTreeに対してRoot権限でGitを実行せず、読取りはno-follow・descriptor-relativeに限る。通常経路でWriterへ`docker exec`しない（exec起動プロセスはWriterと同一のContainer Identityになる）。
- **Read-only Git Collector（別Container・非Writer）:** Writer停止検証後に起動する別Containerで、Writerとは別の非root UID、Capabilityなし、`no-new-privileges`、read-only rootfs、`--network none`とする。収集元TreeはKernelの読取り専用Mount（`ro`）で受け、書込み先はSession専用の別rwステージング領域だけとする。Writerが仕込んだRepository config、hook、filter/textconv、fsmonitor、pager、sshCommand、`core.worktree`等は実行しない（System/Global configの無効化、宣言Driverの明示上書き、`--no-optional-locks`、`GIT_DIR`/`GIT_WORK_TREE`固定）。symlinkは辿らず、Root外を指すsymlinkとhardlinkは検出・記録する。
- Launcherは`SessionKey`、Sandbox ID、Writer Container Identity、Relay Session、Leaseの対応を検証する。**全ての非信頼プロセスがWriter Container内に留まること**が本モデルの前提であり、Writer外で収集元を書き換え得る非信頼主体、Writer Identityの不一致、Supervisor登録の不整合を検出・否定できなければ、**通常の自動Collect/Collection確定を有効化しない**。
- Guest Writer境界とHost Apply復旧のWorkspace Gateは別の条件であり、双方がPASSした場合だけ収集・適用を進める。

### Writer Egress境界（Proxy-only Relay、F-004）

- Writerは`--network none`とし、`lo`以外のInterface・Route・DNS経路を持たない。Writerは名前解決を行わない。sbxのDNS Gateは、Sandbox単位の`deny **`があってもGlobal allowに載る名前を解決することがTask 3Aで観測されたため（oc2-f004-altA-task3a-report、oc2-f004-altA-task3a-dns-report）、WriterにDNS経路を与えることを禁止する。
- Writerの唯一の外向き経路は**Proxy-only Relay**へのUnix Domain Socketとする。SupervisorはSessionごとに専用Socketディレクトリ（Relay UID所有・Writer GID・`2750`、Socket `0660`、Socket以外を置かない）を作成し、Writerへ`ro`でbind mountする。Writer内のProxy設定（必要な場合はWriter内loopbackのSocket Bridge）はこのSocketだけを指す。
- RelayはWriterとは別Containerとし、外向き経路を持たないinternal network上に置く。許可は完全一致の`host:port` Allowlistのみで、CONNECT、IPリテラル、Allowlist外Host、Host Header不一致などの不正形式、Redirect追随を拒否する。Header/Body/Responseのサイズ、Header受信・Upstream応答の時間、1接続1要求の上限を持ち、全判定（peerのuid/gid/pid、理由）を決定ログへ記録する。Secret・Token・Hashはログに出さない。
- Relayは**Model-awareな認可主体ではない**（§9の保証範囲を変更しない）。実Provider宛ての上流経路、TLS、Credential注入は未設計・未検証とする（§10.4）。

### Relay Session認可・Container Identity・失効（F-004）

- **Relay Session:** Supervisorは`SessionKey`ごとにRelay Sessionを登録し、Session専用Socketを作成する。状態は`PENDING`（登録済み・Writer未bind）→`ACTIVE`（Writer Identity bind済み）→`REVOKED`の一方向とする。
- **Session Secret:** SupervisorがWriter外で生成する256bit以上の乱数とし、Writer専用の`ro`・`0400` Mountにだけ置く。Relayには鍵IDとSecretのSHA-256だけを渡し、定数時間比較で照合する。Secret・Hashはargv、ログ、Receipt、証跡へ出さず、Session終了時にGuest側のSecretファイルを破棄する。
- **Container Identity:** Writer起動後、SupervisorがWriterのContainer IDとcgroup v2 inodeを取得してRelay Sessionへbindする。Relayは接続ごとに`SO_PEERPIDFD`で得たpidfdから`PIDFD_GET_INFO`でpeerのcgroup v2 IDを取得し、bind済みinodeと照合する（PID再利用の競合を受けない）。
- **許可条件（全てAND）:** (1) Relay Sessionが`ACTIVE`、(2) `SO_PEERCRED`のuid/gidがWriterのUID/GIDに一致、(3) peerのcgroup v2 IDがSupervisor登録済みのWriter cgroup inodeに一致、(4) 接続冒頭の鍵IDとSecretが当該Socketに登録されたSessionに一致。いずれかの不成立・取得不能は拒否（Fail-Closed）する。
- **失効:** Writerの停止・再起動（cgroup IDが変わるため、Revoke前でもbind不一致で拒否される）、Session終了、明示Revokeのいずれでも、SupervisorがRelay Sessionを`REVOKED`とし、Listenerを閉じ、Socketを削除し、処理中接続を打ち切る。Relayは処理中peerの終了をpidfdで検知して要求を中断する。失効済み・残存・再利用されたSocket、別SessionのSocket/鍵ID/Secret、同UIDの別Containerによる漏えいSecretの使用は拒否する。Socketパスを別Sessionで再利用しない。
- **管理経路:** Relayの管理SocketはGuest uid 0（Supervisor）からの接続だけを受ける。Guest rootはSupervisorの信頼範囲に含まれる。
- **制約:** IdentityはContainer単位であり、Writer Container内の全プロセス（`docker exec`経由を含む）は同一Identityとして許可され、Secretファイルも読める。bindの正しさはSupervisorに依存する。Task 3B-1でRelayを`--pid host`で起動した構成は制約付きのFeasibility結果であり、本番採用ではない（§10.4）。

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

**F-004 Alternative Aとの関係:** WriterのEgressは§6のProxy-only Relay（`host:port` Allowlist）に限定するが、RelayはModel IDを検査しない。Relayと既存Credential Proxy/Brokerの接続、TLS、実Providerでの動作は未検証であり（§10.4）、上記の保証範囲と残余リスクを変更しない。

継続Grantは起動操作を簡素化するものであり、外部送信・課金ゼロや予算上限を自動保証するものではない。

## 10. TUI終了後のCollect / Preview / Apply — F-004限定訂正

TUI終了時にCollectとPreviewを自動実行するが、**Host ApplyはHuman Ownerの承認まで絶対に実行しない**。対象はSessionKeyで固定したGuest最終HEAD、Guest新規Commit OID群、最終Index/Working Tree/Untrackedの集合であり、最新状態を再取得して黙って差し替えない。

### 10.1 収集と候補の固定

**採用候補Mechanism（F-004 Alternative A）:** **Trusted SupervisorによるWriter Containerの停止・停止検証＋別ContainerのRead-only Git Collectorによる読取り専用回収**を設計とする（主体と構成は§6）。TUI終了は必要条件だが十分条件ではない。R0.1.3のcgroup v2 Freezer方式は成立性否定により撤回し、Mechanismとして用いない。Sandbox全体を`sbx stop`してから`sbx cp`する方式も採用しない（Docker Sandboxes v0.51.0/v0.53.0で、停止中`sbx cp`がSandboxを起動することを実測）。Sandboxは稼働させたまま、Writer Containerだけを停止する。証拠は§10.4のとおり範囲限定であり、通常の自動CollectとHost ApplyはHOLDする。R0.1.3記載の単一テストWriterによるFreezer PoC（2026-11-13）は撤回した方式の証拠であり、Alternative Aの根拠にしない。

**責務と強制境界:**

- **Host Launcher（Authority）:** SessionKey/Lease/Sandbox ID/Runtime Identityに結び付いたWriter Container、Relay Session、Collectorの分離を起動前に検証し、未構築・不一致なら推論可能なTUIと自動Collectを開始しない。別SessionのWriter Container・Relay Session・Repositoryを流用しない。
- **Trusted Supervisor（停止・検証・回収の所有者）:** Writer外で動作し、Writer Containerの起動構成（§6）を強制し、停止、停止検証、Relay Session失効、Collector起動、回収を実行する。全ての非信頼プロセスがWriter Container内に留まることを証明できない場合はFail-Closedする。
- **Writer Container:** 停止後に再起動・再利用しない（`--restart no`）。停止したWriterへのexecや再開を回収経路に用いない。
- **Read-only Git Collector（非Writer）:** 収集元のGit Objects/HEAD/Index/Working Tree/Untrackedに書き込まない。Bundle/Manifest生成は別の専用ステージング領域へ行い、Writerが仕込んだconfig/hook/filter/fsmonitorを実行せず、元RepositoryにLock・Index更新・Cleanupなどの副作用を残さないことを検証する。書込み不能性の保証がない場合はCollectを確定しない。
- **Host Collector:** `sbx cp`でSandbox稼働中に収集物をHostのWorkspace外・Session専用私有領域へ移し、Digest/Identity/Commit到達性/Manifestを検証してから不変Collectionを確定する。Guestの生Credential・禁止Objectを輸送しない。

**状態遷移・実行順序（以下の順序を変更しない）:**

1. TUI終了を確認し、Supervisorが同SessionKeyのWriter新規起動・再起動経路を遮断する。
2. SupervisorがWriter Containerを停止（TERM、期限超過時はKILL）し、Relay Sessionを失効させる（Listener閉鎖・Socket削除・処理中接続の切断）。
3. Supervisorが停止を検証する。Container `exited`・`Running=false`・`Pid 0`・Restart Policy `no`・`RestartCount 0`、観測期間後も`StartedAt`不変、登録済みWriter cgroupの消滅、Writer UIDのプロセス不存在、Writer TreeをRW bindする稼働Containerの不存在、停止後のno-follow・descriptor-relativeな読取りScanによるTree不変を全て確認する。単なるPID消滅、一定時間のHash一致、`sbx stop`だけでは停止の証明とせず、Identity・cgroup・状態の検査と組み合わせる。確認不能なら以後の確定手順へ進まない。
4. Read-only Git CollectorがGit HEAD/Branch/Commit OID/Index生バイト、Staged/Unstaged/Untracked、File Manifestを読取り専用に記録する。必要な選択的Git Bundleは専用ステージング領域で生成・検証し、収集元への副作用とSecret/除外Objectを拒否する。残存`index.lock`などの未完了Git Transactionを検出した場合は**修復せず**`PENDING`とする（修復方針は未決定、§10.4）。
5. Sandbox稼働中に`sbx cp`でステージング成果をHostへ回収する。`sbx cp`の後とCollection確定直前に、同一boot ID、同一Writer Container IDが`exited`のまま、cgroup不存在、Writer UIDプロセス不存在、Tree不変、Collector再検証の一致を再確認し、回収前後のHEAD/Index/Working Tree/Untracked Manifest・Bundle/Commit整合性を照合する。再起動・新たなWriter・Digest不一致があれば失敗とする。
6. Guest CommitのParentがHost Baseline HEADへ連続するか、最終Guest HEADが選択Branchに属するか、Commit済み内容と未Commit内容が二重計上されないかを確認する。全検査がPASSするまではCollection Digestを確定せず、ApplyAuthorizationを発行しない。
7. Writerを再起動・再利用しない。手順1〜5の全検査とCommit整合性検査が全てPASSした場合に限り、HostのSession `collection/`にGuest Commit（BundleとOID）、最終Index/Working Tree/Untracked、最終File Manifestを保全し、全ファイルSHA-256と`collection_digest`を**最後に**確定する。成果はそのSessionGenerationに固定・不変とし、最新Guest状態で黙って置換しない。Owner PreviewにはWorkspace/Branch、SessionKey、Baseline、Guest HEAD、Commit OID、Staged/Unstaged/Untracked差分、確定したCollection Digest、保留理由を示す。
8. Digest確定後にLease解放・Sandbox再利用可否を判定する。いずれかの検査失敗・判定不能時は**`PENDING`（理由`GUEST_QUIESCENCE_UNVERIFIED`）**としてGuest原本、部分収集物、Journal/Receipt、Sandbox Identity、停止済みWriter Containerを保全し、`collection_digest`の最終確定・ApplyAuthorization発行・Host Applyを禁止する。Writer再起動、Gitの修復、Sandbox削除、別方式への自動Fallbackをしない。既存の安全な別Session開始条件は§6に従う。

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

### 10.4 F-004 Alternative Aの証拠分類と未検証事項

証拠は報告書名で参照する（oc2-f004-altA-stage2-report、oc2-f004-altA-task3a-report、oc2-f004-altA-task3a-dns-report、oc2-f004-altA-task3b0-report、oc2-f004-altA-task3b1-report）。いずれも使い捨てMountless Sandbox上のFeasibility証拠であり、本番実装・本番受入のPASSではない。

**実証済み（範囲限定）:**

| 範囲 | 報告書 | 判定 | 示したこと |
| --- | --- | --- | --- |
| fixture | oc2-f004-altA-stage2-report | Evidence契約Validatorの単体テストPASS | Gate Manifestの検証規約 |
| runtime-offline | oc2-f004-altA-stage2-report | **RUNTIME_OFFLINE_PASS_WITH_LIMITATIONS**（runtime/containment/stop/collector/consistency PASS、network NOT_VERIFIED、full-runtime NOT_VERIFIED） | Network無しの非特権Writer ContainerでOpenCode v2.2.5と承認済みPhase 5のPlugin 3件・MCP 1件がOffline動作し、全プロセスがWriter内に留まること。停止と停止後の不変、Read-only Collectorの書込み拒否とhostile config/hook/filter/fsmonitorの非実行、稼働中`sbx cp`前後のDigest一致 |
| network-only | oc2-f004-altA-task3a-report | Gate A/C/D PASS、Gate B NOT_VERIFIED（総合NOT_VERIFIED） | 合成Probe Writer（OpenCode非実行）からDocker Engine・Supervisorへ到達できないこと、Runtime境界、Evidence整合 |
| network-only（原因調査） | oc2-f004-altA-task3a-dns-report | 原因特定、リスクは未解消 | sbx DNS GateがSandbox単位の`deny **`を反映せずGlobal allowの名前を解決すること（接続自体は拒否） |
| mock-only | oc2-f004-altA-task3b0-report | C1-C4・C6 PASS、C5 NOT_VERIFIED（総合NOT_VERIFIED、Credential無し） | `--network none` WriterからのDNS/直接TCP不可、Relay Socketだけが経路であること、Relay Policy（CONNECT・Allowlist外・Redirect・Size/Time違反の拒否）、Mockとの通信 |
| mock-only | oc2-f004-altA-task3b1-report | T2 PASS、T5 PASS（Credential無し） | Relay Session認可4条件と失効（Bind前、再起動、Revoke後Socket、別Session資格情報、同UID別Container・漏えいSecretの拒否）、停止後のRead-only Collector回収とHost照合 |

**制約付き:**

- Task 3B-1のRelayは`--pid host`で起動した。別pid namespaceのpeerに対して`PIDFD_GET_INFO`を成立させるためであり（Relay自身のpid namespaceでは取得不能となりFail-Closedで全拒否された）、RelayからGuest全プロセスの`/proc`情報（引数・cgroup）が見える。Kernel 6.13以上の`PIDFD_GET_INFO`に依存する。これは**Feasibility上の構成結果であり本番採用ではない**。本番の代替（Supervisor側Identity Oracle、2段Relay、他のKernel機能、`--pid host`を許容する場合の緩和策）は未決定の設計項目とする。
- Writerの`/home/writer` tmpfsはOpenTUIのNative Library読込みのためexec可能が必要であり、Writer境界内の実行可能範囲を広げる。
- 停止後の静止観測期間は20秒であり、Task 3B-1の停止前Collector実行は停止前後の不変を示すもので、停止中の一貫性の証明ではない。

**未検証（HOLD理由）:**

- Git書込み中の停止: Stage 2のFault Injection（`git add`中のSIGKILL、1回）で残存`index.lock`を観測し`PENDING`と分類したが、修復・再開方針は未決定。
- Credential Proxy、TLS、Model単位の認可、実Providerでの推論。
- Full-runtime: SSOTの`@latest`・`file://` Plugin、Network/認証を要するMCP Server、MCP Gateway。
- Task 3C（未着手）。
- RelayのProcess単位Identity（Container単位のみ。`docker exec`で入ったプロセスは区別できない）。
- Trusted Supervisorの信頼性とWriter Identity登録（bind）の正しさ。
- Guest INPUTがACCEPTであること（SupervisorがTCP Listenerを開けばWriterから到達し得る）とその緩和。
- user namespace remapなし（Container UIDとGuest UIDが同一）。
- Base Libraryの来歴（Guest dpkg databaseとの照合のみ）。
- Wildcard allowを使うDNS経由のexfil（未試験）。
- Task 3B Design R0.1は所在不明であり、本書はその内容を推定で補わない。
- Stage 2/3A/3B-0/3B-1のKit（Feasibility用コード・Image）はMerge対象外。

**HOLD:** Implementation GO、自動Collect、Host Apply。

## 11. エラー・保全条件

- Mount、Sandbox ID、Artifact、Version Lock、Runtime、Session v3 Receipt、Git Baseline、Collection、Credential、推論Grant、Workspace Manifestの不一致はFail-Closed。個別の不一致を自動で同一視・修復しない。
- 同時起動時のLease重複、Guest PENDING、同期競合、Secret検出、Legacy v2状態、Git Ref分岐では既存データを保持する。**Guest PENDINGのみでHost状態が正常かつ全Journalが終端なら別Sandboxで新規Sessionを許可**する。**Host Apply JournalがPREPARED/APPLYING/RECOVERY_REQUIREDまたは終端不明の場合はWorkspace全体を停止し、別Sandboxを作成しても新たなHost Snapshot/Baselineを採用しない**。
- `sbx exec`に加え、v0.51.0/v0.53.0で停止中の`sbx cp`がSandbox起動を伴うことが観測されたため、`sbx stop → sbx cp`をGuest静止/回収Mechanismに採用しない。`--dry-run`や情報表示の経路で副作用のある検査をしない。
- Writer Containerの構成不一致（root実行、Capability、docker.sock、Network、restart policy等）、Writer外の非信頼Writer、停止検証失敗（再起動、cgroup残存、Writer UIDプロセス残存、停止後のTree変化）、Relay Session失効の失敗、Collectorの書込み副作用・hostile設定の実行、未完了Git Transaction（残存`index.lock`等）、回収失敗・Digest不一致は`GUEST_QUIESCENCE_UNVERIFIED`としてCollection確定・Applyを拒否し、Guest/Hostの原本と証拠を保全する。
- Relay認可条件の不成立・Identity取得不能は接続拒否（Fail-Closed）とし、Writerへ別経路のNetwork/DNSを与えて回避しない。
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
7. OpenCode/Plugin/MCP/子孫/Background Jobが起動時から非特権Writer Container内で動作し、TUI終了後にTrusted SupervisorがWriterの停止・停止検証・Relay Session失効を完了し、別ContainerのRead-only Git Collectorが読取り専用で回収・前後照合できた場合のみCollectionを最終確定する。保証不能なら`PENDING`/`GUEST_QUIESCENCE_UNVERIFIED`で保全する。固定CollectionをPreviewし、Ownerが1回承認した同じIdentityだけをHostへ適用できる。変更された候補や再承認なしの再適用は禁止。
8. Clean Baseline＋Guest Fast-forward Commitは履歴保持で反映でき、Dirty Baseline＋Guest CommitはCollection/隔離Refを保全して全体保留する。Guest CommitなしのDirty BaselineはStaged/Unstagedの独立状態を安全に反映できる。
9. Host HEAD/Index/WorktreeのBaseline逸脱、Ref分岐、途中クラッシュ、Rollback不能を再現し、データ消失・Partial Successなしで`RECOVERY_REQUIRED`または保留へ移行できる。Host Apply中は`--new`を含め新規Session/Snapshot採用を全て拒否し、Guest PENDINGのみの場合と区別できる。
10. 初回のみ有効期限付き推論Grantを承認し、同一スコープで`oc2`だけの継続起動ができる。未承認・期限切れ・取消・Provider/Model/Account/Workspaceの変更はRuntime起動前に停止する。通常のOpenCodeモデル選択には承認済みProvider/Modelだけが現れ、独自HTTP要求のModel ID制御は保証外として明示する。
11. OpenAI OAuth、Cloudflare Credential BindingとAPM Provider選択を維持し、OpenCode v1やHostのCredentialを変更しない。
12. 既存OC2 Phase 5のPlugin/MCP/Runtime検証、Mountless隔離、固定Artifact境界を回帰させない。
13. WriterはRelay Socket以外の外向き経路とDNS経路を持たず、Relayは§6の許可条件を全て満たす接続だけをAllowlist宛てに中継し、失効後・別Session・別Containerからの接続を拒否する。

テストは**オフライン単体・統合検証を先行**し、Version Lock/Schema異常、2つの並行Session、Lease Crash、Stage/Unstage/Untracked、**intent-to-add検出と未知Index形式の拒否、Guest Quiescence未確認、Host APPLYING/RECOVERY_REQUIRED時の新規Session遮断と復旧解除、通常モデル選択のGrant投影とTrusted Plugin独自HTTPの非保証境界**、Git履歴Secret、Fast-forward/分岐、Apply Fault Injection、Grant失効/取消を決定論的なFixtureで検証する。F-004では特に、Writer Containerの起動構成とPlugin/MCP子孫・Background Jobの捕捉、Writer外への脱出・権限昇格・再起動の拒否、`--network none`とDNS経路の不在、Relay Session認可条件と失効、停止検証と失敗時のPENDING、Git書込み中停止のPENDING、Collectorの読取り専用性とhostile設定の非実行、停止後のBundle/Manifest生成と`sbx cp`、回収前後のGit全層整合・Digest、Collection確定順序を検証する。§10.4のFeasibility証拠（fixture・runtime-offline・network-only・mock-only）を本番保証のPASSに昇格させない。Sandbox・実際の推論・Credential操作による本番実機受入は、実装とは別途Human Ownerの承認がある場合だけ行う。未実行をPASS/FAILと混同しない。

## 13. 非目標・停止条件・後続判断

**非目標:** Direct Mount化、既存Runtime全面再実装、OpenCode v1改変、任意Plugin/MCPの解禁、任意未検証CLI起動、無承認Git Push、無断Host書込み、既存Sandboxの自動破棄。

**今回の設計整合（R0.2）の完了条件:** R0.1.2で整理済みのF-001/F-002/F-003/F-005とWorkspace復旧Gateを保持し、F-004についてFreezer方式の撤回、Writer Container/Trusted Supervisor/Read-only Git Collectorの分離、Writer `--network none`とProxy-only Relay、Relay Session認可・Container Identity・失効、停止からCollection Digest確定までの順序、保証不能時のPENDING、証拠分類（実証済み・制約付き・未検証）を一意に記載すること。既存のMountless/Snapshot/選択的Bundle/APM SSOT/SessionKey/HostApplyGate/Owner Apply承認を変更しない。Feasibility PASSは本番成立性の承認ではない。

**承認境界:** R0.1の既存アーキテクチャはHuman Owner採択済み。R0.1.1のF-001/F-002、R0.1.2のF-003/F-005解決を維持する。R0.1.3のFreezer方式はOwner判断`F004_CURRENT_MECHANISM_FEASIBILITY_FAILED`により撤回し、Owner判断`ACCEPT_TASK3B1_WITH_LIMITATIONS_AND_AUTHORIZE_F004_DESIGN_ALIGNMENT`に基づきF-004をAlternative Aへ整合させる。**Design R0.2最終採択・残余リスク受容・Implementation Plan作成・実装開始の承認を意味しない**。§10.4の未検証事項が解消されるまで、Implementation GO・自動Collect・Host ApplyはHOLDする。

**停止条件:** 本Design R0.2のF-004設計整合を文書へ反映した後は終了する。Commit/Push、追加のImplementation Plan、実装、独立レビュー、PR、Merge、Sandbox/Runtime実機操作、Credential変更は、別途Human Ownerが承認するまで自動開始しない。
