# AI-Native Stacked PR Workflow: 完全定義書 (v1.4.2)

このドキュメントは、AIエージェントによる開発の「統制」と「品質」を担保するための最上位プロトコル（憲法）である。AIはこの規則を一文字たりとも違えてはならず、自身の学習データにある一般的な慣習よりも本規定を優先しなければならない。

---

## 0. メタデータ定義

```yaml
workflow_metadata:
  name: Guarded Stacked PR Workflow
  version: 1.4.2
  policy:
    human_in_the_loop: true
    naming_enforcement: "STRICT" # 命名規則違反はタスク失敗とみなす
    sync_method: "rebase"
  naming_convention:
    base: "feature/phase[N]-[機能名]__base"
    task: "feature/phase[N]-task[M]-[サブ機能名]"
```

---

## 1. 命名規則の視覚的パターン (Naming Patterns)

AIはブランチ作成時、以下の正規表現パターンを厳守すること。**一般的な `feat/` や `fix/` は使用禁止である。**

*   **集約ブランチ (Base):**
    `feature/phase1-redis-monitor__base`
    (構成: `feature/` + `フェーズ` + `-` + `機能名` + `__base`)
*   **タスクブランチ (Task):**
    `feature/phase1-task1-interface-def`
    (構成: `feature/` + `フェーズ` + `-task` + `連番` + `-` + `サブ機能名`)

---

## 2. ブランチ運用フロー（詳細手順）

### STEP 1: 環境構築
1. **baseブランチの作成**
   - `master` から分岐し、必ず `__base` で終わる名称にする。
   - 例: `git checkout -b feature/phase1-redis-monitor__base`
2. **最初のタスクブランチの作成**
   - `__base` から分岐する。
   - 例: `git checkout -b feature/phase1-task1-interface-def`

### STEP 2: 実装とスタッキング
1. **タスクの実装**
   - **200 LOC 以内** / **単体テスト 100% PASS** を絶対条件とする。
2. **PR（下書き）の作成**
   - **重要:** PRのベース（マージ先）は必ず上記で作成した `__base` ブランチに設定すること。
3. **後続タスクの開始**
   - 直前のタスクから分岐: `task1` -> `task2`
   - 例: `git checkout -b feature/phase1-task2-redis-impl`

### STEP 3: 伝播（Rebase）
1. 先行タスクが `__base` にマージされたら、即座に `__base` を後続の全タスクブランチに `git rebase` し、常に最新のコンテキストを維持せよ。

---

## 3. AIエージェント禁止事項 (Forbidden Actions)

AIは以下の操作を**いかなる理由があっても実行してはならない**。

1.  **Generic Naming**: `feat/`, `fix/`, `hotfix/`, `docs/` 等、本規定外の接頭辞を使用すること。
2.  **Direct Commit to Base**: `__base` ブランチに対して直接 `push` すること（必ず PR を経由せよ）。
3.  **Auto-Merge to Master**: `master` へのマージを実行すること（人間が最終承認する）。
4.  **Implicit Context**: 前のタスクの差分を取り込まずに（Rebaseせずに）次の実装を進めること。

---

## 4. PR作成時のチェックリスト (Internal Audit)

AIは PR を作成する直前に、以下の思考プロセスを必ず経ること。

*   [ ] **ブランチ名は `feature/phase[N]-task[M]-...` になっているか？**
*   [ ] **PRのターゲットは `__base` ブランチに設定されているか？** (masterになっていないか？)
*   [ ] **差分は 200 LOC 以下に収まっているか？**
*   [ ] **これは「ついで」の修正を含まない、単一の目的（Atomic Change）か？**

---

## 5. AI完了報告テンプレート

AIは進捗を報告する際、必ず以下の形式を使用し、自身がルールを守っていることを証明せよ。

> **AI**: Phase [N] のタスクを以下の通り実行しました。
> **作成ブランチ**: `feature/phase[N]-task[M]-[名称]`
> **ターゲット**: `feature/phase[N]-[機能名]__base`
> **ステータス**: 差分 [XXX] LOC / テスト [PASS] / リベース [完了]
> **次のアクション**: `task[M+1]` の実装に移行します。

---

## 6. 結論
このプロトコルを遵守できないAIは、開発パートナーとしての資格を失う。
本規定は、AIの強力な計算能力を「秩序あるコード資産」へと変換するための唯一の道である。
