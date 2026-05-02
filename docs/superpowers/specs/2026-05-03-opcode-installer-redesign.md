# Spec: Opcode Latest Version Installer

## 1. 概要
`_mk/claude.mk` における Opcode (Claude Code GUI) のインストール方式を、ソースビルドから公式リリースの `.deb` パッケージを利用した方式に刷新する。
GitHub API を用いて最新バージョンを動的に取得し、インストールの高速化とメンテナンス性の向上を実現する。

## 2. 目的・背景
- **現状**: `git clone` して `bun run tauri build` を実行するため、Rust/Bun 環境の構築が必要であり、インストールに 10〜15 分かかる。
- **課題**: リリース版 (v0.2.0) が公開されたため、ビルド不要で信頼性の高いバイナリを利用可能。
- **解決策**: `.deb` パッケージを直接インストールすることで、環境構築コストを削減し、インストール時間を数十秒に短縮する。

## 3. 設計詳細

### 3.1 バージョン検出ロジック
- GitHub API (`https://api.github.com/repos/winfunc/opcode/releases/latest`) を使用して `tag_name` を取得。
- `vX.Y.Z` 形式から `v` を除去した数値部分を抽出。
- 抽出したバージョンを `OPCODE_LATEST` 変数として保持。

### 3.2 インストールプロセス
1.  **既存バージョン確認**: `/opt/opcode/opcode --version` (または相当) を実行し、現在インストールされているバージョンと最新バージョンを比較。一致する場合はインストールをスキップ。
2.  **ダウンロード**: `curl` を用いて指定バージョンの `.deb` ファイルを `mktemp` で作成した一時ディレクトリに取得。
    - URL例: `https://github.com/winfunc/opcode/releases/download/v$(VERSION)/opcode_$(VERSION)_amd64.deb`
3.  **パッケージインストール**: `sudo apt install -y <temp_path>.deb` を実行。これによりランタイム依存関係 (webkit2gtk等) も自動解決される。
4.  **デスクトップエントリ更新**: 既存の `opcode.desktop` 作成ロジックを実行し、GUI メニューからの起動を確保。
5.  **クリーンアップ**: 一時ファイルを削除。

### 3.3 Makefile の変更箇所
- **`_mk/variables.mk`**:
    - `OPCODE_COMMIT` 等のビルド用変数を廃止。
    - バージョン取得用のヘルパーコマンドを追加。
- **`_mk/claude.mk`**:
    - `install-packages-opcode`: 依存関係のチェック (rustc, bun 等) を大幅に削減。ダウンロード & インストールフローに書き換え。
    - `update-opcode`: 最新版がある場合に更新するターゲットを新設 (オプション)。

## 4. 成功基準
- `make install-packages-opcode` が数分以内 (通信速度に依存) に完了すること。
- インストール完了後、アプリケーションメニューから Opcode が起動できること。
- `opcode --version` で最新バージョンが表示されること。

## 5. 考慮事項
- **非Debian環境**: `apt` が存在しない環境では、エラーメッセージを表示して AppImage 方式などを検討するよう促す（当面は Debian/Ubuntu を主対象とする）。
- **APIレート制限**: 頻繁な実行による GitHub API のレート制限を考慮し、失敗時のフォールバック (固定バージョン等) を検討。
- **アーキテクチャ**: `amd64` (x86_64) をデフォルトとする。ARM などの場合は、別途ダウンロード URL を調整するロジックが必要だが、本件では amd64 を優先する。
