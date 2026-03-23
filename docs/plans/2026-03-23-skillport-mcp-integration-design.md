# Design: SkillPort & MCP Integration

## 1. Objective
統合エージェントスキル管理ツール `skillport` を MCP (Model Context Protocol) サーバーとしてセットアップし、既存の `docker-mcp-gateway` を介して、Claude Code, Gemini CLI, Cursor などの各種 AI エージェントから一括してスキルを利用可能にする。

## 2. Architecture & Components
- **SkillPort (CLI)**: `./agent-skills` ディレクトリ内のスキルを管理。`.skillportrc` で設定。
- **skillport-mcp**: SkillPort を MCP サーバーとして動作させるアダプター。
- **Docker MCP Gateway**: `localhost:10888` で動作する SSE プロキシ。各種エージェントの共通エンドポイント。
- **AI Agents**:
    - **Claude Code**: Gateway に接続。
    - **Gemini CLI**: Gateway に接続。
    - **Cursor**: Gateway に接続。

## 3. Data Flow
1. エージェントが Gateway (`:10888`) へリクエスト。
2. Gateway が `mcp/config.yaml` の設定に基づき `skillport-mcp` を起動。
3. `skillport-mcp` が `./agent-skills/*.md` を解析し、MCP Tools として公開。
4. エージェントが Tool を実行し、スキルの内容（インストラクション等）を取得・適用。

## 4. Implementation Steps
1. **Tool Installation**: `make skillport` を実行し、`skillport` および `skillport-mcp` をインストール。
2. **MCP Configuration**: `mcp/config.yaml` に `skillport-mcp` サーバーの設定を追加。
3. **Environment Setup**: `make setup-docker-mcp` を実行し、設定ファイルを `~/.docker/mcp/` へ同期。
4. **Service Restart**: `docker-mcp-gateway.service` を再起動して設定を反映。
5. **Validation**: 各エージェントから `skillport` 関連の Tool が認識されているか確認。

## 5. Error Handling & Monitoring
- `journalctl --user -u docker-mcp-gateway -f` でログを監視。
- スキル定義ファイル (`.md`) の構文エラー時は `skillport check` でデバッグ。
