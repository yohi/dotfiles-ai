# OpenCode (oh-my-opencode) 使用ガイド

🚀 OpenCode (oh-my-opencode) のセットアップが完了しました！

## 📦 使用方法:
ターミナルから `opencode` コマンドを実行します。

## 📋 利用可能なコマンド例:
- `opencode -p 1`                - 特定のパターン (1-5) を選択して実行
- `opencode -s`                  - 各種設定の同期
- `opencode -v`                  - バージョン確認

## 🔧 oh-my-opencode 特有の機能:
- `omo-profiles`                  - プロファイルの切り替え
- `omo-status`                    - 全コンポーネントの状態確認
- `omo-sync`                      - 設定の同期

## 📂 設定ファイル:
- **設定**: `~/.config/opencode/opencode.jsonc`
- **oh-my-config**: `~/.config/opencode/oh-my-opencode.jsonc`
- **AGENTS**: `~/.config/opencode/AGENTS.md`
- **docs**: `~/.config/opencode/docs`

## 🩺 トラブルシューティング
設定に不備があると感じた場合は、ターミナルで以下を実行してください。
```bash
make doctor
```

## 📚 詳細情報
プロジェクトルートの `opencode/README.md` を参照してください。
