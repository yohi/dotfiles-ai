# Improvement Proposals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** GitHub ActionsによるCI/CD構築（Python Linter導入）、JSONCパース処理の標準ライブラリ化、およびMCP生成スクリプトの冪等性強化を行う。

**Architecture:** `bitbucket-pipelines.yml`を廃止し、`.github/workflows/`以下にCIを構築。既存の自作パーサーを`json5`に置き換え、生成スクリプト側でファイルのハッシュ比較等による冪等性を確保する。

**Tech Stack:** GitHub Actions, Python 3, ruff, mypy, json5

---

### Task 1: GitHub Actions CI/CDとLinterのセットアップ

**Files:**
- Modify: `requirements.txt`
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml` (Create)
- Delete: `bitbucket-pipelines.yml`

**Step 1: 新規依存関係の追加**

`requirements.txt` に以下の行を追加します。

```text
ruff>=0.3.0
mypy>=1.9.0
types-PyYAML
json5>=0.9.22
```

**Step 2: Makefile に lint ターゲットを追加**

`Makefile` を編集して末尾（あるいは `.PHONY` 指定周辺）に以下の内容を追加します。

```makefile
lint:
	@echo "==> Running Ruff and Mypy on scripts/"
	ruff check scripts/
	mypy scripts/
```

**Step 3: 古いCI設定の削除**

Run: `git rm bitbucket-pipelines.yml`
Expected: `rm 'bitbucket-pipelines.yml'` などの出力

**Step 4: GitHub Actions ワークフローの作成**

`mkdir -p .github/workflows` 

`.github/workflows/ci.yml` を作成して以下を記述します。

```yaml
name: CI

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

jobs:
  lint:
    runs-on: ubuntu-latest
    container: ubuntu-slim
    steps:
    - uses: actions/checkout@v4
    - name: Install uv and Python
      uses: astral-sh/setup-uv@v5
      with:
        enable-cache: true
    - name: Set up Python via uv
      run: uv python install 3.10
    - name: Install dependencies
      run: uv pip install --system -r requirements.txt
    - name: Run Linters
      run: make lint
```

**Step 5: ローカルテストの実行と修正（もしあれば）**

Run: `uv pip install -r requirements.txt`
Run: `make lint`
Expected: エラー・警告が出る可能性があります。問題があれば修正し、パスすることを確認します。

**Step 6: コミット**

```bash
git add requirements.txt Makefile .github/workflows/ci.yml
git commit -m "ci: migrate from bitbucket to GitHub Actions and configure ruff/mypy"
```

---

### Task 2: `render-mcp-configs.py` の `json5` 置き換え

**Files:**
- Modify: `scripts/render-mcp-configs.py`
- Modify: `scripts/test_render_configs.py` (Create)

**Step 1: テスト用スクリプトの作成 (TDD)**

`scripts/test_render_configs.py` を作成します。

```python
import json5

def test_json5_import():
    data = json5.loads('{ "key": "value", // comment\n }')
    assert data["key"] == "value"
    print("Test passed")

if __name__ == "__main__":
    test_json5_import()
```

**Step 2: テストの実行と確認**

Run: `python scripts/test_render_configs.py`
Expected: `Test passed` と出力されること

**Step 3: スクリプトの `parse_jsonc` 置き換え**

`scripts/render-mcp-configs.py` を開き、先頭部分の `import` に `import json5` を追加します。
自作の `parse_jsonc` 処理を以下に置き換えます。

```python
def parse_jsonc(text: str) -> dict[str, Any]:
    return json5.loads(text)
```

**Step 4: スクリプトの動作確認**

Run: `python scripts/render-mcp-configs.py`
Expected: エラー無く実行され、`rendered ...` 等が出力されること。

**Step 5: コミット**

```bash
git add scripts/render-mcp-configs.py scripts/test_render_configs.py
git commit -m "refactor: replace custom jsonc parser with json5 library"
```

---

### Task 3: 生成スクリプトの冪等性 (Idempotency) 強化

同じ設定内容の場合は一切のファイル書き込みや更新を行わないようにして、再起動やIDEの不要なリロードを回避します。

**Files:**
- Modify: `scripts/render-mcp-configs.py`

**Step 1: `write_json_file` へのロジック追加**

`scripts/render-mcp-configs.py` を開き、ファイルへ書き込む直前に差分チェックを追加します。

```python
def write_json_file(path: Path, root_key: str, servers: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        text = path.read_text(encoding="utf-8")
        data = parse_jsonc(text)
    
    data[root_key] = servers
    new_content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    
    # Check idempotency
    if path.exists() and path.read_text(encoding="utf-8") == new_content:
        return
        
    path.write_text(new_content, encoding="utf-8")
```

**Step 2: テスト実行（初回）**

Run: `python scripts/render-mcp-configs.py`

**Step 3: テスト実行（2回目）**

Run: `python scripts/render-mcp-configs.py`
Expected: 2回目は内容に差分がないためファイルの内容は更新されない。スクリプトが問題なく終了すること。

**Step 4: コミット**

```bash
git add scripts/render-mcp-configs.py
git commit -m "perf: ensure idempotency by skipping unchanged files"
```
