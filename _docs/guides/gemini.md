# Gemini CLI 使用ガイド

Gemini CLI は、Google の Gemini モデルをコマンドラインから利用するためのツールです。

## 🚀 使用方法:
1. Gemini CLI を起動: `gemini`
2. 対話を開始するか、カスタムコマンドを使用します。

## 📋 カスタムコマンド (User Tools):
本リポジトリでは、Gemini CLI を強化するカスタムコマンドを提供しています。
Gemini CLI 内で以下のコマンドを入力することで利用可能です。

- `/build-skill` - 新しいスキルの雛形を作成
- `/git-pr-flow` - Git のプルリクエスト作成フローを実行
- `/setup-gh-actions-test-ci` - GitHub Actions のテスト CI をセットアップ

## 🎭 ペルソナの使用:
Gemini CLI では、特定の役割（ペルソナ）を演じさせることができます。
例: `@codebase_investigator プロジェクトの構造を教えて`

## 🩺 トラブルシューティング
設定に不備があると感じた場合は、ターミナルで以下を実行してください。
```bash
make check-gemini
```
