# OpenCode (oh-my-openagent) 設定ガイド

このディレクトリには、AIエージェントハーネス `oh-my-openagent`（通称 `oh-my-opencode`）を最大限に活用するための設定ファイルが格納されています。

## 1. 構成ファイル

### `opencode.jsonc`
OpenCode プラットフォーム自体のコア設定ファイルです。

### `oh-my-openagent.jsonc`
エージェントの知能構成、役割定義、ツール権限などを管理するメイン設定ファイルです。

## 2. 使い方

以前のようなテンプレートやプロファイル切り替えスクリプト（`omo-profiles.sh`）は廃止されました。
設定を変更する場合は、上記の `.jsonc` ファイルを直接編集してください。

これらのファイルは Git で追跡されているため、変更履歴を管理できます。

## 3. エージェントの役割 (11 Specialists)

Sisyphus（監督）は、あなたの指示を分析し、以下の専門家たちに最適な「知能カテゴリー」を割り当ててタスクを実行させます。

- **監督系**: Sisyphus, Prometheus (計画), Metis (レビュー), Momus (監査)
- **実装系**: Hephaestus (職人), Sisyphus-Junior (作業員)
- **調査系**: Oracle (賢者), Librarian (司書), Explore (探検), Atlas (地図)
- **視覚系**: Multimodal-Looker (目)

---
*Updated: 2026-05-01*
