# External Skills Manifest (Lock-file)

このプロジェクトで使用する外部スキルの**公式バージョン（Pin）**を定義するロックファイルです。
実ファイル（`agent-skills/superpowers/` 等）は Git 管理から除外されており、各環境で `make setup-superpowers` を実行することで、このファイルに記載された特定のコミットハッシュのスキルが再現されます。

| Skill Namespace | Source Repository | Version (Commit Hash) | Pinned At | Note |
| :--- | :--- | :--- | :--- | :--- |
| superpowers | https://github.com/obra/superpowers | e4a2375cb705ca5800f0833528ce36a3faf9017a | 2026-03-03 | AI Agent Workflow |
