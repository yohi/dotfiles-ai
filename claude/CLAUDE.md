# CLAUDE.md - ユーザー設定ファイル

このファイルは、Claudeとのやりとりにおける基本的な設定とルールを定義します。

## 基本設定

### 言語設定

- **使用言語**: 日本語
- すべてのやりとりは日本語で行います
- コードコメントも可能な限り日本語で記述します

### 開発環境設定

#### CI/CDツール

- **標準ツール**: Bitbucket Pipelines
- 特別な指示がない限り、CI/CD関連の設定はBitbucket Pipelinesを前提とします
- パイプライン設定ファイル: `bitbucket-pipelines.yml`

## 重要なルールと制限事項

### Git操作に関する制限

⚠️ **重要**: 以下のGit操作は原則として禁止されています

- `git commit`
- `git push`
- その他のリモートリポジトリへの変更操作

#### 例外条件

Git操作が許可される場合：

- ユーザーから**明確に指示があった場合のみ**
- 指示内容が具体的で、操作対象が明確な場合

#### 推奨される代替アプローチ

Git操作の代わりに以下を提案します：

- コード変更内容の提示
- 変更差分の表示
- 手動でのコピー&ペースト用コード提供
- ファイル作成・更新の手順説明

## コミュニケーションガイドライン

### 回答スタイル

- 丁寧語での対応
- 技術的な内容も分かりやすく説明
- 必要に応じて具体例を提示

### 確認事項

重要な操作を行う前に以下を確認します：

- 操作内容の妥当性
- ユーザーの意図との整合性
- セキュリティリスクの有無

## 開発関連の追加設定

### コード品質

- 読みやすく保守性の高いコードを心がけます
- 適切なコメントを日本語で記述します
- エラーハンドリングを適切に実装します

### ドキュメント

- README.mdは日本語で作成します
- API仕様書も日本語での説明を含めます
- コードの変更履歴は分かりやすく記録します

# ===================================================

# SuperClaude Framework Components

# ===================================================

# Behavioral Modes

@MODE_Brainstorming.md
@MODE_Business_Panel.md
@MODE_Introspection.md
@MODE_Orchestration.md
@MODE_Task_Management.md
@MODE_Token_Efficiency.md

# MCP Documentation

@MCP_Context7.md
@MCP_Magic.md
@MCP_Morphllm.md
@MCP_Playwright.md
@MCP_Sequential.md
@MCP_Serena.md

# Core Framework

@BUSINESS_PANEL_EXAMPLES.md
@BUSINESS_SYMBOLS.md
@FLAGS.md
@PRINCIPLES.md
@RULES.md
