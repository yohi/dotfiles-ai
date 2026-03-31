# 2026-03-27 設定ファイルとドキュメントの現代化 デザイン

## 目的
OpenCode および関連ツールの設定ファイル、ドキュメント、スクリプトにおける不整合や安全性の懸念を解消し、最新のベストプラクティスと整合させる。

## 背景
コードレビューにより、以下の問題が指摘された：
1. `npm publish` の安全弁が緩和されている（`ask`）。
2. `visual` カテゴリのモデルとフォールバックが重複している。
3. `frontier-asia` プロファイルのドキュメントと実態が乖離している。
4. マシン固有の絶対パスが設定ファイルに含まれている。
5. ドキュメントの見出しレベルや正規表現、シェルスクリプトの互換性に不備がある。

## 設計詳細

### 1. 設定の安全性と整合性
- **`opencode/opencode.jsonc`**: 
    - ターゲットバージョンを `v1.3.x` に更新（新機能 `lsp`, `skill`, `task` の追加を反映）。
    - `npm publish*` を `deny` に戻し、事故を防止。
- **`oh-my-opencode.jsonc` シリーズ**:
    - `visual` カテゴリの `fallback_models` から重複する `google/gemini-3.1-pro` を削除。
- **`codex/config.toml`**:
    - 絶対パス `/home/y_ohi/...` を含むセクションを削除し、ポータビリティを向上。

### 2. 配置の適正化
- **`oh-my-openagent.jsonc`**:
    - ルートから `.opencode/oh-my-openagent.jsonc` に移動。
    - モデル ID をプロバイダープレフィックス付き（例: `openai/`, `anthropic/`）に統一。

### 3. ドキュメントとスクリプトの品質向上
- **Markdown**: `MD001`（見出しレベル）の修正。
- **正規表現**: URL の `https://` を破壊しないように修正。
- **シェルスクリプト**: `omo-profiles.sh` を Bash 互換にし、堅牢なパス解決を導入。
- **内容の更新**: `ANALYSIS.ja.md` のモデル例を最新世代（GPT-5, Claude 4）に更新。

## 検証計画
- `opencode.jsonc` のパース確認。
- `omo-profiles.sh` のソース読み込みとプロファイル切り替えの動作確認。
- `oh-my-openagent.jsonc` のスキーマ準拠確認。
