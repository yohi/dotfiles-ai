# SuperCopilot Framework

VSCode向けGitHub Copilot拡張フレームワーク

## 概要

SuperCopilot Frameworkは、GitHub Copilotの機能を拡張し、より専門的で文脈に合わせた支援を提供するためのフレームワークです。
特にペルソナの自動選択機能を中心に、コマンド処理システムを統合しています。

## 主な機能

1. **ペルソナ自動選択システム**
   - ファイルタイプ、質問内容から最適なペルソナを自動選択
   - 明示的なペルソナ指定もサポート（@ペルソナ名）
   - バリアント対応（例: @developer (Frontend)）

2. **コマンドシステム**
   - 分析系、開発系、設計系などのカテゴリ別コマンド
   - 質問内容にコマンドを含めるだけで専門家が回答
   - コマンドに応じた最適なペルソナ自動選択

3. **VSCode統合**
   - GitHub Copilotチャットと統合
   - 設定ファイル経由の簡単セットアップ
   - シンボリックリンクによる導入

## ファイル構成

```
vscode/settings/
├── supercopilot.js       # 基本設定・データ定義
├── persona-selector.js   # ペルソナ選択ロジック
├── commands-handler.js   # コマンド処理ロジック
├── supercopilot-main.js  # メインシステム・統合
└── README.md             # このファイル
```

## セットアップ方法

1. **シンボリックリンクの作成**

```bash
# ホームディレクトリの.vscodeフォルダを作成（存在しない場合）
mkdir -p ~/.vscode

# リポジトリルートから以下のコマンドを実行し、シンボリックリンクを作成
ln -sf $(pwd)/vscode/settings ~/.vscode/supercopilot
```

1. **VSCodeの設定に追加**

`settings.json`ファイルに以下の設定を追加します：

```json
{
  "github.copilot.advanced": {
    "preProcessors": {
      "chat": {
        "path": "~/.vscode/supercopilot/supercopilot-main.js",
        "function": "preprocessCopilotPrompt"
      }
    }
  }
}
```

## 利用可能なペルソナ

- **@architect** - システムアーキテクト
- **@developer** - 実装開発者
  - **@developer (Frontend)** - フロントエンド開発者
  - **@developer (Backend)** - バックエンド開発者
- **@tester** - テストエンジニア
- **@devops** - DevOpsエンジニア
- **@analyst** - コードアナリスト

## コマンド一覧

### 分析系コマンド

- **analyze**: コード分析、問題特定、改善提案
- **explain**: コードの動作説明、アルゴリズム解説
- **troubleshoot**: バグ解析、エラー原因特定、解決策提示

### 開発系コマンド

- **implement**: 機能実装、新規開発
- **improve**: リファクタリング、最適化
- **build**: ビルド、コンパイル、パッケージング

### 設計系コマンド

- **design**: アーキテクチャ設計、システム設計
- **estimate**: 作業工数見積もり、スケジュール算出

### 管理系コマンド

- **task**: タスク分解、作業計画
- **workflow**: ワークフロー設計、プロセス改善
- **document**: ドキュメント生成、仕様書作成

### ツール系コマンド

- **test**: テスト作成、テスト実行計画
- **git**: Git操作、ブランチ戦略
- **cleanup**: コード整理、不要ファイル削除
- **load**: プロジェクト構造分析、依存関係把握
- **index**: コードベース索引化、関連性分析

## 使用例

```
# ペルソナ自動選択（ファイルタイプと質問内容から判断）
このコードのパフォーマンスを改善するには？

# 明示的なペルソナ指定
@architect マイクロサービスへの分割方法について教えて

# コマンド使用
implement ユーザー登録機能を追加したい
```

## カスタマイズ

`supercopilot.js`ファイルを編集することで、ペルソナやコマンドの設定をカスタマイズできます：

- ペルソナの追加・変更
- 新しいコマンドの定義
- キーワードパターンの調整
- デフォルトの動作変更

## 注意事項

- この機能はVSCode拡張ではなく、既存のCopilotと統合するシステムです
- Copilotの利用には正規のサブスクリプションが必要です
- VSCodeのバージョンによっては機能しない場合があります
