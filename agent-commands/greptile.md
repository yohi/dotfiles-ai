---
allowed-tools: run_shell_command
description: Autonomous PR completion loop using Greptile Skills
---

# Greptile Loop

Greptile Skillsを使用して、PRのレビュー指摘を自律的に解消し、完了（5/5スコア）まで自動修正を繰り返します。

## 目標
AIエージェントが自律的に「レビュー指摘の取得 → 修正案の作成 → コード適用 → コミット・プッシュ → 再検証」のサイクルを完結させます。

## 実行手順

### 1. 環境確認
Greptile MCPサーバーが設定されており、GitHub CLI (`gh`) の認証が完了しているか確認します。

```bash
gh auth status
# Greptile MCPのツールが利用可能か確認
# (例: mcp__greptile__query など)
```

### 2. ワークフロー実行
[Greptile Skills公式ドキュメント](https://www.greptile.com/docs/mcp-v2/skills#agent-skills)に基づき、以下のスキルを呼び出します。

**PRの総合チェックと修正:**
エージェントに対して以下を指示します：
「`/check-pr` スキルを実行して、CIの失敗やレビューコメントをすべて修正して」

**満点（5/5）までの反復修正:**
エージェントに対して以下を指示します：
「`/greploop` スキルを実行して、Greptileのスコアが満点になるまで修正を繰り返して」

### 3. 進捗の報告
各ループの結果（スコアの推移、修正した箇所、残っている指摘）を報告します。

## 成功基準
- Greptileのレビュー指摘がすべて解消されること
- レビュースコアが 5/5 に到達すること
- すべての修正がコミット・プッシュされ、CIが通過すること
