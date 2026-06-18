---
allowed-tools: run_shell_command
description: AI-powered code review using CodeRabbit CLI
---

# CodeRabbit Review

CodeRabbit CLIを使用してプロジェクトのコードレビューと品質分析を実行します。

## 目標
高品質なAIコードレビューを実行し、開発者が即座に活用できる具体的な改善案を提供します。

## 実行手順

### 1. 環境確認
CodeRabbit CLIがインストールされており、認証が完了しているか確認します。

```bash
coderabbit --version
coderabbit auth status
```

もしインストールされていない場合は、以下のコマンドでインストールを案内してください。
`curl -fsSL https://cli.coderabbit.ai/install.sh | sh`

### 2. レビュー実行
[CodeRabbit CLI公式ドキュメント](https://docs.coderabbit.ai/cli/overview)に基づき、以下のコマンドを状況に応じて実行します。

**包括的レビュー:**
```bash
coderabbit review --agent
```

**未コミット変更のみ:**
```bash
coderabbit review --agent -t uncommitted
```

**特定のブランチとの比較:**
```bash
coderabbit review --agent --base main
```

### 3. 結果の整理
CodeRabbit CLIの出力を以下のカテゴリで整理して報告します：
- 🔴 **Critical**: セキュリティ脆弱性、致命的なバグ
- 🟡 **Warning**: パフォーマンス、保守性、一般的なバグ
- 🟢 **Info**: コードスタイル、ドキュメント、軽微な改善案

## 成功基準
- CodeRabbit CLIが正常に実行されること
- 具体的な改善提案（ファイル名、行番号、修正案）が提示されること
- 指摘事項に基づき、エージェントが必要な修正案を提示できること
