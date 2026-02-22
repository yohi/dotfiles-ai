# Makefile Organization Reference

本ドキュメントは、Makefile の保守・拡張に関する詳細な技術仕様とパターンをまとめたものです。

## 1. ファイル分類と責任範囲

| カテゴリ | 対象ファイル (mk/*.mk) | 責任範囲 |
| :--- | :--- | :--- |
| **Core** | `variables.mk`, `idempotency.mk`, `help.mk`, `presets.mk` | 定数定義、冪等性マクロ、ヘルプ表示、共通設定。 |
| **Infrastructure** | `bitwarden.mk`, `system.mk`, `docker.mk` | OS 設定、パッケージマネージャ、秘密情報管理、コンテナ基盤。 |
| **Functional** | `install.mk`, `setup.mk`, `fonts.mk`, `mozc.mk`, `zsh.mk` | 個別アプリケーションのインストールと設定。 |
| **AI & Tools** | `cursor.mk`, `claude.mk`, `gemini.mk`, `opencode.mk` | AI アシスタント関連ツール、開発支援ツールの管理。 |
| **Meta** | `main.mk`, `stages.mk`, `menu.mk`, `shortcuts.mk`, `deprecated-targets.mk` | 統合ターゲット（`setup-all` 等）、UI/メニュー、非推奨管理。 |
| **Testing** | `test.mk` | ユニットテスト、統合テスト、モック環境の定義。 |

## 2. PHONY ターゲット管理
- 全てのターゲットは原則として `.PHONY` に登録する。
- 登録場所は `mk/variables.mk` の末尾に集約し、重複を防ぐ。
- ターゲット名が `setup-` や `install-` で始まる場合、対応する `check-` や `clean-` ターゲットの提供を検討する。

## 3. エラーハンドリングのパターン
シェルスクリプトのベストプラクティスを Makefile 内で再現する：

```makefile
target:
	@echo "🔍 Checking condition..."
	@if [ ! -d "/path/to/dir" ]; then 
		echo "❌ Error: Directory not found."; 
		exit 1; 
	fi
	@command -v some-cmd >/dev/null 2>&1 || { echo "❌ some-cmd is required"; exit 1; }
```

## 4. 冪等性・バージョンチェックマクロ (`idempotency.mk`)

| マクロ名 | 用途 |
| :--- | :--- |
| `$(call create_marker,name,ver)` | 完了マーカーファイルを作成。 |
| `$(call check_marker,name)` | マーカーの存在を確認（`test -f`）。 |
| `$(call check_min_version,cmd,name,req)` | Python を使用してセマンティックバージョニングを比較。 |
| `$(call check_symlink,src,dest)` | シンボリックリンクが正しく貼られているか検証。 |

## 5. 段階的セットアップのパターン (`main.mk`)
大規模なセットアップは以下の 7 段階で構成する：
1. システムセットアップ（メモリ最適化含む）
2. パッケージマネージャ（Homebrew 等）の初期化
3. アプリケーション本体のインストール
4. エコシステム（AI ツール等）の構築
5. 設定ファイル（Dotfiles）のリンク・配置
6. 拡張機能（VSCode/GNOME 等）の導入
7. 最終確認と最適化

## 6. テストファイルの構造
- **Mock Tests**: 外部依存（API、認証等）を排除したテスト。高速実行可能。
- **Integration Tests**: 実際の環境（`BW_SESSION` 等）を必要とするテスト。
- 命名規則: `test-` プレフィックスを使用（例: `test-bw-mock`）。

## 7. 新機能追加時のチェックリスト
- [ ] `mk/` 内に適切な命名規則でファイルを作成。
- [ ] `Makefile` (Root) での `include` 順序が論理構造（Core -> Infrastructure -> ...）に沿っているか。
- [ ] `mk/variables.mk` の `.PHONY` リストに新ターゲットを追加。
- [ ] `idempotency.mk` のマクロを使用して、二重実行を防止。
- [ ] `main.mk` の `setup-config-all` 等の統合ターゲットに組み込む必要があるか検討。
- [ ] 必要に応じて `test.mk` にテストケースを追加。
