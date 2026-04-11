# Fix Code Review Issues Implementation Plan

> **前提:** このドキュメント内のコマンドはすべてリポジトリルート (`$REPO_ROOT`) から実行することを想定しています。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** コードレビューで発見された Critical 2件・Important 4件・Minor 1件の計7バグを修正し、`make setup-docker-mcp` が正常に動作する状態にする。

**Architecture:** シェルスクリプト・設定テンプレートを中心とした修正。`setup-docker-mcp.sh` の二重書き込みを削除し、`sync-mcp-configs.sh` への一元化を完成させる。各 Task は独立しており、任意の順序で実行可能（ただし Task 1・2 は同一ファイルへの変更なので連続して行うことを推奨）。

**Tech Stack:** Bash, Python (uv), systemd, JSONC テンプレート

---

## ファイル変更マップ

| ファイル | 変更種別 | 対応 Issue |
|---|---|---|
| `_scripts/setup-docker-mcp.sh` | Modify | C1, C2 |
| `_scripts/sync-mcp-configs.sh` | Modify | I2 |
| `opencode/opencode.jsonc.template` | Modify | I1 |
| `ide/vscode/settings.json.template` | Modify | I3 |
| `mcp/docker-mcp-gateway.service` | Modify | I4 |
| `claude/claude-settings.json.template` | Modify | M1 |

---

### Task 1: [C2] `MCP_CONFIG_DIR` 未定義変数を修正

**Files:**
- Modify: `_scripts/setup-docker-mcp.sh:128`

**背景:** `setup-docker-mcp.sh` の旧コードで `MCP_CONFIG_DIR="$HOME/.docker/mcp"` を定義していたブロックが削除されたが、その変数を参照する行（128行目）が残っている。`set -euo pipefail` により未定義変数参照でスクリプトが即 abort する。

- [ ] **Step 1: 現状確認**

```bash
grep -n "MCP_CONFIG_DIR" /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected: `128:CATALOG_FILE="$MCP_CONFIG_DIR/catalogs/docker-mcp.yaml"` が出力される（定義行なし）

- [ ] **Step 2: `MCP_CONFIG_DIR` 定義を追加**

`_scripts/setup-docker-mcp.sh` の `# カタログの初期化...` コメント行の直前（127行目付近）に追加する:

```bash
# カタログの初期化（未初期化の場合のみ、docker-mcp.yaml を取得するため）
MCP_CONFIG_DIR="$HOME/.docker/mcp"
CATALOG_FILE="$MCP_CONFIG_DIR/catalogs/docker-mcp.yaml"
```

変更後の対象箇所:
```bash
# カタログの初期化（未初期化の場合のみ、docker-mcp.yaml を取得するため）
MCP_CONFIG_DIR="$HOME/.docker/mcp"
CATALOG_FILE="$MCP_CONFIG_DIR/catalogs/docker-mcp.yaml"
if [[ ! -f "$CATALOG_FILE" ]]; then
```

- [ ] **Step 3: 構文チェック**

```bash
bash -n /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected: 出力なし（エラーなし）

- [ ] **Step 4: shellcheck 実行**

```bash
shellcheck /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected: 出力なし（警告なし）。SC2034 (unused variable) の警告が出る場合は `# shellcheck disable=SC2034` を当該行の前に追加。

---

### Task 2: [C1] `setup-docker-mcp.sh` のサービスファイル二重書き込みを削除

**Files:**
- Modify: `_scripts/setup-docker-mcp.sh:147-150`

**背景:** `setup-docker-mcp.sh` は line 118 で `sync-mcp-configs.sh` を呼び出してサービスファイルを正しく生成する（`__REPO_ROOT__` と `__ENABLED_SERVERS__` の両方を置換）。しかしその後 line 147-150 で `__REPO_ROOT__` のみを置換した内容で同ファイルを上書きしてしまい、`__ENABLED_SERVERS__` がリテラルのまま systemd に渡される。

- [ ] **Step 1: 二重書き込みブロックを確認**

```bash
sed -n '145,155p' /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected:
```
echo -e "${BLUE}⚙️  Setting up systemd service...${NC}"
mkdir -p "$HOME/.config/systemd/user"
# Replace __REPO_ROOT__ placeholder with actual path
sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$REPO_ROOT/mcp/docker-mcp-gateway.service" > "$HOME/.config/systemd/user/docker-mcp-gateway.service"
systemctl --user daemon-reload
```

- [ ] **Step 2: `sed` による上書き行のみを削除**

`_scripts/setup-docker-mcp.sh` の該当ブロックを以下の通り変更する:

削除前:
```bash
echo -e "${BLUE}⚙️  Setting up systemd service...${NC}"
mkdir -p "$HOME/.config/systemd/user"
# Replace __REPO_ROOT__ placeholder with actual path
sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$REPO_ROOT/mcp/docker-mcp-gateway.service" > "$HOME/.config/systemd/user/docker-mcp-gateway.service"
systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service
echo -e "${GREEN}✅ systemd service enabled and started.${NC}"
```

変更後:
```bash
echo -e "${BLUE}⚙️  Setting up systemd service...${NC}"
# Service file is already written by sync-mcp-configs.sh (called above).
# Only reload and enable/restart here.
systemctl --user daemon-reload
systemctl --user enable docker-mcp-gateway.service
systemctl --user restart docker-mcp-gateway.service
echo -e "${GREEN}✅ systemd service enabled and started.${NC}"
```

- [ ] **Step 3: 構文チェック**

```bash
bash -n /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected: 出力なし

- [ ] **Step 4: shellcheck 実行**

```bash
shellcheck /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
```

Expected: 出力なし

- [ ] **Step 5: コミット（Task 1 と Task 2 を一括）**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add _scripts/setup-docker-mcp.sh
git commit -m "fix(setup-docker-mcp): MCP_CONFIG_DIR未定義とサービスファイル二重書き込みを修正"
```

---

### Task 3: [I1] `opencode.jsonc.template` 末尾の重複コンテンツを削除

**Files:**
- Modify: `opencode/opencode.jsonc.template:429-434`

**背景:** ファイル末尾に `}, // End Provider\n  },\n}` が2回繰り返されており、有効な JSONC として解析できない。

- [ ] **Step 1: 末尾を確認**

```bash
tail -10 /home/y_ohi/dotfiles/components/dotfiles-ai/opencode/opencode.jsonc.template
```

Expected:
```
    }, // End Provider
  },
}
        "port": 4937,
      },
    }, // End Provider
  },
}
```

- [ ] **Step 2: 重複行（430-434行目）を削除**

`opencode/opencode.jsonc.template` の最後の5行（`"port": 4937,` から末尾の `}` まで）を削除し、ファイルが以下で終わるようにする:

```jsonc
    }, // End Provider
  },
}
```

- [ ] **Step 3: 末尾の確認**

```bash
tail -5 /home/y_ohi/dotfiles/components/dotfiles-ai/opencode/opencode.jsonc.template
```

Expected:
```
    }, // End Provider
  },
}
```

（末尾に余分な行がないこと）

- [ ] **Step 4: コミット**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add opencode/opencode.jsonc.template
git commit -m "fix(opencode): テンプレート末尾の重複コンテンツを削除"
```

---

### Task 4: [I2] `sync-mcp-configs.sh` Python ヒアドキュメントの相対パスを修正

**Files:**
- Modify: `_scripts/sync-mcp-configs.sh:75-86`

**背景:** Python ヒアドキュメント内で `Path("mcp/config.yaml")` という相対パスを使用しているが、スクリプトを任意のディレクトリから実行した場合にファイルが見つからずエラーになる。`REPO_ROOT` は既に定義されているため、環境変数経由でパスを渡す。

- [ ] **Step 1: 対象箇所を確認**

```bash
sed -n '73,90p' /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/sync-mcp-configs.sh
```

Expected: `ENABLED_SERVERS=$(` から `PY` 終端まで、`Path("mcp/config.yaml")` が見える。

- [ ] **Step 2: 環境変数経由でパスを渡すよう修正**

変更前:
```bash
ENABLED_SERVERS=$(
    uv run --with-requirements "$REPO_ROOT/requirements.txt" python3 - <<'PY'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("mcp/config.yaml").read_text(encoding="utf-8")) or {}
```

変更後:
```bash
ENABLED_SERVERS=$(
    DOTFILES_AI_REPO_ROOT="$REPO_ROOT" uv run --with-requirements "$REPO_ROOT/requirements.txt" python3 - <<'PY'
from pathlib import Path
import os
import yaml

config = yaml.safe_load(Path(os.environ["DOTFILES_AI_REPO_ROOT"]).joinpath("mcp/config.yaml").read_text(encoding="utf-8")) or {}
```

- [ ] **Step 3: 構文チェック**

```bash
bash -n /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/sync-mcp-configs.sh
```

Expected: 出力なし

- [ ] **Step 4: shellcheck 実行**

```bash
shellcheck /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/sync-mcp-configs.sh
```

Expected: 出力なし

- [ ] **Step 5: コミット**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add _scripts/sync-mcp-configs.sh
git commit -m "fix(sync-mcp-configs): Python heredocの相対パスをREPO_ROOT経由に変更"
```

---

### Task 5: [I3] `ide/vscode/settings.json.template` の不正 JSON 構造を修正

**Files:**
- Modify: `ide/vscode/settings.json.template`

**背景:** ファイルが `{` で始まらず、トップレベルにキーが裸で存在し、末尾が `}}` になっている。VSCode が `settings.json` を読めない。また、`sync-mcp-configs.sh` が `__HOME__` を置換するため、ハードコードされたパスを `__HOME__` に置き換える。

- [ ] **Step 1: 現状確認**

```bash
cat /home/y_ohi/dotfiles/components/dotfiles-ai/ide/vscode/settings.json.template
```

Expected: `{` で始まらず `}}` で終わっている。

- [ ] **Step 2: 正しい JSON 構造に書き直す**

`ide/vscode/settings.json.template` を以下の内容に置き換える:

```json
{
  "mcpServers": {
    "docker-mcp-gateway": {
      "url": "http://127.0.0.1:10888/sse"
    },
    "chronos-graph": {
      "command": "uv",
      "args": [
        "--quiet",
        "tool",
        "run",
        "--from",
        "git+https://github.com/yohi/chronos-graph.git@37308f47837469d801abc1226ee65e4262093042",
        "context-store"
      ],
      "env": {
        "STORAGE_BACKEND": "sqlite",
        "SQLITE_DB_PATH": "__HOME__/.context-store/memories.db",
        "GRAPH_ENABLED": "true"
      }
    }
  }
}
```

- [ ] **Step 3: JSON 構文検証**

```bash
python3 -m json.tool /home/y_ohi/dotfiles/components/dotfiles-ai/ide/vscode/settings.json.template > /dev/null && echo "Valid JSON"
```

Expected: `Valid JSON`

- [ ] **Step 4: コミット**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add ide/vscode/settings.json.template
git commit -m "fix(vscode): settings.json.templateの不正なJSON構造を修正"
```

---

### Task 6: [I4] `docker-mcp-gateway.service` の ExecStart 内コメントを削除

**Files:**
- Modify: `mcp/docker-mcp-gateway.service:17`

**背景:** systemd の `ExecStart` 多行コマンド内に `#` コメントが含まれており、コマンド引数として渡されてしまう。Gateway 起動時にコマンド解析エラーが発生する。

- [ ] **Step 1: 現状確認**

```bash
cat /home/y_ohi/dotfiles/components/dotfiles-ai/mcp/docker-mcp-gateway.service
```

Expected: `ExecStart` ブロック内に `# chronos-graph is excluded...` 行が見える。

- [ ] **Step 2: コメント行を削除**

`mcp/docker-mcp-gateway.service` から `ExecStart` 内の `#` コメント行を削除し、代わりに `[Unit]` セクションの `Description` を更新してコメントの意図を保持する:

変更前:
```ini
[Unit]
Description=Docker MCP Gateway
After=network.target docker.service
```

変更後:
```ini
[Unit]
Description=Docker MCP Gateway (chronos-graph runs locally via uv on each client)
After=network.target docker.service
```

また、`ExecStart` ブロックから以下の行を削除する:

```
  # chronos-graph is excluded here because it runs locally via 'uv' on each client.
```

- [ ] **Step 3: systemd-analyze でサービスファイル検証（任意）**

```bash
systemd-analyze verify /home/y_ohi/dotfiles/components/dotfiles-ai/mcp/docker-mcp-gateway.service 2>&1 || true
```

Expected: プレースホルダー `__REPO_ROOT__` / `__ENABLED_SERVERS__` に関する警告のみが出る（コメント関連のエラーはない）。

- [ ] **Step 4: コミット**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add mcp/docker-mcp-gateway.service
git commit -m "fix(systemd): ExecStart内の不正な#コメントを削除"
```

---

### Task 7: [M1] テンプレートファイルのハードコードパスを `__HOME__` プレースホルダーに置換

**Files:**
- Modify: `claude/claude-settings.json.template:9,32`

**背景:** `claude/claude-settings.json.template` に `/home/y_ohi/` がハードコードされており、他環境への移植性がない。`sync-mcp-configs.sh` は既に `__HOME__` → `$HOME` の置換を行っているため、プレースホルダーに変更するだけでよい。

- [ ] **Step 1: ハードコードパスを確認**

```bash
grep -n "y_ohi" /home/y_ohi/dotfiles/components/dotfiles-ai/claude/claude-settings.json.template
```

Expected: `/home/y_ohi/` を含む行が表示される。

- [ ] **Step 2: `__HOME__` に置換**

`claude/claude-settings.json.template` の `/home/y_ohi` を `__HOME__` に一括置換する:

変更前:
```json
  "statusLine": {
    "type": "command",
    "command": "sh /home/y_ohi/.claude/statusline-command.sh"
  },
```

変更後:
```json
  "statusLine": {
    "type": "command",
    "command": "sh __HOME__/.claude/statusline-command.sh"
  },
```

また、`chronos-graph` の `SQLITE_DB_PATH` も同様:

変更前:
```json
        "SQLITE_DB_PATH": "/home/y_ohi/.context-store/memories.db",
```

変更後:
```json
        "SQLITE_DB_PATH": "__HOME__/.context-store/memories.db",
```

- [ ] **Step 3: 残りのハードコードパスがないか確認**

```bash
grep -n "y_ohi" /home/y_ohi/dotfiles/components/dotfiles-ai/claude/claude-settings.json.template
```

Expected: 出力なし

- [ ] **Step 4: JSON 構文検証**

```bash
python3 -m json.tool /home/y_ohi/dotfiles/components/dotfiles-ai/claude/claude-settings.json.template > /dev/null && echo "Valid JSON"
```

Expected: `Valid JSON`

（Note: `__HOME__` はプレースホルダーなので、純粋な JSON としては有効なはずである。）

- [ ] **Step 5: コミット**

```bash
cd /home/y_ohi/dotfiles/components/dotfiles-ai
git add claude/claude-settings.json.template
git commit -m "fix(claude): テンプレートのハードコードパスを__HOME__プレースホルダーに変更"
```

---

## 最終確認

- [ ] **全コミットを確認**

```bash
git log --oneline -7
```

Expected: 上記 Task のコミットメッセージが7件（Task 1+2 を合算で最大6件）表示される。

- [ ] **shellcheck を全スクリプトに実行**

```bash
shellcheck /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/setup-docker-mcp.sh
shellcheck /home/y_ohi/dotfiles/components/dotfiles-ai/_scripts/sync-mcp-configs.sh
```

Expected: 両方とも出力なし

- [ ] **テンプレート JSON 検証**

```bash
python3 -m json.tool /home/y_ohi/dotfiles/components/dotfiles-ai/ide/vscode/settings.json.template > /dev/null && echo "vscode: OK"
python3 -m json.tool /home/y_ohi/dotfiles/components/dotfiles-ai/claude/claude-settings.json.template > /dev/null && echo "claude: OK"
```

Expected: `vscode: OK` と `claude: OK`
