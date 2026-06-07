# Skill Directory Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `.agents/skills` the runtime skill directory used by SkillPort MCP and by native agent skill discovery through symlink adapters.

**Architecture:** APM remains responsible for installing external skills into `.agents/skills`, while local custom skills remain authored under `agent-skills/custom` and are exposed through `.agents/skills/custom`. Native agent directories such as `~/.opencode/skills`, `~/.claude/skills`, and `~/.skillport/skills` become non-authoritative symlink adapters that point to `.agents/skills`, so slash/native skill discovery and MCP loading use the same runtime tree.

**Tech Stack:** Make, Bash, APM, SkillPort MCP, pytest, shell integration checks

---

## Scope and invariants

This plan is a follow-up to `docs/superpowers/plans/2026-06-06-apm-optimization.md`. That plan moved SkillPort MCP toward `.agents/skills`; this plan closes the remaining native-directory drift.

Required invariants after implementation:

1. `.agents/skills` is the runtime skill directory for MCP and native discovery.
2. `agent-skills/custom` remains the edit location for local custom skills unless a later migration explicitly moves custom authoring.
3. `~/.opencode/skills`, `~/.claude/skills`, and `~/.skillport/skills` are symlink adapters to `.agents/skills`.
4. No generated config may point SkillPort at `agent-skills` for runtime loading.
5. Existing real directories at native adapter paths are never overwritten silently; they are backed up or skipped with a clear warning.
6. `README.md` changes require explicit user approval before implementation.

## File structure

- Modify `_mk/variables.mk`: define canonical runtime and custom skill directories.
- Create `_mk/skills-adapters.mk`: centralize symlink adapter targets and checks.
- Modify `Makefile`: include `_mk/skills-adapters.mk` and run adapter setup during `sync-agents`.
- Modify `_mk/opencode.mk`: point OpenCode's skills adapter at `.agents/skills` instead of `opencode/skills`.
- Modify `_mk/claude.mk`: add Claude skills adapter setup and diagnostics.
- Modify `_mk/skillport.mk`: point `~/.skillport/skills` at `.agents/skills`.
- Modify `_mk/main.mk`: stop deleting `.agents` from `make clean`.
- Modify `_mk/test.mk`: include the new adapter test in `test-all`.
- Create `_scripts/test-skill-adapters.sh`: verify adapter symlinks and SkillPort runtime path consistency.
- Modify `_scripts/sync_agents.sh`: update comments and canonical scanning language.
- Modify `apm.yml`: ensure SkillPort MCP and APM skill deployment are aligned to `.agents/skills`; remove `.claude/skills` as a copied deployment target if present.
- Regenerate `apm.lock.yaml`: remove stale `.claude/skills/*` deployed entries.
- Review generated configs: `.mcp.json`, `opencode.json`, `.codex/config.toml`, `antigravity/mcp_config.json`, `.agents/mcp_config.json`.
- Documentation requiring approval: `README.md`.
- Documentation safe to update after approval of direction: `SPEC.md`, `_docs/guides/skillport.md`, `agent-skills/README.md`, `global-rules/AGENTS.global.md`.

---

### Task 1: Add failing adapter verification

**Files:**
- Create: `_scripts/test-skill-adapters.sh`
- Modify: `_mk/test.mk`

- [ ] **Step 1: Create the failing adapter test**

Create `_scripts/test-skill-adapters.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_SKILLS_DIR="$REPO_ROOT/.agents/skills"

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

assert_dir() {
    path="$1"
    [ -d "$path" ] || fail "directory not found: $path"
}

assert_link_target() {
    link_path="$1"
    expected="$2"
    [ -L "$link_path" ] || fail "not a symlink: $link_path"
    actual="$(readlink "$link_path")"
    [ "$actual" = "$expected" ] || fail "$link_path points to $actual, expected $expected"
}

assert_no_runtime_skillport_agent_skills() {
    if grep -R "SKILLPORT_SKILLS_DIR.*agent-skills" \
        "$REPO_ROOT/.mcp.json" \
        "$REPO_ROOT/opencode.json" \
        "$REPO_ROOT/.codex/config.toml" \
        "$REPO_ROOT/antigravity/mcp_config.json" \
        "$REPO_ROOT/.agents/mcp_config.json" 2>/dev/null; then
        fail "generated config still points SkillPort at agent-skills"
    fi
}

assert_dir "$RUNTIME_SKILLS_DIR"
assert_dir "$RUNTIME_SKILLS_DIR/using-superpowers"
assert_dir "$RUNTIME_SKILLS_DIR/custom"

assert_link_target "$HOME/.opencode/skills" "$RUNTIME_SKILLS_DIR"
assert_link_target "$HOME/.claude/skills" "$RUNTIME_SKILLS_DIR"
assert_link_target "$HOME/.skillport/skills" "$RUNTIME_SKILLS_DIR"

assert_no_runtime_skillport_agent_skills

printf 'PASS: skill adapters verified.\n'
```

- [ ] **Step 2: Make the test executable**

Run:

```bash
chmod +x _scripts/test-skill-adapters.sh
```

Expected: command exits 0.

- [ ] **Step 3: Run the test and verify it fails before implementation**

Run:

```bash
bash _scripts/test-skill-adapters.sh
```

Expected: FAIL with at least one of these messages:

```text
FAIL: not a symlink: $HOME/.claude/skills
FAIL: $HOME/.opencode/skills points to .../opencode/skills, expected .../.agents/skills
FAIL: generated config still points SkillPort at agent-skills
```

- [ ] **Step 4: Add the test to `test-all`**

Modify `_mk/test.mk` so the shell test loop includes `_scripts/test-skill-adapters.sh`. No special-case skip is needed.

The relevant block should remain:

```makefile
	for f in _scripts/test-*.sh; do \
		[[ "$$f" == "_scripts/test-mcp-connectivity.sh" ]] && continue; \
		echo "Running bash test: $$f"; \
		bash "$$f" || exit 1; \
	done'
```

- [ ] **Step 5: Commit**

```bash
git add _scripts/test-skill-adapters.sh _mk/test.mk
git commit -m "test: add skill directory adapter checks"
```

---

### Task 2: Centralize skill directory variables

**Files:**
- Modify: `_mk/variables.mk`

- [ ] **Step 1: Add canonical skill path variables**

Modify `_mk/variables.mk` near the existing common path definitions:

```makefile
# Common paths
HOME_DIR := $(HOME)
REPO_ROOT := $(CURDIR)
GLOBAL_RULES_DIR := $(REPO_ROOT)/global-rules
AGENT_SKILLS_DIR := $(REPO_ROOT)/agent-skills
AGENT_CUSTOM_SKILLS_DIR := $(AGENT_SKILLS_DIR)/custom
RUNTIME_SKILLS_DIR := $(REPO_ROOT)/.agents/skills
RUNTIME_CUSTOM_SKILLS_DIR := $(RUNTIME_SKILLS_DIR)/custom
```

- [ ] **Step 2: Verify Make can resolve the variables**

Run:

```bash
make -pn | grep -E '^(AGENT_CUSTOM_SKILLS_DIR|RUNTIME_SKILLS_DIR|RUNTIME_CUSTOM_SKILLS_DIR) :='
```

Expected output includes:

```text
AGENT_CUSTOM_SKILLS_DIR := $(REPO_ROOT)/agent-skills/custom
RUNTIME_SKILLS_DIR := $(REPO_ROOT)/.agents/skills
RUNTIME_CUSTOM_SKILLS_DIR := $(REPO_ROOT)/.agents/skills/custom
```

- [ ] **Step 3: Commit**

```bash
git add _mk/variables.mk
git commit -m "config: define canonical skill directories"
```

---

### Task 3: Add shared symlink adapter targets

**Files:**
- Create: `_mk/skills-adapters.mk`
- Modify: `Makefile`

- [ ] **Step 1: Create `_mk/skills-adapters.mk`**

Create `_mk/skills-adapters.mk`:

```makefile
# ============================================================
# Skill directory adapters
# ============================================================

SKILL_ADAPTER_TARGETS := \
	$(HOME_DIR)/.opencode/skills \
	$(HOME_DIR)/.claude/skills \
	$(HOME_DIR)/.skillport/skills

.PHONY: setup-skill-adapters check-skill-adapters sync-skills-to-agents

define link_skill_adapter
	@if [ -e "$(1)" ] && [ ! -L "$(1)" ]; then \
		backup="$(1).bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "[!] Existing skill directory is not a symlink; moving it to $$backup"; \
		mv "$(1)" "$$backup"; \
	fi; \
	mkdir -p "$$(dirname "$(1)")"; \
	ln -sfn "$(RUNTIME_SKILLS_DIR)" "$(1)"; \
	echo "[+] Linked $(1) -> $(RUNTIME_SKILLS_DIR)"
endef

setup-skill-adapters: ## Link native skill directories to .agents/skills
	@if [ ! -d "$(RUNTIME_SKILLS_DIR)" ]; then \
		echo "[x] Runtime skills directory not found: $(RUNTIME_SKILLS_DIR)"; \
		echo "[i] Run 'apm install' before setting up skill adapters."; \
		exit 1; \
	fi
	$(call link_skill_adapter,$(HOME_DIR)/.opencode/skills)
	$(call link_skill_adapter,$(HOME_DIR)/.claude/skills)
	$(call link_skill_adapter,$(HOME_DIR)/.skillport/skills)

sync-skills-to-agents: setup-skill-adapters ## Backward-compatible alias for native skill adapters

check-skill-adapters: ## Verify native skill directories point at .agents/skills
	@bash _scripts/test-skill-adapters.sh
```

- [ ] **Step 2: Include the new Make module**

Modify `Makefile` after `_mk/skillport.mk` and before `_mk/sync-agents.mk`:

```makefile
-include _mk/skillport.mk
-include _mk/skills-adapters.mk
-include _mk/sync-agents.mk
```

- [ ] **Step 3: Run the new target before implementation-dependent fixes**

Run:

```bash
make setup-skill-adapters
```

Expected: if `.agents/skills` exists, output includes:

```text
[+] Linked .../.opencode/skills -> .../.agents/skills
[+] Linked .../.claude/skills -> .../.agents/skills
[+] Linked .../.skillport/skills -> .../.agents/skills
```

If `.agents/skills` does not exist, expected output includes:

```text
[x] Runtime skills directory not found: .../.agents/skills
[i] Run 'apm install' before setting up skill adapters.
```

- [ ] **Step 4: Commit**

```bash
git add Makefile _mk/skills-adapters.mk
git commit -m "feat: add native skill directory adapters"
```

---

### Task 4: Wire adapters into existing setup targets

**Files:**
- Modify: `Makefile`
- Modify: `_mk/opencode.mk`
- Modify: `_mk/claude.mk`
- Modify: `_mk/skillport.mk`

- [ ] **Step 1: Run adapters during `sync-agents`**

Modify `Makefile` so `sync-agents` runs adapter setup after APM install and before config compilation:

```makefile
sync-agents: ## Run APM install, compile, generate Antigravity config, and sync agents
	@apm install
	@$(MAKE) setup-skill-adapters
	@apm compile
	@$(PYTHON) _scripts/sync_antigravity.py
	@$(MAKE) sync-agents-core
```

- [ ] **Step 2: Update OpenCode's dotfiles skills source**

Modify `_mk/opencode.mk` near the path definitions:

```makefile
OPENCODE_SKILLS_PATH ?= $(OPENCODE_HOME)/skills
OPENCODE_DOTFILES_SKILLS ?= $(RUNTIME_SKILLS_DIR)
```

Keep `setup-opencode` calling `link_config` for skills. This preserves the existing backup behavior while changing the adapter target.

- [ ] **Step 3: Add Claude skills adapter setup**

Modify `_mk/claude.mk` in `setup-claude`, after the `settings.json` block and before `statusline.sh`:

```makefile
	@# skills/
	@if [ -e "$(HOME_DIR)/.claude/skills" ] && [ ! -L "$(HOME_DIR)/.claude/skills" ]; then \
		backup="$(HOME_DIR)/.claude/skills.bak.$$(date +%Y%m%d%H%M%S)"; \
		echo "[!] Existing Claude skills directory is not a symlink; moving it to $$backup"; \
		mv "$(HOME_DIR)/.claude/skills" "$$backup"; \
	fi
	@ln -sfn "$(RUNTIME_SKILLS_DIR)" "$(HOME_DIR)/.claude/skills"
```

- [ ] **Step 4: Update Claude diagnostics**

Modify `_mk/claude.mk` in `check-claude`, after the `settings.json` check:

```makefile
	@if [ -L "$(HOME_DIR)/.claude/skills" ]; then \
		target="$$(readlink "$(HOME_DIR)/.claude/skills")"; \
		if [ "$$target" = "$(RUNTIME_SKILLS_DIR)" ]; then \
			echo "[+] skills: linked to $(RUNTIME_SKILLS_DIR)"; \
		else \
			echo "[x] skills: linked to $$target, expected $(RUNTIME_SKILLS_DIR)"; \
		fi; \
	else \
		echo "[x] skills: not linked. Run 'make setup-claude'."; \
	fi
```

- [ ] **Step 5: Repoint SkillPort setup**

Modify `_mk/skillport.mk` so `setup-skillport` links `~/.skillport/skills` to `$(RUNTIME_SKILLS_DIR)`, not `$(AGENT_SKILLS_DIR)`.

The relevant assignment should become:

```makefile
SKILLPORT_RUNTIME_SKILLS_DIR ?= $(RUNTIME_SKILLS_DIR)
```

The symlink command inside `setup-skillport` should become:

```makefile
ln -sfn "$(SKILLPORT_RUNTIME_SKILLS_DIR)" "$(SKILLPORT_SKILLS_DIR)"
```

- [ ] **Step 6: Verify adapter wiring**

Run:

```bash
make setup-opencode
make setup-claude
make setup-skillport
bash _scripts/test-skill-adapters.sh
```

Expected: the final command prints:

```text
PASS: skill adapters verified.
```

- [ ] **Step 7: Commit**

```bash
git add Makefile _mk/opencode.mk _mk/claude.mk _mk/skillport.mk
git commit -m "fix: wire native skill directories to runtime adapter"
```

---

### Task 5: Stop deleting the runtime skill directory

**Files:**
- Modify: `_mk/main.mk`

- [ ] **Step 1: Remove `.agents` from destructive clean**

Modify `_mk/main.mk` so the `clean` target does not delete `.agents`.

Replace this kind of command:

```makefile
	@rm -rf "$(REPO_ROOT)/.claude" "$(REPO_ROOT)/.gemini" "$(REPO_ROOT)/.agents"
```

with:

```makefile
	@rm -rf "$(REPO_ROOT)/.claude" "$(REPO_ROOT)/.gemini"
	@echo "[i] Preserved runtime skills directory: $(RUNTIME_SKILLS_DIR)"
```

- [ ] **Step 2: Verify clean preserves runtime skills**

Run:

```bash
test -d .agents/skills
make clean
test -d .agents/skills
```

Expected: all commands exit 0, and output includes:

```text
[i] Preserved runtime skills directory: .../.agents/skills
```

- [ ] **Step 3: Commit**

```bash
git add _mk/main.mk
git commit -m "fix: preserve runtime skills during clean"
```

---

### Task 6: Align SkillPort runtime configuration

**Files:**
- Modify: `.skillportrc`
- Modify: `_scripts/opencode-wrapper.sh`
- Modify: `_scripts/sync_agents.sh`
- Modify: `_scripts/sync_antigravity.py` or `_scripts/render-antigravity-config.py` depending on which generator is current
- Modify: `tests/test_sync_antigravity.py`

- [ ] **Step 1: Repoint `.skillportrc` to runtime skills**

Modify `.skillportrc`:

```yaml
skills_dir: ./.agents/skills
```

- [ ] **Step 2: Keep OpenCode wrapper runtime export unchanged**

Verify `_scripts/opencode-wrapper.sh` contains:

```bash
export SKILLPORT_SKILLS_DIR="$REPO_ROOT/.agents/skills"
```

If it does not, change it to that exact line.

- [ ] **Step 3: Fix `sync_agents.sh` header and runtime wording**

Modify the header comment in `_scripts/sync_agents.sh` to match the real behavior:

```bash
# description: Generate agent-skills/AVAILABLE_SKILLS.md from the runtime
# .agents/skills tree plus local custom skills under agent-skills/custom.
```

Do not claim it updates `AGENTS.md` or `global-rules/AGENTS.global.md` unless those files are actually added to `OUTPUT_FILES`.

- [ ] **Step 4: Extend Antigravity config test**

Modify `tests/test_sync_antigravity.py` so the test asserts the emitted SkillPort env points at `.agents/skills`.

Ensure the assertion remains:

```python
assert skillport["env"]["SKILLPORT_SKILLS_DIR"] == "/workspace/.agents/skills"
```

- [ ] **Step 5: Regenerate configs**

Run:

```bash
apm compile
$(PYTHON) _scripts/sync_antigravity.py
```

Expected: generated configs no longer contain `SKILLPORT_SKILLS_DIR` values ending in `/agent-skills`.

- [ ] **Step 6: Verify no generated runtime config points at `agent-skills`**

Run:

```bash
if grep -R "SKILLPORT_SKILLS_DIR.*agent-skills" .mcp.json opencode.json .codex/config.toml antigravity/mcp_config.json .agents/mcp_config.json 2>/dev/null; then exit 1; fi
```

Expected: command exits 0 with no output.

- [ ] **Step 7: Commit**

```bash
git add .skillportrc _scripts/opencode-wrapper.sh _scripts/sync_agents.sh tests/test_sync_antigravity.py
for generated in .mcp.json opencode.json .codex/config.toml antigravity/mcp_config.json .agents/mcp_config.json; do
    if [ -e "$generated" ]; then
        git add "$generated"
    else
        printf '[i] Generated config not present, skipping: %s\n' "$generated"
    fi
done
git commit -m "fix: align skillport runtime directory"
```

---

### Task 7: Remove copied native skill deployments from APM outputs

**Files:**
- Modify: `apm.yml`
- Regenerate: `apm.lock.yaml`

- [ ] **Step 1: Inspect current APM target skill outputs**

Run:

```bash
grep -n "\.claude/skills\|\.agents/skills\|SKILLPORT_SKILLS_DIR" apm.yml apm.lock.yaml
```

Expected before implementation: `apm.lock.yaml` shows both `.agents/skills/...` and `.claude/skills/...` entries.

- [ ] **Step 2: Keep SkillPort MCP env canonical**

Ensure the SkillPort MCP entry in `apm.yml` remains:

```yaml
env:
  SKILLPORT_SKILLS_DIR: "${env:PWD}/.agents/skills"
```

- [ ] **Step 3: Remove `.claude/skills` as a copied deployment target**

Modify `apm.yml` target configuration so external skills are deployed to `.agents/skills` only. If the target format exposes a Claude-specific skills destination, remove the `.claude/skills` destination from that target.

The desired generated lockfile property is:

```text
apm.lock.yaml contains .agents/skills entries and does not contain .claude/skills entries.
```

- [ ] **Step 4: Regenerate APM lockfile**

Run:

```bash
apm install
```

Expected: `apm.lock.yaml` is regenerated.

- [ ] **Step 5: Verify lockfile no longer preserves copied Claude skills**

Run:

```bash
grep -n "\.claude/skills" apm.lock.yaml && exit 1 || true
grep -n "\.agents/skills" apm.lock.yaml
```

Expected: first command finds no `.claude/skills` entries; second command finds `.agents/skills` entries.

- [ ] **Step 6: Commit**

```bash
git add apm.yml apm.lock.yaml
git commit -m "config: deploy skills only to runtime directory"
```

---

### Task 8: Update diagnostics and sync checks

**Files:**
- Modify: `_mk/test.mk`
- Modify: `_mk/skillport.mk`
- Modify: `_mk/opencode.mk`
- Modify: `_mk/claude.mk`
- Modify: `_scripts/validate_skills_locations.sh`

- [ ] **Step 1: Add `check-skill-adapters` to `test-all` prerequisites**

Modify `_mk/test.mk`:

```makefile
.PHONY: test-all
test-all: test-integrity check-skill-adapters ## Run all tests in the project
```

- [ ] **Step 2: Update SkillPort diagnostics**

Modify `_mk/skillport.mk` so `check-skillport` reports `~/.skillport/skills` pointing to `$(RUNTIME_SKILLS_DIR)`.

Expected check logic:

```makefile
	@if [ -L "$(SKILLPORT_SKILLS_DIR)" ] && [ "$$(readlink "$(SKILLPORT_SKILLS_DIR)")" = "$(RUNTIME_SKILLS_DIR)" ]; then \
		echo "[+] SkillPort skills adapter: $(SKILLPORT_SKILLS_DIR) -> $(RUNTIME_SKILLS_DIR)"; \
	else \
		echo "[x] SkillPort skills adapter is not linked to $(RUNTIME_SKILLS_DIR)"; \
	fi
```

- [ ] **Step 3: Update OpenCode diagnostics**

Ensure `_mk/opencode.mk` `check-opencode` verifies:

```makefile
$(OPENCODE_SKILLS_PATH) -> $(RUNTIME_SKILLS_DIR)
```

- [ ] **Step 4: Extend skill location validator**

Modify `_scripts/validate_skills_locations.sh` so it validates locations in both files:

```bash
FILES=(
    "global-rules/AGENTS.global.md"
    "agent-skills/AVAILABLE_SKILLS.md"
)
```

For each file, extract `<location>file://...` entries and verify the referenced relative path exists under the repo.

- [ ] **Step 5: Run diagnostics**

Run:

```bash
make check-skill-adapters
make check-skillport
make check-opencode
make check-claude
bash _scripts/validate_skills_locations.sh
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add _mk/test.mk _mk/skillport.mk _mk/opencode.mk _mk/claude.mk _scripts/validate_skills_locations.sh
git commit -m "test: verify skill adapter diagnostics"
```

---

### Task 9: Reconcile generated index and command naming drift

**Files:**
- Modify: `_scripts/sync_agents.sh`
- Modify: `agent-skills/AVAILABLE_SKILLS.md`
- Modify: `_mk/sync-agents.mk`

- [ ] **Step 1: Generate SkillPort docs from runtime tree plus custom skills**

Modify `_scripts/sync_agents.sh` so the temp directory is built from:

```bash
if [ -d ".agents/skills" ]; then
    cp -a .agents/skills/. "$tmp_skills_dir/"
fi

if [ -d "agent-skills/custom" ] && [ -n "$(ls -A agent-skills/custom 2>/dev/null)" ]; then
    mkdir -p "$tmp_skills_dir/custom"
    cp -a agent-skills/custom/. "$tmp_skills_dir/custom/"
fi
```

- [ ] **Step 2: Keep generated location prefixes stable**

Ensure the path rewrite section contains:

```bash
sed -i "s|${escaped_tmp_skills_dir}/custom/|agent-skills/custom/|g" "$tmp_file"
sed -i "s|${escaped_tmp_skills_dir}/|.agents/skills/|g" "$tmp_file"
```

- [ ] **Step 3: Confirm `sync-skills-to-agents` exists as alias**

Verify `_mk/skills-adapters.mk` contains:

```makefile
sync-skills-to-agents: setup-skill-adapters ## Backward-compatible alias for native skill adapters
```

- [ ] **Step 4: Run index generation**

Run:

```bash
bash _scripts/sync_agents.sh
```

Expected: `agent-skills/AVAILABLE_SKILLS.md` contains locations under `.agents/skills/` for runtime skills and `agent-skills/custom/` for custom authored skills.

- [ ] **Step 5: Verify generated index contains both skill classes**

Run:

```bash
grep -q '<name>using-superpowers</name>' agent-skills/AVAILABLE_SKILLS.md
grep -q '<name>agent-skill-architect</name>' agent-skills/AVAILABLE_SKILLS.md
grep -q '.agents/skills/using-superpowers/SKILL.md' agent-skills/AVAILABLE_SKILLS.md
grep -q 'agent-skills/custom/agent-skill-architect/SKILL.md' agent-skills/AVAILABLE_SKILLS.md
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add _scripts/sync_agents.sh agent-skills/AVAILABLE_SKILLS.md _mk/sync-agents.mk _mk/skills-adapters.mk
git commit -m "fix: generate skill index from runtime skills"
```

---

### Task 10: Update documentation after approval

**Files:**
- Modify after approval: `README.md`
- Modify: `SPEC.md`
- Modify: `_docs/guides/skillport.md`
- Modify: `agent-skills/README.md`
- Modify: `global-rules/AGENTS.global.md`

- [ ] **Step 1: Ask for README approval before changing it**

Before editing `README.md`, present this proposed drift fix to the user:

```text
README.md currently says agent-skills/ is the skill SSOT and claims make sync-skills-to-agents syncs agent-skills/ into .agents/skills/. The implementation will instead make .agents/skills the runtime skill directory and make native agent directories symlink adapters. May I update README.md to reflect this?
```

Expected: user explicitly approves README edits.

- [ ] **Step 2: Update README skill architecture section**

After approval, replace the relevant README language with:

```markdown
- **Runtime skill directory**: `.agents/skills/` is the directory read by SkillPort MCP and native agent skill discovery.
- **Custom skill authoring**: Local custom skills are edited under `agent-skills/custom/` and exposed through `.agents/skills/custom/`.
- **Native adapters**: `~/.opencode/skills`, `~/.claude/skills`, and `~/.skillport/skills` are symlinks to `.agents/skills/`.
- **Synchronization**: `make sync-agents` runs APM install/compile, config generation, skill adapter setup, and SkillPort index generation.
```

- [ ] **Step 3: Update `SPEC.md`**

Replace references that call `agent-skills/` the universal SSOT with:

```markdown
`.agents/skills/` is the runtime skill directory for all agents. `agent-skills/custom/` is the authoring location for local custom skills and is exposed through `.agents/skills/custom/` during synchronization.
```

- [ ] **Step 4: Update `_docs/guides/skillport.md`**

Add this operational rule:

```markdown
SkillPort MCP reads skills from `.agents/skills/`. Do not configure SkillPort runtime loading to read from `agent-skills/`; that directory is reserved for local custom skill authoring and generated indexes.
```

- [ ] **Step 5: Update `agent-skills/README.md`**

Replace the SSOT claim with:

```markdown
`agent-skills/custom/` contains local custom skill source files. Runtime loading happens from `.agents/skills/`, which is populated by APM and connected to native agent directories by symlink adapters.
```

- [ ] **Step 6: Update `global-rules/AGENTS.global.md`**

Replace the skill reference line with:

```markdown
- **Agent Skills**: Runtime skills are exposed through `.agents/skills/`; local custom skill sources live under `agent-skills/custom/`.
```

- [ ] **Step 7: Commit**

```bash
git add README.md SPEC.md _docs/guides/skillport.md agent-skills/README.md global-rules/AGENTS.global.md
git commit -m "docs: clarify runtime skill directory adapters"
```

---

### Task 11: Full verification

**Files:**
- Verify only: no planned edits

- [ ] **Step 1: Run adapter verification**

Run:

```bash
make check-skill-adapters
```

Expected:

```text
PASS: skill adapters verified.
```

- [ ] **Step 2: Run sync flow**

Run:

```bash
make sync-agents
```

Expected: APM install and compile succeed, adapters are linked, Antigravity config is generated, and `sync-agents-core` completes.

- [ ] **Step 3: Run project tests**

Run:

```bash
make test-all
```

Expected: all shell checks and pytest tests pass.

- [ ] **Step 4: Verify no runtime SkillPort config points at `agent-skills`**

Run:

```bash
if grep -R "SKILLPORT_SKILLS_DIR.*agent-skills" .mcp.json opencode.json .codex/config.toml antigravity/mcp_config.json .agents/mcp_config.json 2>/dev/null; then exit 1; fi
```

Expected: command exits 0 with no output.

- [ ] **Step 5: Verify lockfile does not copy skills to Claude native directory**

Run:

```bash
grep -n "\.claude/skills" apm.lock.yaml && exit 1 || true
```

Expected: command exits 0.

- [ ] **Step 6: Run lint-relevant checks for touched shell scripts**

Run:

```bash
shellcheck _scripts/test-skill-adapters.sh _scripts/sync_agents.sh _scripts/opencode-wrapper.sh
```

Expected: shellcheck exits 0.

- [ ] **Step 7: Final commit if verification fixes were needed**

```bash
git add _scripts/test-skill-adapters.sh _scripts/sync_agents.sh _scripts/opencode-wrapper.sh apm.yml apm.lock.yaml
git commit -m "fix: complete skill adapter verification"
```

---

## Self-review

- Spec coverage: The plan covers `.agents/skills` runtime SSOT, native directory adapters, SkillPort MCP path convergence, APM lock drift, generated config drift, docs drift, and tests.
- Placeholder scan: No step uses undefined work such as "handle edge cases" without concrete commands or code.
- Type and naming consistency: The plan consistently uses `RUNTIME_SKILLS_DIR` for `.agents/skills`, `AGENT_CUSTOM_SKILLS_DIR` for `agent-skills/custom`, and `setup-skill-adapters` for native adapter creation.
- Known approval gate: `README.md` is listed as requiring explicit approval before edits.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-08-skill-directory-adapters.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
