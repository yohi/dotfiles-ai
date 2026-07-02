# Spec: Upgrade oh-my-openagent to v4.15.1

## 1. 目的
`oh-my-openagent` (OpenCode) を最新のリリースバージョン `v4.15.1` にアップグレードし、モデル設定と環境全体の整合性を維持した状態で再生成します。また、最新のリリースノートに基づき関連ドキュメントを更新します。

## 2. 変更内容

### ① `apm.yml` の更新
- `plugin:` セクションの `"oh-my-openagent@4.13.0"` を `"oh-my-openagent@4.15.1"` に更新します。
- `amazon-bedrock` などのモデル whitelist の整合性を検証します。現行のホワイトリストおよびモデル一覧は `models.dev` の最新スキーマに適合しているため、モデル定義自体の削除・追加は不要ですが、スキーマの変更がないかをチェックします。

### ② 設定ファイルの再生成
- 以下のコマンドを実行して、`apm.yml` から `opencode/oh-my-openagent.jsonc` などを再生成します。
  ```bash
  make sync-opencode
  ```

### ③ 環境プロファイル（`personal.env`, `work.env`）の確認
- `personal.env` および `work.env` の設定値を確認します。
  - `personal.env`: Amazon Bedrock モデルが含まれておらず、OpenAI / Gemini / Kimi モデル群が適切に割り当てられていることを確認します。
  - `work.env`: Amazon Bedrock モデル (`global.anthropic.claude-*`) のみが割り当てられていることを確認します。
- 今回の検証の結果、現在設定されているモデル（`claude-opus-4-8` や `claude-sonnet-5` など）は `models.dev` に存在し適合しているため、変更は不要です。

### ④ `opencode/README.md` の更新
- `Target Version` を `v4.15.1` に更新します。
- `v4.15.1` で導入された LazyCodex の自動修復機能および Codex スキル発見のクリーンアップなどについて、ドキュメントの適合を確認します。
- 既存の zsh 連携スクリプトや apm 同期手順、環境の切り替え方法などのプロジェクト固有のドキュメント記述は保護（維持）します。

## 3. 検証項目
- [ ] `make sync-opencode` が正常終了すること。
- [ ] `make check-sync-opencode` による整合性チェックがエラーなくパスすること。
- [ ] 生成された `opencode/oh-my-openagent.jsonc` のヘッダーコメントなどの Target Version が `v4.15.1` を指していること。

## 4. Gitコミットメッセージ
- `feat(opencode): oh-my-openagentをv4.15.1にアップグレード`
