# External Skills Manifest (Lock-file)

このプロジェクトで使用する外部スキルの**公式バージョン（Pin）**を定義するロックファイルです。
実ファイル（`agent-skills/superpowers/` 等）は Git 管理から除外されており、各環境で `make setup-superpowers` を実行することで、このファイルに記載された特定のコミットハッシュのスキルが再現されます。

| Skill Namespace | Source Repository | Version (Commit Hash) | Pinned At | Note |
| :--- | :--- | :--- | :--- | :--- |
| superpowers | https://github.com/obra/superpowers | 6efe32c9e2dd002d0c394e861e0529675d1ab32e | 2026-04-27 | AI Agent Workflow |
| anthropics | https://github.com/anthropics/skills | 98669c11ca63e9c81c11501e1437e5c47b556621 | 2026-04-09 | Official Anthropic Skills |
