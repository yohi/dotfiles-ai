# 🤖 OpenCode Configuration & Pattern Switcher

OpenCode エージェントの動作設定と、モデル割り当てパターンを管理するためのディレクトリです。
コストや用途に合わせて、使用する AI モデルの組み合わせ（パターン）を簡単に切り替えることができます。

## 📂 ディレクトリ構成

```text
opencode/
├── commands/                  # カスタムスラッシュコマンド
│   ├── build-skill.md         # エージェントスキルの対話的設計・生成
│   ├── git-pr-flow.md         # ブランチ作成→コミット→PR作成の統合フロー
│   └── setup-gh-actions-test-ci.md  # GitHub Actions CI自動生成
├── docs/                      # エージェント向けドキュメント
│   ├── global/                # グローバルルール（シンボリックリンク経由で参照）
│   │   ├── DOCS_STYLE.md      # ドキュメントスタイルガイド
│   │   └── GIT_STANDARDS.md   # Git操作の標準ルール
│   └── rules/                 # ユニバーサルコーディング標準
│       └── MARKDOWN.md        # Markdownガイドライン
├── patterns/                  # モデル割り当てパターンの定義ファイル群
│   ├── default.jsonc          # デフォルト設定（パターン2と同一）
│   ├── pattern-1.jsonc        # 最強構成（Best-of-Breed）
│   ├── pattern-2.jsonc        # Claude節約構成
│   ├── pattern-3.jsonc        # Claudeなし（GPT+Gemini）
│   ├── pattern-4.jsonc        # GPTなし（Claude+Gemini）
│   └── pattern-5.jsonc        # Gemini主体（Claude最小）
├── skills/                    # エージェントスキル定義
│   ├── agent-skill-architect/ # スキル設計官
│   └── config-modernizer.md   # 設定ファイル現代化スキル
├── AGENTS.global.md           # エージェント向けグローバル指示（英語）
├── oh-my-opencode.base.jsonc  # 設定ファイルのベーステンプレート
├── oh-my-opencode.jsonc       # [自動生成] 実行用設定ファイル（git管理外）
├── opencode.jsonc             # OpenCode本体の設定（プラグイン・権限・MCP等）
└── switch-opencode-pattern.sh # パターン切り替え用スクリプト
```

## 🔄 パターンの切り替え

`switch-opencode-pattern.sh` スクリプトを使用して、エージェント構成を対話的に切り替えることができます。

### 実行方法

```bash
./opencode/switch-opencode-pattern.sh
```

### 操作フロー

1. コマンドを実行すると、利用可能なパターンの一覧が表示されます。
2. 適用したいパターンの番号を入力します。
3. `oh-my-opencode.jsonc` が選択したパターンで上書き更新されます。

## 📊 利用可能なパターン一覧

| パターン | ファイル | 説明 | Sisyphus(指揮) | Hephaestus(職人) | Oracle(相談) |
|---------|---------|------|:---:|:---:|:---:|
| **1: 最強構成** | `pattern-1.jsonc` | GPT+Claude+Gemini Best-of-Breed | Opus Thinking | Codex | Opus Thinking |
| **2: Claude節約** | `pattern-2.jsonc` | Sisyphus=Gemini, Oracle=Opus | Gemini Pro | Codex | Opus Thinking |
| **3: Claudeなし** | `pattern-3.jsonc` | GPT+Geminiのみ | GPT-5.3 | Codex | GPT-5.2 |
| **4: GPTなし** | `pattern-4.jsonc` | Claude+Geminiのみ | Opus Thinking | ─ | Opus Thinking |
| **5: Gemini主体** | `pattern-5.jsonc` | コスト最優先、Claude最小 | Gemini Pro | ─ | Gemini Pro |
| **default** | `default.jsonc` | デフォルト（パターン2と同一） | Gemini Pro | Codex | Opus Thinking |

> **注意**: パターン4・5では Hephaestus（GPT Codex）が使用不可のため、深い実装タスクの性能が低下する場合があります。

## 📝 新しいパターンの作成

### 現在の設定を保存する場合

1. `oh-my-opencode.jsonc` を直接編集して好みの設定にします。
2. スクリプトを実行し、「現在の設定を保存」を選択します。
3. 名前と説明を入力すると、`patterns/` ディレクトリに新しい `.jsonc` ファイルが保存されます。

### 手動で作成する場合

1. `patterns/` ディレクトリ内に新しい `.jsonc` ファイルを作成します（例: `my-custom.jsonc`）。
2. 以下の形式で `agents` と `categories` を定義します。

```jsonc
{
  "description": "パターンの説明",
  "agents": {
    "sisyphus": { "model": "google/antigravity-gemini-3-pro" },
    "hephaestus": { "model": "openai/gpt-5.3-codex" },
    "oracle": { "model": "google/antigravity-claude-opus-4-6-thinking" },
    "momus": { "model": "openai/gpt-5.2" },
    "librarian": { "model": "google/antigravity-gemini-3-pro" },
    "explore": { "model": "google/antigravity-gemini-3-flash" },
    "multimodal-looker": { "model": "google/antigravity-gemini-3-flash" }
  },
  "categories": {
    "quick": { "model": "google/antigravity-gemini-3-flash" },
    "writing": { "model": "google/antigravity-gemini-3-flash" },
    "visual-engineering": { "model": "google/antigravity-gemini-3-pro" },
    "artistry": { "model": "google/antigravity-gemini-3-pro", "variant": "max" },
    "ultrabrain": { "model": "openai/gpt-5.3-codex", "variant": "xhigh" },
    "deep": { "model": "openai/gpt-5.3-codex", "variant": "medium" },
    "unspecified-low": { "model": "openai/gpt-5.2" },
    "unspecified-high": { "model": "google/antigravity-claude-opus-4-6-thinking", "variant": "max" }
  }
}
```

## ⚙️ 仕組み

このシステムは、ベース設定（`oh-my-opencode.base.jsonc`）の特定の領域（マーカー間）に、パターンファイル（`patterns/*.jsonc`）の内容を注入することで機能します。

### ベース設定 (`oh-my-opencode.base.jsonc`)

共通のプラグイン設定、権限設定、MCP設定、各種機能設定が記述されています。

主要な設定項目:

- **Tmux連携**: エージェントの思考プロセスを別ペインで可視化
- **ブラウザ自動化**: Playwright MCP
- **バックグラウンドタスク**: 並列数制御（デフォルト5並列）
- **Ralph Loop**: 自律改善ループ（最大20回）
- **Boulder State**: タスク中断時の進捗保存・再開
- **Session Recovery**: クラッシュ時の会話状態復元
- **Rules Injector**: `.cursorrules` や `CONTEXT.md` の自動注入

`// @pattern:start` と `// @pattern:end` マーカーの間にパターンの agents/categories が注入されます。

### 生成される設定 (`oh-my-opencode.jsonc`)

OpenCode はこのファイルを参照して動作します。

> **注意**: このファイルを直接編集しても、次回パターン切り替え時に上書きされます。恒久的な変更はベース設定かパターンファイルを編集してください。

### OpenCode本体設定 (`opencode.jsonc`)

OpenCode 自体の基本設定ファイルです。以下を管理しています:

- **プラグイン**: `oh-my-opencode`, `opencode-antigravity-auth`, `omo-sdd-hybrid` 等
- **権限**: ファイル読み書き、Bash実行、MCP操作の許可設定
- **MCP サーバー**: Context7, Serena, Playwright, AWS, Terraform, 21st.dev, Tavily 等

## 🤖 エージェントロール

| エージェント | 役割 | 推奨モデル |
|:---:|------|------|
| **Sisyphus** | 指揮官 — タスク分解・委任・全体統括 | Opus Thinking / Gemini Pro |
| **Hephaestus** | 職人 — 深い実装・コーディング | GPT-5.3 Codex |
| **Oracle** | 相談役 — アーキテクチャ・デバッグ助言（読み取り専用） | Opus Thinking / GPT-5.2 |
| **Momus** | 品質保証 — コードレビュー・計画レビュー | GPT-5.2 / Sonnet 4.5 |
| **Metis** | 参謀 — 計画立案・要件定義・AI失敗回避 | Opus Thinking / GPT-5.2 |
| **Librarian** | 書庫番 — 外部ドキュメント・OSS検索 | Gemini Pro |
| **Explore** | 探索 — コードベースの高速把握 | Gemini Flash |
| **Multimodal Looker** | 視覚 — 画像・PDF認識 | Gemini Flash |
| **Git Specialist** | Git職人 — 安全なGit操作 | GPT-5.3 / Gemini Pro |

## 📋 カスタムコマンド

`commands/` ディレクトリにカスタムスラッシュコマンドを定義できます。

| コマンド | ファイル | 説明 |
|---------|---------|------|
| `build-skill` | `build-skill.md` | エージェントスキル（SKILL.md）を対話的に設計・生成 |
| `git-pr-flow` | `git-pr-flow.md` | ブランチ作成/選択→関連ファイルコミット→PR作成の統合フロー |
| `setup-gh-actions-test-ci` | `setup-gh-actions-test-ci.md` | リポジトリの言語・フレームワークを自動検出し GitHub Actions CI を生成 |

## 📚 ドキュメント

`docs/` ディレクトリにはエージェントが参照するルールファイルが格納されています。

- **`docs/rules/MARKDOWN.md`** — Markdownのフォーマットルール（`markdownlint-cli2` 準拠）
- **`docs/global/DOCS_STYLE.md`** — ドキュメントスタイルガイド
- **`docs/global/GIT_STANDARDS.md`** — Git操作の標準ルール

> `AGENTS.global.md` は LLM の理解精度を最大化するため英語で記述されています。
