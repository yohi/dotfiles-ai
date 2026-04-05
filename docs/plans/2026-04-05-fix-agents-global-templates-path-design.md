# Design: Fix Template Path Example in AGENTS.global.md

## 1. Overview
`global-rules/AGENTS.global.md` の Tips セクションにおいて、スキルテンプレートへのアクセス方法を示す例示パスが、実際のディレクトリ構造と不整合を起こしているため、これを修正する。

## 2. Goals
- 具体的かつ不正確な例示を排除し、汎用的で正しい指示に変更する。
- エージェントが間違った場所（各スキルの `templates/` フォルダなど）を探索しようとするのを防ぐ。

## 3. Proposed Changes
- **Target File**: `global-rules/AGENTS.global.md`
- **Section**: `### Tips` (Line 56)
- **Modification**:
    - Old: `{skill_dir}/templates/SKILL_TEMPLATE.md`
    - New: `{path}/templates/<filename>`

## 4. Verification Plan
- `global-rules/AGENTS.global.md` を直接確認し、記述が更新されていることを確認する。
