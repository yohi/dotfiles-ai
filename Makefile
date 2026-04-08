# 1. Base Rules (Provided by parent or local)
-include _mk/core.mk
-include _mk/help.mk

# 2. Variables & Idempotency
-include _mk/variables.mk
-include _mk/idempotency.mk

# 3. Orchestrator (Main Workflow)
include _mk/main.mk

# 4. Component Modules
-include _mk/claude.mk
-include _mk/gemini.mk
-include _mk/codex.mk
-include _mk/opencode.mk
-include _mk/antigravity.mk
-include _mk/superclaude.mk
-include _mk/skillport.mk
-include _mk/sync-agents.mk
-include _mk/mcp.mk
-include _mk/superpowers.mk
-include _mk/ide-cursor.mk
-include _mk/ide-vscode.mk
-include _mk/test-ide-cursor.mk
