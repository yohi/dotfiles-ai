# VSCode設定

このディレクトリには、VSCodeの設定と拡張機能の管理に関するファイルが含まれています。

## ディレクトリ構成

```text
ide/vscode/
├── keybindings.json           # キーボードショートカット設定
├── settings.json              # VSCode設定
├── extensions.list            # インストール済み拡張機能リスト
└── README.md                  # このファイル
```

## セットアップ方法

### 基本設定のシンボリックリンク

以下のコマンドを実行して、VSCodeの設定とキーバインドのシンボリックリンクを作成します。
なお、VSCodeの標準的なユーザー設定フォルダはOSによって異なります：

- macOS: `~/Library/Application Support/Code/User`
- Linux: `~/.config/Code/User`
- Windows: `%APPDATA%\Code\User`

システム標準の場所にリンクを作成する場合は、以下のコマンドをOSに合わせて実行してください（例はLinuxの場合）：

```bash
# OS標準のUserディレクトリを作成（存在しない場合）
mkdir -p ~/.config/Code/User

# 設定ファイルのシンボリックリンクを作成（リポジトリルートで実行）
ln -sf $(pwd)/ide/vscode/settings.json ~/.config/Code/User/settings.json
ln -sf $(pwd)/ide/vscode/keybindings.json ~/.config/Code/User/keybindings.json
```

### 拡張機能のインストール

`extensions.list`に記載されている拡張機能をインストールするには：

```bash
cat ~/dotfiles/ide/vscode/extensions.list | xargs -L 1 code --install-extension
```

## MCP 設定

- VSCode の `mcpServers` は `mcp/servers.yaml` を SSOT として管理します。
- 変更を反映するにはリポジトリルートで `make sync-mcp` を実行してください。
- このコマンドで `ide/vscode/settings.json` の MCP セクションが再生成されます。

## 注意事項

- VSCodeのバージョンによっては一部機能が動作しない場合があります
- GitHub Copilotの利用には別途サブスクリプションが必要です
