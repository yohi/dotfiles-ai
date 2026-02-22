---
description: リポジトリの言語・フレームワークを自動検出し、適切なテスト・Lintを実行する GitHub Actions ワークフローを作成する
agent: sisyphus
model: google/antigravity-gemini-3-flash
---

あなたは熟練した CI/CD エンジニアです。
ユーザーのリポジトリを分析し、最適な GitHub Actions の CI ワークフロー (`.github/workflows/test.yml`) を構築してください。

## ゴール
Pull Request や master への Push 時に、プロジェクトのテストとLintを自動実行するワークフローを作成すること。

## 実行フロー

### Step 1: プロジェクト解析
まず、リポジトリの構成ファイルを調査し、使用されている言語とフレームワークを特定します。

1. **言語・フレームワークの特定**:
   - `package.json` -> Node.js / TypeScript / JavaScript
   - `go.mod` -> Go
   - `Cargo.toml` -> Rust
   - `requirements.txt`, `pyproject.toml`, `Pipfile` -> Python
   - `pom.xml`, `build.gradle` -> Java / Kotlin
   - `Gemfile` -> Ruby
   - `composer.json` -> PHP
   - `Makefile` -> Make ベース (C/C++ や汎用プロジェクト)

2. **テストコマンドの特定**:
   - Node.js: `npm test`, `yarn test`, `pnpm test` (`package.json` の `scripts` を確認)
   - Go: `go test ./...`
   - Rust: `cargo test`
   - Python: `pytest`, `python -m unittest`
   - その他: `make test` など

3. **Lintコマンドの特定（可能であれば）**:
   - `eslint`, `prettier`, `golangci-lint`, `clippy`, `black`, `flake8`, `rubocop` などの設定有無を確認。

### Step 2: ワークフローの提案と作成
解析結果に基づき、`.github/workflows/test.yml` の内容を作成します。

**基本方針:**
- **実行環境**: コスト効率を最大化するため、**1 vCPU Linux ランナー (`ubuntu-slim`)** を使用します。
  - **参考**: [1 vCPU Linux runner now available](https://github.blog/changelog/2025-10-28-1-vcpu-linux-runner-now-available-in-github-actions-in-public-preview/)
  - **注意**: `ubuntu-latest` (通常 2-4 vCPU) の間違いではありません。軽量なテスト・Lintタスクに適しています。
- **依存パッケージ**: ランナーが最小構成(`slim`)の場合、`git`, `curl` 等が含まれていない可能性があるため、必要に応じてインストールステップを追加します。

**基本構成テンプレート（Node.jsの例）:**
```yaml
name: Test CI

on:
  push:
    branches: [ "master" ]
  pull_request:
    branches: [ "master" ]

jobs:
  test:
    runs-on: ubuntu-slim # 1 vCPU runner (Not ubuntu-latest)
    steps:
    - name: Install prerequisites
      run: |
        if ! command -v git &> /dev/null; then
          sudo apt-get update && sudo apt-get install -y git curl ca-certificates gnupg
        fi
    - uses: actions/checkout@v4
    - name: Setup Node.js
      uses: actions/setup-node@v4
      with:
        node-version: '20'
        cache: 'npm'
    - name: Install dependencies
      run: npm ci
    - name: Run lint
      if: ${{ hashFiles('eslint.config.js', '.eslintrc*') != '' }}
      run: npm run lint --if-present
    - name: Run tests
      run: npm test
```

**要件:**
- **ファイルパス**: `.github/workflows/test.yml` (既に存在する場合は確認してから上書きまたは別名作成)
- **トリガー**: `push` (master) および `pull_request` (master)
- **ランナー**: `runs-on: ubuntu-slim` を指定すること。
- **キャッシュ**: 言語ごとの setup アクションのキャッシュ機能を有効化すること。

### Step 3: ファイルの書き込み
作成したYAMLファイルをリポジトリに保存します。

1. `.github/workflows` ディレクトリが存在しない場合は作成します。
2. `test.yml` を書き込みます。

### Step 4: 完了報告
作成したワークフローの内容と、実行されるタイミングをユーザーに報告してください。
もし解析不能な場合や、テストコマンドが見つからない場合は、汎用的な構成（チェックアウトのみなど）またはユーザーへのヒアリングを行ってください。
