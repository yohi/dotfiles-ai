# Quick CodeRabbit Review - 高速差分レビュー

変更されたファイルのみを対象とした高速CodeRabbitレビューを実行します。効率性と実用性を最優先とし、開発者が即座に対応できる具体的な改善案を提供します。

## 目標
Git差分に基づく変更ファイルのみを対象として、3分以内で実用的なレビュー結果を提供する。

## 実行戦略

### 段階1: 環境とコンテキストの確認
以下を同時実行：
- `git status --porcelain` で変更ファイル特定
- `git diff --name-only` で差分ファイル取得
- CodeRabbit CLI利用可能性確認

### 段階2: 差分フォーカスレビュー（高速モード）
[CodeRabbit CLI公式ドキュメント](https://docs.coderabbit.ai/cli/overview)に基づき、変更ファイルに対して以下のコマンドを実行：

```bash
# 未コミット変更の高速レビュー（AI統合最適化）
coderabbit --type uncommitted --prompt-only

# 全変更の詳細レビュー（確認用）
coderabbit --type all --plain

# ベースブランチとの差分レビュー
coderabbit --base main --type uncommitted --prompt-only
```

### 段階3: 実装優先度付きレポート生成
以下の形式で即座に実装可能なレポートを出力：

```text
⚡ 高速CodeRabbitレビュー結果
実行時間: {duration}秒
対象ファイル: {changed_files}

🚨 即時対応必須（セキュリティ・バグ）
[{file}:{line}] {critical_issue_summary}
💡 修正案: {concrete_fix}

⚠️ 重要改善（パフォーマンス・品質）
[{file}:{line}] {major_issue_summary}
🔧 改善案: {improvement_suggestion}

📋 軽微改善（スタイル・慣習）
[{file}:{line}] {minor_issue_summary}
✨ 提案: {style_suggestion}

📊 変更サマリー
- 追加行数: {lines_added}
- 削除行数: {lines_deleted}
- 品質スコア: {quality_score}/100
- 推奨次アクション: {next_action}
```

## 高速化技術要件

### パフォーマンス最適化
- 変更ファイルのみにスコープ限定（`--type uncommitted`）
- AI統合最適化（`--prompt-only`）使用
- エラー処理による継続性確保

### 実用性重視の出力
- ファイル・行番号の正確な特定
- コピー&ペースト可能な修正コード
- 優先度に基づく実装順序の提示

### エラー処理
- CodeRabbit CLI未インストール時の代替案提示
- ネットワークエラー時のローカル分析
- 部分的失敗時の有用な結果提供

## 成功指標

- 実行時間 < 3分
- 変更コードの95%以上をカバー
- 実装可能な具体的提案を3つ以上提供
- 開発者が即座に次の行動を取れる情報を含む

## 開発者エクスペリエンス

### 即時フィードバック
- プログレスインジケーター表示
- 段階的結果の表示
- エラー時の明確な対処法提示

### 最適なタイミング
- コミット前の最終チェック
- PR作成前の品質確認
- デイリー開発サイクルでの継続的レビュー
