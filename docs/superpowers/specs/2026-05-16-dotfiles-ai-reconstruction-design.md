# dotfiles-ai 再構築設計書

- **Date**: 2026-05-16
- **Status**: Draft (Pending Review)
- **Scope**: dotfiles-ai リポジトリ全体の構成整理（APM活用・Docker MCP Catalog連携・環境変数管理・スキル構成）

---

## 1. 概要

本設計書は、`dotfiles-ai` リポジトリの再構築に関する設計ドキュメントです。

以下の要素を再構築の対象とします：

1. **APMの活用**: AIエージェントの設定周りを APM による一元管理に統合
2. **Docker MCP Catalogの活用**: Docker MCP Hub にあるものは Gateway のカタログ標準機能で利用し、無いものだけを APM で管理
3. **環境変数の管理**: `apm-environment.md` を参考に、3層モデル（Tier 1/2/3）による構成の見直し
4. **エージェントスキル**: `agent-skills.md` を参考に APM と Skillport のハイブリッド構成

---

## 2. 現状分析

### 2.1 現状の `apm.yml`

```yaml
dependencies:
  apm:
    - obra/superpowers
    - anthropics/skills
  mcp:
    - name: skillport
      ...
    - name: nexus
      ...
    - name: SQLite          # Docker Catalog に存在
      ...
    - name: github-official   # Docker Catalog に存在
      ...
    - name: sequentialthinking  # Docker Catalog に存在
      ...
    - name: chronos-graph
      ...
```

### 2.2 現状の課題

- **APM の役割が曖昧**: Docker Catalog にある MCP まで `apm.yml` で個別定義しており、管理が分散している
- **環境変数が単層**: 秘匿情報・マシン依存設定・デフォルト値が区別されていない
- **スキルディレクトリの重複**: `agent-skills/` と各エージェント固有ディレクトリが並存

---

## 3. 設計方針

### 3.1 コアプリンシプル

> **"APM で環境を整え、Skillport で自律的に動く"**

### 3.2 3つの分離

| 分離軸 | 説明 |
| :--- | :--- |
| **管理 vs 実行** | APM（静的配備）と Skillport（動的ロード）を明確に分離 |
| **標準 vs カスタム** | Docker Catalog 標準とプロジェクト固有カスタムを明確に分離 |
| **秘匿 vs 設定** | 環境変数を Tier 1/2/3 の3層で階層化し、セキュリティと可搬性を両立 |

---

## 4. アーキテクチャ

### 4.1 システム構成図

```
dotfiles-ai (SSOT)
├── apm.yml .................. SSOT（外部スキル依存関係 + カスタムMCP）
├── agent-skills/
│   ├── .skillport/ .......... Skillport メタデータ
│   ├── custom/ .............. ローカルカスタムスキル
│   ├── superpowers/ ......... APM 配備（obra/superpowers）
│   └── anthropics/ .......... APM 配備（anthropics/skills）
├── .agents/
│   └── skills/ .............. クロスプラットフォーム標準配置先
├── .env ..................... Tier 2 環境変数（Git 除外）
├── .env.example ............. .env のテンプレート
└── mcp/
    ├── config.yaml .......... Docker Gateway 設定（カスタムMCPのみ）
    └── catalogs/
        └── custom.yaml ...... Docker Catalog 追加定義

Docker MCP Gateway (localhost:10888)
├── [Docker Catalog Standard]  github, SQLite, sequentialthinking...
└── [Custom via APM]           skillport, nexus, chronos-graph...
    ↑
    SSE (http://127.0.0.1:10888/sse)
    ↓
AI Agents (Claude, Gemini, OpenCode, Cursor, VSCode, Codex, Antigravity)
```

### 4.2 各コンポーネントの役割整理

| コンポーネント | 役割 | 変更内容 |
| :--- | :--- | :--- |
| **apm.yml** | 唯一の正解 (SSOT) | Docker Catalog 標準MCP定義を削除。外部スキル + カスタムMCPのみ管理 |
| **.agents/skills/** | クロスプラットフォーム標準 | 新設。全エージェントが参照する統合スキルディレクトリ |
| **Skillport MCP** | スキルの窓口 | `.agents/skills/` を参照先に変更 |
| **.env.example** | 環境変数テンプレート | 新設。Tier 1/2 の変数を明示 |
| **Docker Gateway** | SSE 集約 | Catalog 標準MCPは Docker 側で有効化。Gateway は SSE 集約に集中 |

---

## 5. 詳細設計

### 5.1 `apm.yml` の再設計

```yaml
name: dotfiles-ai
version: 2.0.0
description: AI Agent settings, skills, and unified MCP configuration for dotfiles

dependencies:
  apm:
    - obra/superpowers
    - anthropics/skills

  mcp:
    # --- Custom MCP Servers (Docker Catalog にないもの) ---
    - name: skillport
      title: "Skillport"
      registry: false
      transport: stdio
      command: "uvx"
      args: ["skillport-mcp"]
      env:
        SKILLPORT_SKILLS_DIR: "${env:PWD}/.agents/skills"
      standalone: true

    - name: nexus
      title: "Nexus"
      registry: false
      transport: stdio
      command: "npx"
      args: ["-y", "@yohi/nexus@1.7.0"]
      env:
        NEXUS_STORAGE_ROOT_DIR: "${env:HOME}/.nexus"
        NO_PROXY: "127.0.0.1,localhost"
      standalone: true

    - name: chronos-graph
      title: "Chronos Graph"
      registry: false
      transport: stdio
      command: "uv"
      args:
        - "run"
        - "--quiet"
        - "--from"
        - "git+https://github.com/yohi/chronos-graph.git"
        - "context-store"
      env:
        # Tier 2: .env ファイルに記述
        POSTGRES_HOST: "${env:CHRONOS_POSTGRES_HOST}"
        POSTGRES_PASSWORD: "${env:CHRONOS_POSTGRES_PASSWORD}"
        NEO4J_URI: "${env:CHRONOS_NEO4J_URI}"
        NEO4J_PASSWORD: "${env:CHRONOS_NEO4J_PASSWORD}"
        REDIS_URL: "${env:CHRONOS_REDIS_URL}"

        # Tier 3: デフォルト値を直接記述
        POSTGRES_PORT: "5432"
        POSTGRES_DB: "postgres"
        POSTGRES_USER: "postgres"
        POSTGRES_SSL: "true"
        GRAPH_ENABLED: "true"
        NEO4J_USER: "3af8423f"
        CACHE_BACKEND: "redis"
        REDIS_SSL: "true"
        DECAY_HALF_LIFE_DAYS: "30"
        SIMILARITY_THRESHOLD: "0.70"
        DEDUP_THRESHOLD: "0.90"
        EMBEDDING_PROVIDER: "local-model"
        LOCAL_MODEL_NAME: "cl-nagoya/ruri-v3-310m"
        EMBEDDING_DIMENSION: "768"
      standalone: true

targets:
  default: [opencode, gemini, claude, cursor, vscode, antigravity, codex]

exports:
  skills:
    - agent-skills/**
  instructions:
    - global-rules/AGENTS.global.md
```

### 5.2 `.env.example` の新設

```bash
# ==============================================================================
# dotfiles-ai Environment Variables
# ==============================================================================
# このファイルは .env のテンプレートです。
# コピーして .env にリネームし、各項目を環境に合わせて設定してください。
# .env は絶対に Git にコミットしないでください。
# ==============================================================================

# --- Tier 1: API Keys & Secrets ---
# これらは OS の環境変数またはキーチェーンから継承されるべきです。
# 必要に応じてここに設定してください。
# ANTHROPIC_API_KEY=your_key_here
# GITHUB_TOKEN=your_token_here
# MCP_GATEWAY_TOKEN=your_token_here

# --- Tier 2: Environment-specific Settings ---
# マシンや環境に依存する設定（非秘匿）
# CHRONOS_POSTGRES_HOST=db.cojzbcmvvqlivowmjeza.supabase.co
# CHRONOS_NEO4J_URI=neo4j+s://3af8423f.databases.neo4j.io
# CHRONOS_NEO4J_PASSWORD=your_password
# CHRONOS_REDIS_URL=rediss://default:your_password@organic-crow-100989.upstash.io:6379

# --- Tier 3: Defaults (通常は変更不要) ---
# これらは apm.yml にデフォルト値が記述されています。
# 上書きが必要な場合のみ設定してください。
# CHRONOS_POSTGRES_PORT=5432
# CHRONOS_SIMILARITY_THRESHOLD=0.70
```

### 5.3 環境変数の3層モデル詳細

#### Tier 1: OS / シェル環境（最優先）

| 変数名 | 用途 | 例 |
| :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | Claude系エージェントの認証 | `sk-ant-...` |
| `GITHUB_TOKEN` | GitHub API アクセス | `ghp_...` |
| `MCP_GATEWAY_TOKEN` | Gateway アクセス制御 | ランダム文字列 |

#### Tier 2: プロジェクト `.env`

| 変数名 | 用途 | 例 |
| :--- | :--- | :--- |
| `CHRONOS_POSTGRES_HOST` | DBホスト | `db.cojzbcmvvqlivowmjeza.supabase.co` |
| `CHRONOS_NEO4J_URI` | Neo4j接続先 | `neo4j+s://...` |
| `CHRONOS_REDIS_URL` | Redis接続先 | `rediss://...` |

#### Tier 3: `apm.yml` 内直接定義（デフォルト値）

| 変数名 | デフォルト値 | 用途 |
| :--- | :--- | :--- |
| `POSTGRES_PORT` | `5432` | DBポート |
| `SIMILARITY_THRESHOLD` | `0.70` | 類似度閾値 |
| `DECAY_HALF_LIFE_DAYS` | `30` | 半減期（日） |
| `EMBEDDING_DIMENSION` | `768` | 埋め込み次元数 |

### 5.4 スキル管理構成

#### ディレクトリ構造

```
agent-skills/
├── .skillport/ ........... Skillport 設定・メタデータ
├── custom/ ............... プロジェクト固有スキル
│   ├── agent-skill-architect/
│   ├── config-modernizer/
│   ├── doc-sync-verifier/
│   ├── dotfiles-guidelines/
│   ├── git-master/
│   ├── makefile-organization/
│   └── ...
├── superpowers/ .......... APM 配備（obra/superpowers）
│   ├── brainstorming/
│   ├── executing-plans/
│   ├── receiving-code-review/
│   ├── requesting-code-review/
│   ├── systematic-debugging/
│   ├── test-driven-development/
│   ├── using-git-worktrees/
│   ├── verification-before-completion/
│   ├── webapp-testing/
│   ├── writing-plans/
│   └── ...
└── anthropics/ ........... APM 配備（anthropics/skills）
    ├── algorithmic-art/
    ├── brand-guidelines/
    ├── canvas-design/
    ├── claude-api/
    ├── doc-coauthoring/
    ├── docx/
    ├── frontend-design/
    ├── internal-comms/
    ├── mcp-builder/
    ├── pdf/
    ├── pptx/
    ├── theme-factory/
    ├── web-artifacts-builder/
    ├── xlsx/
    └── ...
```

#### 集合成品（`.agents/skills/`）

```
.agents/skills/ ........... APM 標準クロスプラットフォーム配置先
├── agent-skill-architect -> ../agent-skills/custom/agent-skill-architect
├── config-modernizer -> ../agent-skills/custom/config-modernizer
├── doc-sync-verifier -> ../agent-skills/custom/doc-sync-verifier
├── dotfiles-guidelines -> ../agent-skills/custom/dotfiles-guidelines
├── git-master -> ../agent-skills/custom/git-master
├── makefile-organization -> ../agent-skills/custom/makefile-organization
├── anthropics/
│   ├── algorithmic-art -> ../../agent-skills/anthropics/algorithmic-art
│   ├── brand-guidelines -> ../../agent-skills/anthropics/brand-guidelines
│   └── ...
└── superpowers/
    ├── brainstorming -> ../../agent-skills/superpowers/brainstorming
    ├── executing-plans -> ../../agent-skills/superpowers/executing-plans
    └── ...
```

### 5.5 Docker MCP Catalog 連携方針

#### 管理対象の分離

| MCP名 | 管理先 | 理由 |
| :--- | :--- | :--- |
| `github-official` | Docker Catalog | Docker 標準カタログに存在 |
| `sqlite` | Docker Catalog | Docker 標準カタログに存在 |
| `sequentialthinking` | Docker Catalog | Docker 標準カタログに存在 |
| `skillport` | `apm.yml` | Docker Catalog に**不在** |
| `nexus` | `apm.yml` | Docker Catalog に**不在** |
| `chronos-graph` | `apm.yml` | Docker Catalog に**不在** |

#### Gateway 設定

Docker Catalog 標準の MCP は Docker Desktop / Docker CLI で有効化し、Gateway は `mcp/config.yaml` で自動検出・統合します。

`mcp/catalogs/custom.yaml` には、**カスタムMCPの参照情報**のみを記述します。

---

## 6. ワークフロー変更

### 6.1 変更・追加される Make ターゲット

| ターゲット | 内容 | 追加/変更 |
| :--- | :--- | :--- |
| `make setup-apm-env` | `.env.example` から `.env` を作成（初回のみ） | **追加** |
| `make sync-agents` | `agent-skills/` → `.agents/skills/` へ集約リンク | **変更** |
| `make apm-install` | `apm install` + post_install hooks 実行 | **追加** |
| `make sync-mcp` | カスタムMCP設定再生成 + Gateway 再読み込み | **変更** |

### 6.2 セットアップフロー

```
make setup
│
├─ apm install --target agent-skills ............ 外部スキル配備
│  └─ post_install:
│     ├─ make sync-agents ....................... .agents/skills/ 集約
│     ├─ make sync-mcp .......................... Gateway 設定再生成
│     └─ make setup-apm-env ..................... .env 雛形作成（初回）
│
└─ make setup-docker-mcp ......................... Gateway 起動
```

### 6.3 スキル追加フロー

```
# 外部スキルを追加する場合
1. apm.yml dependencies.apm に追加
2. make apm-install

# カスタムスキルを追加する場合
1. agent-skills/custom/<skill-name>/SKILL.md を作成
2. make sync-agents（自動で .agents/skills/ にリンク）
```

---

## 7. 変更対象ファイル一覧

| ファイル | 変更内容 | 理由 |
| :--- | :--- | :--- |
| `apm.yml` | Docker Catalog MCP 定義を削除。環境変数を Tier モデル化 | SSOT の役割を絞る |
| `.env.example` (新規) | Tier 1/2 変数のテンプレート作成 | 環境変数管理の標準化 |
| `.gitignore` | `.env` を追加 | 秘匿情報保護 |
| `.agents/skills/` (新規) | クロスプラットフォーム標準スキル配置先 | APM の `.agents/skills/` 標準に準拠 |
| `mcp/config.yaml` | カスタムMCPのみ定義 | Docker Catalog と役割分離 |
| `mcp/catalogs/custom.yaml` | カスタムMCP参照情報のみ | Docker Catalog 標準とは別管理 |
| `_mk/setup.mk` | `make setup-apm-env` 追加 | 環境変数初期化 |
| `_mk/sync-agents.mk` | `.agents/skills/` への集約処理に更新 | 標準ディレクトリ対応 |
| `_mk/mcp.mk` | `make sync-mcp` をカスタムMCP専用に変更 | Docker Catalog 連携 |
| `_mk/main.mk` | `make apm-install` 追加 | 標準インストールフロー |
| `AGENTS.md` | SkillPort ブロックを更新 | `.agents/skills/` 参照に変更 |
| `README.md` | 構成変更に伴う説明更新 | ドキュメント整合性 |

---

## 8. リスクと対策

| リスク | 影響 | 対策 |
| :--- | :--- | :--- |
| `.agents/skills/` への移行によるエージェント参照パス変更 | 高 | `make sync-agents` で自動集約。AGENTS.md に新パスを明記 |
| Docker Catalog MCP の環境変数が異なる | 中 | `apm.yml` から削除する際、必要な env var を `.env.example` に移行 |
| chronos-graph の Tier 2 変数未設定による起動失敗 | 中 | `apm install` 時に `.env` の存在チェックと警告を実装 |
| APM post_install フックの整合性 | 低 | Makefile の依存関係を明確にし、`make setup` で一括実行 |

---

## 9. マイルストーン

| Phase | タスク | 見積時間 |
| :--- | :--- | :--- |
| Phase 1 | `apm.yml` 再設計・`.env.example` 作成 | 1h |
| Phase 2 | `.agents/skills/` 構成と `make sync-agents` 更新 | 1h |
| Phase 3 | `make sync-mcp` のカスタムMCP専用化 | 1h |
| Phase 4 | Makefile・ワークフロー更新 | 1h |
| Phase 5 | ドキュメント更新（AGENTS.md, README.md） | 1h |
| Phase 6 | 検証動作・テスト | 2h |
| **合計** | | **〜7h** |

---

## 10. Self-Review Checklist

- [x] 構成図は最新のリポジトリ構造と一致しているか → Yes
- [x] セキュリティ上の懸念（秘匿情報の露出）はないか → `.env` は `.gitignore`、Tier3 はデフォルト値のみ
- [x] 既存の `agent-skills/` と `.agents/skills/` の違いは明確か → Yes（前者: 実体、後者: 標準配置先）
- [x] Docker Catalog にない MCP が `apm.yml` から誤って削除されていないか → Yes（skillport, nexus, chronos-graph を確認）
- [x] 絶対パスがコミットされていないか → `${env:PWD}` / `${env:HOME}` を使用

---

*本設計書は `superpowers/brainstorming` スキルに基づき作成されました。*
