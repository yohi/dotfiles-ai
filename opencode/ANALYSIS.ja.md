# oh-my-openagent プロジェクト分析レポート

`oh-my-openagent`（通称 `oh-my-opencode`）は、OpenCode（Claude Codeのフォーク）を極限まで強化した、マルチモデル・オーケストレーション・エージェント・ハーネスです。

## 1. プロジェクト概要
- **目的**: 単一のLLMモデルに依存せず、複数のモデル（Claude, GPT, Gemini, Kimi等）を専門分野に合わせて並列かつ自律的に動作させ、開発効率を最大化する。
- **哲学**: エージェントが「本物のシニアエンジニア」のように振る舞い、計画、委任、検証を自律的に行う。

## 2. 主要なディレクトリ構造と役割

| ディレクトリ | 役割 |
| :--- | :--- |
| `src/agents/` | 11種類の特化型エージェント（Sisyphus, Hephaestus, Prometheus等）。 |
| `src/tools/` | エージェントに精度を与える26種類のツール（Hashline, LSP, AST-Grep等）。 |
| `src/hooks/` | 48種類のライフサイクルフック。セッション全体を細かく制御。 |
| `src/features/` | 背景実行、tmux連携、MCP管理などの高レベルモジュール。 |
| `src/cli/` | Commander.js を使用した CLI 実装（install, run, doctor等）。 |
| `.opencode/` | プロジェクト固有のスキル、コマンド、バックグラウンドタスクの設定。 |
| `packages/` | 各プラットフォーム向けのバイナリパッケージ。 |

## 3. 規律あるエージェント（Discipline Agents）

- **Sisyphus**: メインのオーケストレーター。計画、委任、検証を統括。
- **Hephaestus**: 自律的なディープワーカー。目標に対して能動的にコードを探索・修正。
- **Prometheus**: 戦略プランナー。実装前にインタビューモードで要件を詰め、検証済みの計画を構築。
- **Oracle / Librarian**: 知識ベースの検索やアーキテクチャの評価を担当。

## 4. 核心的な技術

### Hashline (Hash-Anchored Edits)
- 行ごとにコンテンツハッシュを付与し、編集時の不整合（stale-lineエラー）を排除。
- エージェントが最後に読んだ状態と現在のファイル状態が一致するかを厳密に検証。

### Intent Gate
- ユーザーの入力をそのまま実行するのではなく、真の意図（リサーチ、実装、修正、評価など）を分析してから適切なルーティングを行う。

### マルチモデル・オーケストレーション
- `visual-engineering`, `deep`, `quick`, `ultrabrain` といったカテゴリーに基づき、最適なモデル（Claude 3.7, GPT-4o, Kimi K2.5等）を自動的に選択。

## 5. 主要機能

- **`ultrawork` / `ulw`**: 全エージェントをアクティブにし、タスクが完了するまで自律的に働き続けるモード。
- **Tmux統合**: エージェントが tmux 内でインタラクティブターミナル（REPL、デバッガー等）を操作。
- **Claude Code 互換性**: Claude Code 用のフック、スキル、MCP、プラグインをそのままサポート。
- **`/init-deep`**: プロジェクト全体に階層的な `AGENTS.md` を自動生成し、コンテキスト効率を向上。

## 6. 技術スタック

- **Runtime**: Bun (全面的に採用)
- **Language**: TypeScript (Strict mode, ESNext)
- **Tools**: AST-Grep, LSP, Commander.js, Zod (Config validation)
- **Testing**: Bun test (`bun:test`), ライフサイクルフックやエージェントプロンプトの膨大なテストケース。

---
*このレポートは Gemini CLI によって自動生成されました。*
