---
description: リポジトリの言語・フレームワークを自動検出し GitHub Actions CI を生成 (Delegated)
---

# Setup GitHub Actions Test CI

このファイルはコマンドの参照プレースホルダーです。
実体のコマンド定義は `../../agent-commands/setup-gh-actions-test-ci.md` にあります。
OpenCode (`opencode/commands/setup-gh-actions-test-ci.md`) と同じ参照パターンを利用して、主要リソースを共有します。

## 参照メカニズムの動作仕様

- **相対パスの解釈ルール**: 本ファイルからの一番近い実体ファイルへの相対パスとして解釈されます。
- **優先順位**: `agent-commands/` 配下のマスタファイルが常に優先されます。ローカルに独自の変更を加えたい場合は、マスタファイルを書き換えてください。
- **フォールバック動作**: リンク先の実体ファイルが存在しない場合、このコマンドは利用不可（無視またはエラー）となります。

## 解決の例

- 参照先文字列: `../../agent-commands/setup-gh-actions-test-ci.md`
- 期待される解決結果: `{リポジトリルート}/agent-commands/setup-gh-actions-test-ci.md` が読み込まれ、コマンドとして実行されます。
