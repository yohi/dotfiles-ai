# SuperCopilot Framework - VSCodeへの統合方法

## 概要

SuperCopilot Frameworkを使って、VSCodeでのGitHub Copilotエクスペリエンスを拡張します。
特にペルソナの自動選択機能、コマンド処理機能を統合することで、より専門的な支援を受けることができます。

## セットアップ方法

### 1. シンボリックリンクの作成

SuperCopilot Frameworkのファイルは、VSCodeの設定ディレクトリからシンボリックリンクで参照する必要があります。

```bash
# ホームディレクトリの.vscodeフォルダを作成（存在しない場合）
mkdir -p "$HOME/.vscode"

# 環境変数などを利用してリポジトリルートを指定し、シンボリックリンクを作成
# 実行前にリポジトリルートを設定してください (例: export REPO_ROOT="$(pwd)")
ln -sf "$REPO_ROOT/vscode/settings" "$HOME/.vscode/supercopilot"
```

### 2. Copilot設定の編集

VSCodeのCopilotに関する設定を編集します。`path` の `<user_home>` はご自身の環境に合わせて置き換えてください（Linux: `/home/<user>`, macOS: `/Users/<user>`）。

```json
{
  "github.copilot.advanced": {
    "preProcessors": {
      "chat": {
        "path": "<user_home>/.vscode/supercopilot/supercopilot-main.js",
        "function": "preprocessCopilotPrompt"
      }
    }
  }
}
```

## 使い方

### ペルソナの使用方法

SuperCopilot Frameworkは、以下の方法でペルソナを選択します：

1. **自動選択**: ファイルタイプと質問内容から最適なペルソナを自動選択
2. **明示的指定**: 質問に `@ペルソナ名` を含める（例: `@architect このシステムの設計について教えて`）
3. **コマンド使用**: コマンドキーワードを使用（例: `design システムアーキテクチャ`）

### 利用可能なペルソナ

- **@architect** - システムアーキテクト
- **@developer** - 実装開発者（Frontend/Backendのバリアント有り）
- **@tester** - テストエンジニア
- **@devops** - DevOpsエンジニア
- **@analyst** - コードアナリスト

### コマンドの使用方法

質問中にコマンドキーワードを含めるだけで、そのコマンドに対応する専門家が回答します。

#### 分析系コマンド

- **analyze**: コード分析、問題特定、改善提案
- **explain**: コードの動作説明、アルゴリズム解説
- **troubleshoot**: バグ解析、エラー原因特定、解決策提示

#### 開発系コマンド

- **implement**: 機能実装、新規開発
- **improve**: リファクタリング、最適化
- **build**: ビルド、コンパイル、パッケージング

#### 設計系コマンド

- **design**: アーキテクチャ設計、システム設計
- **estimate**: 作業工数見積もり、スケジュール算出

#### 管理系コマンド

- **task**: タスク分解、作業計画
- **workflow**: ワークフロー設計、プロセス改善
- **document**: ドキュメント生成、仕様書作成

#### ツール系コマンド

- **test**: テスト作成、テスト実行計画
- **git**: Git操作、ブランチ戦略
- **cleanup**: コード整理、不要ファイル削除
- **load**: プロジェクト構造分析、依存関係把握
- **index**: コードベース索引化、関連性分析

## インストールスクリプト

dotfilesリポジトリのインストールスクリプトに以下の処理を追加することをお勧めします：

```bash
#!/bin/bash

# SuperCopilot Frameworkのインストール
install_supercopilot() {
  echo "SuperCopilot Frameworkをセットアップしています..."

  # .vscodeディレクトリが存在しない場合は作成
  mkdir -p "$HOME/.vscode"

  # スクリプトのディレクトリからリポジトリルートを計算してシンボリックリンクを作成
  # 前提: このスクリプトは <リポジトリのルート>/vscode ディレクトリ直下に配置されている必要があります
  local SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local REPO_ROOT="$(dirname "$SCRIPT_DIR")"
  ln -sf "$REPO_ROOT/vscode/settings" "$HOME/.vscode/supercopilot"

  echo "SuperCopilot Frameworkのセットアップが完了しました"
  echo "VSCodeのsettings.jsonに設定を追加してください"
}

# インストール関数を実行
install_supercopilot
```

## 注意事項

- この機能はVSCode拡張ではなく、既存のCopilotと統合するシステムです
- Copilotの利用には正規のサブスクリプションが必要です
- VSCodeのバージョンによっては機能しない場合があります
