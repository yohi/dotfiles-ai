# Migrate Superpowers to SkillPort Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `superpowers` の管理を `_mk/superpowers.mk` による独自管理から `skillport` による統合管理へ移行する。

**Architecture:**
- `_mk/superpowers.mk` を刷新し、`git clone` の代わりに `skillport add` および `skillport update` を使用するように変更する。
- `superpowers` のスキルは `agent-skills/superpowers/` 配下に名前空間を持って配置される。
- `skillport doc` によって `AGENTS.md` 等のスキルテーブルが自動更新されるように `_mk/sync-agents.mk` と連携する。

**Tech Stack:**
- skillport (CLI)
- GNU Make

---

### Task 1: Research and Cleanup (Verification)

**Files:**
- Modify: `_mk/superpowers.mk`
- Modify: `.skillportrc`

**Step 1: Check existing skills in agent-skills/superpowers**
Run: `ls -d agent-skills/superpowers/*/`
Expected: 14 subdirectories should exist.

**Step 2: Update .skillportrc to ensure instructions include superpowers if needed**
Modify: `.skillportrc` to include `agent-skills/superpowers/*/SKILL.md` in indexing if required by future skillport versions. (Currently skillport recurses, so this may be minimal).

### Task 2: Refactor _mk/superpowers.mk

**Files:**
- Modify: `_mk/superpowers.mk`

**Step 1: Rewrite update-superpowers target**
Replace Git clone logic with `skillport add` logic.

```makefile
update-superpowers: ## skillport を使用して superpowers を更新
	@echo "🔄 superpowers: skillport を使用してインポート/更新中..."
	@uvx skillport add obra/superpowers skills/ --namespace superpowers --yes --force
	@uvx skillport update --all
```

**Step 2: Remove redundant link targets**
`skillport` が `agent-skills/` に直接ファイルを配置するため、`link-superpowers-*` ターゲットを簡略化、あるいは `skillport sync` に役割を譲る。
ただし、Gemini CLI や Antigravity のための特定のディレクトリへのリンクが必要な場合は、`agent-skills/superpowers` からリンクを張るように修正する。

### Task 3: Integrate with sync-agents.mk

**Files:**
- Modify: `_mk/sync-agents.mk`

**Step 1: Ensure sync-skillport-doc covers the new namespace**
Run: `make sync-skillport-doc`
Expected: `AGENTS.md` should be updated with superpowers skills.

### Task 4: Final Validation and Cleanup

**Step 1: Run full setup**
Run: `make setup-superpowers sync-agents`
Expected: All skills present in `agent-skills/` and synced to agents.

**Step 2: Remove legacy directory**
Run: `rm -rf ~/.gemini/superpowers`
Expected: Legacy source is removed, system relies on `agent-skills/superpowers`.

**Step 3: Commit changes**
Run: `git add . && git commit -m "feat: migrate superpowers management to skillport"`
