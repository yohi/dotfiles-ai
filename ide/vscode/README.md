# VSCode設定

このディレクトリには、VSCodeの設定と拡張機能の管理に関するファイルが含まれています。

## ディレクトリ構成

```
vscode/
├── settings/                  # SuperCopilot Framework
│   ├── supercopilot.js        # 基本設定・データ定義
│   ├── persona-selector.js    # ペルソナ選択ロジック
│   ├── commands-handler.js    # コマンド処理ロジック
│   ├── supercopilot-main.js   # メインシステム・統合
│   └── README.md              # SuperCopilot Framework のREADME
├── copilot-instructions/      # GitHub Copilot指示ファイル
│   ├── commands.md            # コマンド定義
│   ├── personas.md            # ペルソナ定義
│   ├── rules.md               # 基本ルール
│   └── integration.md         # 統合方法の説明
├── keybindings.json           # キーボードショートカット設定
├── settings.json              # VSCode設定
├── extensions.list            # インストール済み拡張機能リスト
├── setup-supercopilot.sh      # SuperCopilot Framework セットアップスクリプト
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
ln -sf $(pwd)/vscode/settings.json ~/.config/Code/User/settings.json
ln -sf $(pwd)/vscode/keybindings.json ~/.config/Code/User/keybindings.json
```

または、ポータブルな設定として `~/.vscode` を使用している特別な理由がある場合（例えばエディタの起動スクリプトで独自の `--user-data-dir` を指定している場合）は、以下のようにします：

```bash
mkdir -p ~/.vscode
ln -sf $(pwd)/vscode/settings.json ~/.vscode/settings.json
ln -sf $(pwd)/vscode/keybindings.json ~/.vscode/keybindings.json
```

### 拡張機能のインストール

`extensions.list`に記載されている拡張機能をインストールするには：

```bash
cat ~/dotfiles/vscode/extensions.list | xargs -L 1 code --install-extension
```

### SuperCopilot Frameworkのセットアップ

SuperCopilot Frameworkを設定するには、セットアップスクリプトを実行します：

```bash
~/dotfiles/vscode/setup-supercopilot.sh
```

これにより、以下が行われます：

1. `~/.vscode/supercopilot`ディレクトリへのシンボリックリンク作成
2. VSCode設定の確認と必要な設定の案内
3. 使用方法の表示

## 特徴

### キーバインディング

`keybindings.json`には、効率的な作業のためのキーボードショートカットが定義されています。

### SuperCopilot Framework

GitHub Copilotを拡張し、以下の機能を提供します：

1. **ペルソナ自動選択**
   - ファイルタイプと質問内容から最適なペルソナを自動選択
   - 明示的なペルソナ指定も可能（例: `@architect`）

2. **コマンドシステム**
   - 質問中にコマンドを含めるだけで専門的な回答を得られる
   - 例: `implement 新しいログイン機能を追加したい`

詳細は `settings/README.md` を参照してください。

## 注意事項

- VSCodeのバージョンによっては一部機能が動作しない場合があります
- GitHub Copilotの利用には別途サブスクリプションが必要です
