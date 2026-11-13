# OC2 Daily Launcher — Design R0.1

- Date: 2026-11-13
- Repository: \`yohi/dotfiles-ai\`
- Baseline: \`master\` at \`e79573903f1a2b550e32bc6022d91c43fdcccbb4\`
- Status: **Human Owner approved design**
- Scope: **Design only**. This document does not authorize implementation, Sandbox changes, Credential changes, PR creation, or Merge.

## 1. 背景と目的

Phase 5で実装したOpenCode v2 Runtime、APM Full SSOT、Superpowers、Akane、Sibyl、MCP、Host Credential Proxyを活用し、日常の開発を\`oc2\`だけで開始できるようにする。

ユーザーはGitリポジトリのルートから\`oc2\`を起動する。Launcherは正しいOpenCode v2のバージョン、APM Runtime設定、認証、既存Sandbox、Workspace同期状態を自動選択する。AIの変更はSandboxに隔離し、終了時に差分とCommitを収集して、Human Ownerの**1回の承認**でHostへ反映できるようにする。

隔離性だけを追求して日常操作を複雑にしたり、使いやすさのためにHostのソースや\`.git\`を無条件に書き換えたりしない。

## 2. 既存実装と変更境界

\`master\`の既存資産を再利用する。

- \`sandbox/scripts/oc2.py\`: Host Launcher、固定CLI検証、Sandbox起動、Provider認証。
- \`sandbox/scripts/oc2_native.py\`と\`prepare_opencode_v2.py\`: APMの検証・Runtimeへの設定反映。
- \`sandbox/scripts/oc2_guest.py\`: Guest側の設定・Asset・Plugin検証。
- \`sandbox/scripts/oc2_workspace.py\`と\`oc2_workspace_ops.py\`: Snapshot、変更検出、衝突検出・限定適用。
- \`sandbox/scripts/oc2_session.py\`: Workspaceごとの転送Receipt。
- \`apm.yml\`: User-configurable Runtime設定のSSOT。

現在の通常起動は固定バージョン\`2.2.5\`、既定Sandbox名\`oc2-v2\`、既存Sandbox名の再利用拒否、およびMountless Snapshot転送を前提としている。PATH登録は手動であり、Workspaceの自動再同期、Git履歴のGuest利用、終了時の自動Collect/Apply導線は日常利用に不足している。

これらの**起動・同期・セッション管理**を拡張する。既存Phase 5 Runtimeや安全境界を全面的に再実装しない。

## 3. アプローチ比較と採択

| 方式 | 利点 | 制約 | 判定 |
| --- | --- | --- | --- |
| A. Mountless + Snapshot自動同期 + 選択的Git Bundle | Hostへの直接書込みを防ぎ、既存の安全機構を活用できる。Git履歴と未Commit状態を扱える。 | 安全な同期・履歴転送・競合処理の実装が必要。 | **採用** |
| B. Docker Clone Mode + Git同期 | Git履歴を自然に利用できる。 | HostのGit内容の公開範囲、Worktree、未追跡ファイル、同期運用が制約となる。 | 非採用 |
| C. Direct Mount | 編集結果がHostへ即時反映され操作は簡単。 | Hostのファイル・Gitへの誤編集と多重起動競合を防ぎにくい。 | 非採用 |

Git履歴が使えないSnapshot+\`git init\`のみの方式も、普段の開発に必要な\`git log\`やCommit継続性を満たさないため採用しない。

## 4. 通常の操作とCLI契約

\`\`\`sh
cd ~/program/nexus
oc2
\`\`\`

- \`oc2\`: カレントGitリポジトリのルートをWorkspaceにし、互換性のある未使用Sandboxを選択してTUIを起動。
- \`oc2 --new\`: 既存Sandboxを破壊せず新規Sandboxを選択。
- \`oc2 --status\`: Workspaceに紐付くSandbox、占有、同期・未反映変更、Runtime IdentityをSecretなしで表示。
- \`oc2 --dry-run\`: 設定と選択予定を検証・表示し、Sandbox作成、Credential変更、推論、ファイル同期を行わない。
- \`oc2 --version\`: APMで選択されたOpenCodeバージョンを表示。

\`oc2\`のPATH設定は初回に標準化する。通常使用では\`--workspace\`、\`--sandbox\`、手動\`sbx cp\`、手動Collect/Applyを要求しない。診断・保守用の明示オプションを残してよい。

## 5. APM SSOTとOpenCode Version

ユーザーが指定するバージョンは既存\`apm.yml\`の\`x-oc2-runtime\`配下に置く。

\`\`\`yaml
x-oc2-runtime:
  enabled: true
  opencode:
    version: "2.2.5"
  theme: tokyonight
  # 既存watchdog / sibylObserver等は保持
\`\`\`

- Launcher、Guest Validator、CLI Artifact選択は同一の検証済みバージョン設定を使用し、個別のユーザー設定値を持たない。
- バージョンごとの公式Artifact、サイズ、ダイジェスト等は**信頼済みLock契約**から取得する。APMの文字列だけを根拠に未検証バイナリを実行しない。
- Lockにないバージョン、Identity不一致、構成不整合はFail-Closed。勝手な最新版への追従やFallbackはしない。
- Models、Providers、Agents、Plugin、MCP、Rules/Commands/Skills、Theme、Timeout、Akane/Sibyl Optionsは既存Full SSOT契約を継承する。
- VersionまたはRuntime設定の変更が適用互換性に影響するときはRuntime/Sandbox互換性を再評価する。旧Sandboxを無断で上書きしない。

固定Artifact Identity、Sandbox隔離、Credentialの安全制約など、ユーザー操作で緩和させないルールはコード側に維持する。

## 6. Sandbox自動選択・多重起動

Host側でWorkspaceごとにSandboxインベントリとLeaseを管理する。紐付けには以下を含める。

- Host側Git Workspaceの正規化された絶対パスと識別子
- Sandboxの固有ID（**名前だけでは再利用しない**）
- 選択されたOpenCodeバージョンと検証済みCLI Identity
- Runtime Identity、Workspace baseline、同期状態
- Leaseの所有者・有効性（PIDだけでなく実行状態と競合を確認）

通常起動：

1. 対象WorkspaceとAPM/Artifact/Runtimeを検証する。
2. 排他ロック下で互換性のあるSandboxを検索し、未使用ならLeaseを取得する。
3. 空きがなければ独立したSandboxを新規作成する。多重起動は別Sandboxを使う。
4. TUI終了時にLeaseを解放するがSandboxは保持する。
5. 再起動・異常終了後にLeaseが不確かな場合は二重占有せず保留する。

Sandboxの互換性には既存\`is_compatible_sandbox\`のmountless検証、Sandbox ID、固定CLI、必要なRuntime Identityが含まれる。既存の検証用R5/R6等を名前の一致だけで通常再利用しない。使用中・バージョン不一致・未反映変更を持つSandboxの内容を破棄しない。

## 7. Workspace Snapshotと再利用時の同期

HostのWorkspaceディレクトリはGuestへ直接マウントしない。

- Git追跡済みファイルの未Commit変更と、安全な未追跡の新規ソースファイルをSnapshotに含める。
- \`.git\`、Credential、Secret、特別なファイル、無許可のsymlinkや既存の除外対象はGuestへ直接転送しない。
- 除外だけで安全を推定せず、既存の秘密情報検査と明示的な転送許可契約を維持する。
- HostのHEAD、Index、作業ツリーとSnapshot Manifestの基準状態を保持する。

再利用時には、前回のHost同期基準と現在のHost状態およびGuest側の未反映変更を比較する。**Guestで未反映の変更がある場合、上書き同期しない。** 安全に更新できる変更だけを取り込み、競合時は旧Guest状態を保持して停止する。利用者が操作しない限り未反映の変更を破棄しない。

## 8. Sandbox内のGit履歴・Commit

Mountlessを維持したまま、検証済みの選択的Git Bundleを使い、Guest内に**独立したGit Repository**を構築する。

- Hostの\`.git\`のマウント・丸ごとコピーは禁止。
- Bundleで必要なRefとCommit履歴を持ち込み、その上に許可済みWorkspace Snapshot（未Commit・未追跡ファイルを含む）を再現する。
- \`git status\`、\`git diff\`、\`git log\`、ブランチ作成、\`git commit\`を通常利用できるようにする。
- Git Bundleには過去の削除済みファイルやSecretが含まれ得る。参照・到達オブジェクトの対象を制限し、転送前の機密性を検査する。安全を確認できない履歴は転送せずFail-Closedとする。
- HostのSSH Agent、認証設定、Git Push権限をGuestへ暗黙に渡さない。外部へのGit Pushは別途明示承認の対象。

Git Bundleは履歴の輸送手段であり、現在のHost Working Treeの未Commit内容を自動的に含めるものではない。この2つを別々に検証・復元する。

## 9. 認証とProvider

\`apm.yml\`はProvider/モデル選択のSSOTとする。Host側の既存Credential ProxyとDockerのCredential Bindingを再利用する。

- OpenAI OAuth: 既に登録済みのHost Broker/Proxy経由で使用する。SecretをSnapshot、APM、Git、Guest環境へ平文コピーしない。
- Cloudflare AI Gateway: APMで選択されたProviderに応じて利用可否を自動決定し、検証済みの非Secret IDと既存SecretのBindingを解決する。毎回\`--use-cloudflare-ai-gateway\`を入力する必要をなくす。
- 登録済みCredentialが欠ける・期限切れ・Brokerが利用不能なら明示的に案内し、安全に停止する。勝手にGuestへTokenを埋め込まない。
- 外部推論の許可はHost側の明示的で取り消し可能な利用ポリシーに基づく。初回の確認なく課金可能な推論を有効化しない。モデル選択自体はAPMに従う。
- OpenCode v1のCredential、環境、設定には変更を加えない。

## 10. TUI終了後のCollect / Preview / Apply

TUI終了後、Launcherは変更を自動**収集**して提示する。自動**適用**はしない。

1. GuestのCommit履歴（Bundle等）と未Commit差分を隔離されたHost側の一時領域/参照に収集する。
2. File Manifest、Secret検査、Git履歴、HostのHEAD・Index・作業ツリーの現在状態を照合する。
3. 追加・変更・削除・Commit一覧と適用可否を提示する。
4. **Human Ownerの1回の承認**で、安全に成立する変更だけをHostへ適用する。
5. 承認拒否、失敗、競合時はGuestの変更と隔離済み成果を保持する。

Git Commitは履歴を保持し、安全にFast-forwardできる場合のみHostの対象ブランチへ取り込む。未Commit変更は別途差分として適用する。Hostブランチが分岐している場合、無断Merge/Rebase/Reset/Force Pushを行わず、隔離Refへ保存して停止する。

Hostが起動・同期時から更新された場合や、Index/Worktreeの変更が衝突する場合も自動上書きしない。適用操作は競合検出から書込みまでの整合性を再確認し、部分的な失敗でもデータを失わない。承認前にHostの現行HEADやファイルを変更しない。

## 11. エラー・保全条件

- Mount、Sandbox ID、Artifact、Runtime、Session Receipt、Credential、Manifestの不一致はFail-Closed。
- 同時起動時のLease重複、未回収のGuest変更、同期競合、Secret検出では既存データを保存して停止または安全な独立Sandboxへ分岐する。
- \`sbx exec\`が停止中Sandboxを起動し得る点を考慮し、\`--dry-run\`や情報表示の経路では副作用を避ける。
- Sandbox削除、作業データ破棄、HostのGit履歴改変、Credential更新、外部Git Pushは通常の\`oc2\`操作に暗黙に含めない。
- デバッグ用ログとSession状態にToken、認証DB、Secret本文を記録しない。

## 12. 受入条件

1. Gitリポジトリのルートで\`oc2\`のみを実行して、APM指定バージョンのOpenCode TUIを起動できる。
2. APMとLockが一致しないバージョンでは、安全に起動を拒否する。
3. 初回起動後、空きSandboxを正しいIdentityで再利用でき、使用中の多重起動は独立Sandboxを使う。
4. 既存Sandbox再利用時にHostの最新Workspaceを同期し、Guest未反映変更を失わない。
5. Hostの未Commit・安全な未追跡ファイルをGuestで利用できる。Hostの\`.git\`やSecretを直接共有しない。
6. GuestでGit履歴閲覧、ブランチ作成、Commit、未Commit編集が機能する。
7. TUI終了時にCommit・未Commit差分を収集・提示し、Human Ownerの1回の承認で安全にHostへ反映できる。
8. HostのHEAD分岐、並行編集、Secret混入、同期不整合ではデータを保持してFail-Closedする。
9. APMに基づくOpenAI OAuth/Cloudflareの認証解決が動作し、Secretの直接転送や無承認推論を行わない。
10. 既存OC2 Phase 5機能、OpenCode v1環境、隔離・固定Artifact検証を回帰させない。

## 13. 非目標・停止条件・後続判断

**非目標:** Direct Mount化、既存Runtime全面再実装、OpenCode v1改変、任意Plugin/MCPの解禁、任意未検証CLI起動、無承認Git Push、無断Host書込み、既存Sandboxの自動破棄。

**設計完了条件:** 承認済みの操作体験、安全境界、Git履歴・未Commit同期、競合時挙動と受入条件を1文書で定義すること。

**停止条件:** 本Designの記録・Commit・Push後は終了する。実装、Implementation Plan、独立レビュー、PR、Merge、Sandbox実機操作、Credential変更は、別途Human Ownerが承認するまで自動開始しない。
