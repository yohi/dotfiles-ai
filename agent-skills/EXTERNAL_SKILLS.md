# External Skills Manifest (Lock-file)

このプロジェクトで使用する外部スキルの**公式バージョン（Pin）**を定義するロックファイルです。
実ファイル（`agent-skills/superpowers/` 等）は Git 管理から除外されており、各環境で `make setup-superpowers` を実行することで、このファイルに記載された特定のコミットハッシュのスキルが再現されます。

| Skill Namespace | Source Repository | Version (Commit Hash) | Pinned At | Note |
| :--- | :--- | :--- | :--- | :--- |
| superpowers | https://github.com/obra/superpowers | c4bbe651cb1bc5e7bec6f7effae2b946571f3258 | 2026-04-17 | AI Agent Workflow |
| anthropics | https://github.com/anthropics/skills | 98669c11ca63e9c81c11501e1437e5c47b556621 | 2026-04-09 | Official Anthropic Skills |
