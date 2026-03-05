# CodeRabbit CLI カスタムスラッシュコマンド集

このディレクトリには、[CodeRabbit CLI](https://docs.coderabbit.ai/cli/overview)を活用した高度なAIコードレビューを実行するためのCursor カスタムスラッシュコマンド（`.md`形式）が含まれています。

## 🔧 前提条件

### CodeRabbit CLI のインストール
```bash
curl -fsSL https://cli.coderabbit.ai/install.sh | sh
```

### 認証設定
```bash
coderabbit auth login
# または短縮エイリアス
cr auth login
```

### 動作環境
- **対応OS**: macOS (Intel/Apple Silicon), Linux
- **未対応**: Windows
- **要件**: Git リポジトリ内で実行

## 📋 利用可能なコマンド

### 🎯 `/coderabbit-review` - 包括的AIコードレビュー
**用途**: プロジェクト全体の徹底的なコードレビューと品質分析

**実行される CodeRabbit CLI コマンド**:
- `coderabbit --prompt-only` (AI統合最適化)
- `coderabbit --plain` (詳細フィードバック)
- `coderabbit --base master --prompt-only` (ベース比較)

**特徴**:
- 全ファイルの包括的分析
- セキュリティ、パフォーマンス、保守性の多角的評価
- 優先度付きの改善提案

---

### ⚡ `/quick-cr-review` - 高速差分レビュー
**用途**: 変更されたファイルのみを対象とした高速レビュー

**実行される CodeRabbit CLI コマンド**:
- `coderabbit --type uncommitted --prompt-only` (未コミット変更)
- `coderabbit --type all --plain` (詳細確認)
- `coderabbit --base master --type uncommitted --prompt-only` (差分レビュー)

**特徴**:
- Git差分ベースの効率的スキャン
- 3分以内の高速実行
- 即座に実装可能な具体的修正案

**最適なタイミング**:
- コミット前の最終チェック
- PR作成前の品質確認
- デイリー開発サイクルでの継続的レビュー

---

### 🛡️ `/security-cr-audit` - セキュリティ監査
**用途**: セキュリティ脆弱性に特化した監査レビュー

**実行される CodeRabbit CLI コマンド**:
- `coderabbit --prompt-only` (AI統合最適化)
- `coderabbit --plain --type all` (詳細分析)
- `coderabbit --type uncommitted --prompt-only` (変更チェック)

**特徴**:
- セキュリティ脆弱性の専門的検出
- 脅威レベル分類とCVSS評価
- 即時対応アクションプラン

---

### 🚀 `/performance-cr-review` - パフォーマンス最適化
**用途**: パフォーマンス問題の特定と最適化提案

**実行される CodeRabbit CLI コマンド**:
- `coderabbit --prompt-only` (AI統合最適化)
- `coderabbit --plain --type all` (詳細分析)
- `coderabbit --base master --prompt-only` (差分チェック)

**特徴**:
- 定量的メトリクスによる性能分析
- ボトルネック特定とアルゴリズム効率分析
- ROI分析による改善優先度付け

## 🚀 CodeRabbit CLI 統合の特徴

### 1. `--prompt-only` モード
[Claude Code統合](https://docs.coderabbit.ai/cli/claude-code-integration)に最適化されたモード：
- **トークン効率的**: AIエージェント用に最適化された出力
- **簡潔なコンテキスト**: 問題の場所、説明、修正提案を含む
- **自動統合**: Cursorとの seamless な連携

### 2. レビュータイプ指定
```bash
--type all         # コミット済み + 未コミット (デフォルト)
--type committed   # コミット済み変更のみ
--type uncommitted # 未コミット変更のみ
```

### 3. ベースブランチ指定
```bash
--base master   # masterブランチとの比較
--base develop  # developブランチとの比較
--base master   # masterブランチとの比較
```

## 📊 使用パターン推奨

### 日常開発サイクル
```text
1. 機能開発中: /quick-cr-review (未コミット変更チェック)
2. 開発完了後: /coderabbit-review (包括的品質チェック)
3. PR作成前: /security-cr-audit (セキュリティ確認)
4. パフォーマンス問題時: /performance-cr-review (最適化)
```

### チーム開発プロセス
```text
1. 個人開発: /quick-cr-review (毎日)
2. フィーチャー完成: /coderabbit-review (週次)
3. セキュリティレビュー: /security-cr-audit (リリース前)
4. 最適化検討: /performance-cr-review (月次)
```

## ⚡ 高度な機能

### Autonomous AI Development
[CodeRabbit + Claude Code統合](https://docs.coderabbit.ai/cli/claude-code-integration)により：
- **専門的問題検出**: レースコンディション、メモリリーク等
- **AI自動修正**: CodeRabbitの分析に基づくClaude Codeの修正
- **継続的ワークフロー**: 問題検出→修正→検証の自動サイクル

### 設定ファイル連携
CodeRabbitは自動的に以下のファイルを読み取り：
- `claude.md` - コーディング標準とアーキテクチャ設定
- `.cursorrules` - Cursor固有のルール
- カスタム設定ファイル (`--config` オプション)

### 料金体系と機能
- **無料版**: 基本的な静的解析、制限付き利用
- **有料版**: 学習機能、高度な問題検出、コンテキスト分析

## 🔧 トラブルシューティング

### CodeRabbitが問題を検出しない場合
1. **認証確認**: `coderabbit auth status`
2. **Git状態確認**: `git status`
3. **レビュータイプ指定**: `--type uncommitted`
4. **ベースブランチ指定**: `--base develop`

### レビュー時間が長い場合
- **範囲限定**: `--type uncommitted` で未コミット変更のみ
- **小さなブランチ**: 機能を小分けして開発
- **バックグラウンド実行**: Claude Codeでバックグラウンド実行

## 📈 期待される効果

基づく公式データ：
- **問題検出精度**: 従来のリンターが見逃す問題を検出
- **開発効率**: 専門的なレビューとAI修正の組み合わせ
- **品質向上**: レースコンディション、メモリリーク等の早期発見

## 📞 サポート・リソース

- **公式ドキュメント**: <https://docs.coderabbit.ai/cli/overview>
- **Claude Code統合ガイド**: <https://docs.coderabbit.ai/cli/claude-code-integration>
- **Discord**: CodeRabbit公式コミュニティ
- **Enterprise**: <mailto:sales@coderabbit.ai>

---

*これらのコマンドは[CodeRabbit CLI公式ドキュメント](https://docs.coderabbit.ai/cli/overview)に基づいて設計され、Claude Code統合とCursorでの使用に最適化されています。*
