# SkillPort 使用ガイド

🛠️ SkillPort のセットアップが完了しました！

## 📦 インストールされているツール:
- `skillport`: スキル管理 CLI
- `skillport-mcp`: スキルを LLM に提供する MCP サーバー

## 📋 利用可能なコマンド例:
- `skillport list`                - 登録済みスキルの一覧表示
- `skillport info <skill-id>`     - スキルの詳細表示
- `skillport lint`                - スキルのバリデーション
- `skillport search <query>`      - スキルの検索

## 📂 スキルディレクトリ:
- **実体**: `.agents/skills/`
- **編集元**: `agent-skills/custom/`
- **設定**: `.skillportrc` の `skills_dir` は `./.agents/skills`

## 🩺 トラブルシューティング
設定に不備があると感じた場合は、ターミナルで以下を実行してください。
```bash
make doctor
```

## 🔄 スキルの同期
`make sync-agents` を実行することで、`.agents/skills/` の runtime tree と `agent-skills/custom/` の変更が各エージェント（Claude, Gemini, OpenCode等）に反映されます。
