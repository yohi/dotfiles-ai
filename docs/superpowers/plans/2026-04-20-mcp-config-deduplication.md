# MCP Config Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically prevent MCP tool duplication in client agent configurations by filtering out servers already provided by the Docker MCP Gateway.

**Architecture:** Modify the `_scripts/render-mcp-configs.py` script to identify Gateway-hosted servers (`type: server`) and remove them from individual agent configurations if the agent is configured to use the Gateway (`docker-mcp` or `docker-mcp-local`).

**Tech Stack:** Python 3, `json`, `yaml`, `json5`

---

### Task 1: Identify Gateway-enabled Servers and Implement Deduplication Logic

**Files:**
- Modify: `_scripts/render-mcp-configs.py`
- Test: `_scripts/test_render_mcp.py` (Assuming a basic test script can be created or exists. We'll create a minimal one if needed, or rely on manual verification via `make sync-mcp`). For this plan, we will rely on manual verification using the existing script structure, as it's a script rather than a standard module.

- [ ] **Step 1: Write the failing test / verification setup**
We will verify this by temporarily adding a gateway-hosted server to the gemini configuration in `mcp/servers.yaml` and checking that `render-mcp-configs.py` outputs a skip message and doesn't include it in `gemini/settings.json`.

```bash
# Modify mcp/servers.yaml to add filesystem to gemini
sed -i 's/docker-mcp: { inherit: "docker-mcp" }/docker-mcp: { inherit: "docker-mcp" }\n      filesystem: { inherit: "filesystem" }/' mcp/servers.yaml
# Run the sync script
make sync-mcp
# Check if filesystem is in gemini/settings.json (it currently will be, which is the "fail" state)
grep -q '"filesystem":' gemini/settings.json && echo "FAIL: filesystem found" || echo "PASS: filesystem not found"
```

- [ ] **Step 2: Implement the deduplication logic in `render-mcp-configs.py`**
Locate the section in `_scripts/render-mcp-configs.py` where `processed_servers` are generated (around line 258, after `processed_servers` is populated but before `replace_placeholders`).

```python
        # Identify if the gateway is used by this agent
        uses_gateway = any(
            s_name in {"docker-mcp", "docker-mcp-local"}
            for s_name in raw_servers.keys()
        )

        # Gateway-hosted servers are those with type "server" in the main config
        gateway_hosted_servers = {
            name for name, cfg in all_servers.items() if cfg.get("type") == "server"
        }

        # Deduplicate: if gateway is used, remove servers that the gateway already provides
        if uses_gateway:
            servers_to_remove = []
            for s_name in processed_servers.keys():
                # Don't remove the gateway itself
                if s_name in {"docker-mcp", "docker-mcp-local"}:
                    continue
                # If the server is hosted by the gateway, mark for removal
                if s_name in gateway_hosted_servers:
                    servers_to_remove.append(s_name)
                    print(f"Skipping '{s_name}' for agent '{agent_name}' because it is provided by the Gateway.")
            
            for s_name in servers_to_remove:
                processed_servers.pop(s_name, None)
```
Insert this logic right before:
```python
        # プレースホルダ置換
        servers = replace_placeholders(processed_servers, gateway_url)
```

- [ ] **Step 3: Run verification to ensure it passes**
```bash
make sync-mcp
# Check if filesystem is in gemini/settings.json (it should NOT be, and a skip message should be printed)
grep -q '"filesystem":' gemini/settings.json && echo "FAIL: filesystem found" || echo "PASS: filesystem not found"
```

- [ ] **Step 4: Cleanup the test modification**
```bash
git checkout mcp/servers.yaml
make sync-mcp
```

- [ ] **Step 5: Commit**
```bash
git add _scripts/render-mcp-configs.py
git commit -m "fix(mcp): auto-deduplicate gateway-hosted servers from agent configs"
```
