---
name: apm-optimization-ja
title: APM構成およびワークフローの最適化
date: 2026-06-06
status: approved
---

# APM構成およびワークフローの最適化設計書

## 1. 背景と目的
現在、`dotfiles-ai` リポジトリにおけるAIエージェント構成の管理は、APM（Agent Package Manager）と、従来のMakefileターゲットおよびカスタムシェルスクリプトの双方が混在する構成となっています。この二重管理により、外部スキルの重複したコピーが発生し、ビルドステップが複雑化し、異なるエージェント構成（Claude Code、Gemini、Cursor、OpenCode、Codex）間での設定の同期ずれが発生しやすい状態になっています。

本最適化の目的は、APMが持つ依存関係管理、ターゲット別コンパイル、およびビルドステップのオーケストレーション機能を最大限に活用することで、コードベースを簡素化し、高いポータビリティと再現性を確保することです。

## 2. アーキテクチャおよび詳細設計

### 2.1 スキル管理と同期フローの再設計
* **APM主導のデプロイ**:
  * `apm.yml` に記載された外部スキル（例：`obra/superpowers`、`anthropics/skills`）は、APMのインストール機能によってターゲットディレクトリ（`.agents/skills/` および各エージェントの実行ディレクトリ）へ直接配置されます。
  * `apm_modules/` から `agent-skills/` へ外部スキルを手動コピーするカスタムスクリプトおよびMakeターゲットは廃止します。
* **`agent-skills/` の役割の整理**:
  * [agent-skills/](file:///home/y_ohi/dotfiles/components/dotfiles-ai/agent-skills) ディレクトリは、ローカルのカスタムスキル（`agent-skills/custom/` 配下）のみを格納する場所とします。
  * 外部スキル用の一時フォルダ（`agent-skills/anthropics/`、`agent-skills/superpowers/`）はクリーンアップし、Git追跡およびローカルから除外します。
* **Skillport MCP の統合**:
  * `apm.yml` 内の `skillport` MCP設定において、`SKILLPORT_SKILLS_DIR` 環境変数を `agent-skills` から `${env:PWD}/.agents/skills` に変更します。
  * これにより、Skillport MCPは共通のデプロイ先から外部スキルとローカルカスタムスキルの双方をシームレスに走査・ロードできるようになります。

### 2.2 コンパイルとターゲット統合
* **APMターゲットコンパイルの活用**:
  * 各エージェント向けの設定ファイル生成には APM のターゲットコンパイル機能（`apm compile`）を使用します。
  * `apm.yml` 内にインストール後/コンパイル後フック（post-install / post-compile hooks）を定義し、Markdown形式のコマンドからGemini用 `.toml` ファイルやCodex用 `.md` ルールへの変換スクリプトを自動実行します。
* **Antigravity向けの回避策フック**:
  * 現状、AntigravityはAPMのコンパイルターゲットとして標準サポートされていないため、`apm.lock.yaml`（または `apm.yml`）から解決済みのMCP構成を解析し、Antigravity用の [antigravity/mcp_config.json](file:///home/y_ohi/dotfiles/components/dotfiles-ai/antigravity/mcp_config.json) を出力するカスタムスクリプト（`_scripts/sync_antigravity.sh`）を実装します。
  * このスクリプトは、Makefileラッパーを介して `apm compile` の実行直後に post-compile フックとして実行されます。
* **共通指示（Instructions）の結合**:
  * `apm.yml` の `instructions` および `exports.instructions` 設定に `global-rules/AGENTS.global.md` を指定し、APMが各エージェント用の設定ファイルをビルドする際に自動結合するようにします。これにより手動でのシンボリックリンク作成を不要にします。

### 2.3 Makefileの簡素化
* **不要ターゲットのクリーンアップ**:
  * [_mk/sync-agents.mk](file:///home/y_ohi/dotfiles/components/dotfiles-ai/_mk/sync-agents.mk) から `install-external-skills`、`sync-skills-to-agents`、`uninstall-superpowers` などの不要な同期・コピー処理を削除します。
* **エントリーポイントの統合**:
  * 開発者向けコマンドの互換性のために `make setup` および `make sync-agents` は維持しますが、その実体を `apm install && apm compile` を実行するシンプルなラッパーに変更します。
  * `clean-sync-artifacts` を調整し、二重管理時代に作成された不要なゴミファイルを自動で削除できるようにします。

## 3. 検証・テスト計画
* **インストール検証**:
  * `apm install` を実行し、`.agents/skills/` 配下に外部スキルおよびローカルスキルが正しく配置されることを確認します。
* **Skillport動作検証**:
  * `skillport list` を実行し、カスタムスキルと外部スキルの双方が正しくスキャンされ、リストに表示されることを検証します。
* **ターゲット構成ファイルの検証**:
  * Claude Code (`.claude/`)、Gemini (`gemini/`)、Cursor (`.cursor/rules/`)、OpenCode (`opencode/`) 向けの構成ファイルが正常にコンパイルされ、動作することを確認します。
  * `antigravity/mcp_config.json` が正しく生成され、対応するMCPサーバーの設定が反映されていることを確認します。
