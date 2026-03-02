# Superpowers ワークフロー統合 設計ドキュメント

**目標:** superpowers ワークフローをプロジェクトのセットアップ工程に統合し、PRを作成して変更を確定させる。

**背景:** `Makefile` の変更と `_mk/superpowers.mk` ファイルの追加により、プロジェクトのセットアップ時に superpowers スキルの導入とリンクが自動化される。

**アプローチ:**
- Git を使用して新しいフィーチャーブランチ `feature/integrate-superpowers-workflow` を作成する。
- 既存の変更（Makefile, _mk/superpowers.mk）および本設計・計画ドキュメントをコミットする。
- GitHub CLI (`gh`) を使用してプルリクエストを作成する。

**検証:**
- ブランチが正しく作成されていること。
- コミットが記録されていること。
- GitHub 上に PR が作成されていること。
