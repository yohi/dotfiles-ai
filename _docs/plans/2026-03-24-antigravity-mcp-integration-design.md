# Design: Antigravity & MCP Gateway Integration

## 1. Objective
Google Antigravity (IDE/Agent) を、統合的な MCP サーバーである Docker MCP Gateway (`localhost:10888`) と接続し、SkillPort のスキルやその他の MCP ツールを Antigravity 内でシームレスに利用可能にする。また、Antigravity の設定管理を OpenCode から切り離し、独立した管理ディレクトリとして整理する。

## 2. Architecture & Components
- **Antigravity (Standalone)**: Google の AI エージェント IDE。`~/.gemini/antigravity/` を本来の設定ディレクトリとする。
- **antigravity/mcp_config.json**: リポジトリ内の Antigravity 用 MCP 設定ファイル。
- **Docker MCP Gateway**: `http://localhost:10888/sse` で動作する SSE プロキシ。
- **SkillPort-MCP**: Gateway 経由で公開されるスキル管理ツール。

## 3. Configuration Details
`antigravity/mcp_config.json` に SSE ゲートウェイの設定を追加。
```json
{
  "mcpServers": {
    "gateway": {
      "url": "http://localhost:10888/sse"
    }
  }
}
```

## 4. Implementation Steps
1. **Directory Migration**: `antigravity/` をリポジトリルートに作成し、既存の `opencode/antigravity.json` の役割を整理。
2. **Configuration Setup**: `antigravity/mcp_config.json` を作成。
3. **Makefile Creation**: `_mk/antigravity.mk` を新設。`~/.gemini/antigravity/` へのシンボリックリンク機能を実装。
4. **Project Integration**: ルートの `Makefile` に `include _mk/antigravity.mk` を追加し、`setup-agents` ターゲットに `setup-antigravity` を組み込む。
5. **Validation**: Antigravity を起動し、`skillport` 関連のツールが認識されているか確認。

## 5. Deployment Path
- Repository: `antigravity/mcp_config.json`
- Target: `~/.gemini/antigravity/mcp_config.json` (Symlink)
