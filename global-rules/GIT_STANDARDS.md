# Global Git & Version Control Standards

すべてのプロジェクトにおいて、以下のGit運用ルールを遵守してください。

## 1. コミットメッセージ
[Conventional Commits](https://www.conventionalcommits.org/ja/v1.0.0/) に従い、**日本語**で記述してください。

### フォーマット
`type(scope): subject`

### Types
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメントのみの変更
- `style`: コードの動作に影響しない変更
- `refactor`: バグ修正も機能追加も行わない変更
- `test`: テスト関連
- `chore`: ビルドやツール関連

**例**: `feat(auth): Googleログイン機能を追加`

## 2. プルリクエスト (PR)
- タイトルはコミットメッセージと同様のフォーマットを使用してください。
- **通常の会話でPR作成を依頼された場合**: 変更の「概要(What)」と「目的(Why)」を簡潔に記述してください。
- **本格的なPR作成**: `/git-pr-flow` コマンドが利用可能な場合は、そちらを使用してください。
