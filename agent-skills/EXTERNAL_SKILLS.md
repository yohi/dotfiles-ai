# External Skills Manifest (Lock-file)

このプロジェクトで使用する外部スキルの**公式バージョン（Pin）**を定義するロックファイルです。
実ファイル（`agent-skills/superpowers/` 等）は Git 管理から除外されており、各環境で `make setup-superpowers` を実行することで、このファイルに記載された特定のコミットハッシュのスキルが再現されます。

| Skill Namespace | Source Repository | Version (Commit Hash) | Pinned At | Note |
| :--- | :--- | :--- | :--- | :--- |
| superpowers | https://github.com/obra/superpowers | 917e5f53b16b115b70a3a355ed5f4993b9f8b73d | 2026-04-07 | AI Agent Workflow |
