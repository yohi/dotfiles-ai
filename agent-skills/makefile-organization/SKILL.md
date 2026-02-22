---
name: makefile-organization
description: Guidelines for organizing and maintaining modular Makefiles. Use when refactoring, creating new .mk files, or ensuring consistency across the project's Makefile structure. Covers naming conventions, inclusion order, idempotency management, and error handling for a robust development environment.
---

# Makefile Organization Rules

## Context
このプロジェクトのMakefile分割・保守に関するルール

## Instructions
<instructions>

> [!IMPORTANT]
> Makefile の詳細な分類、マクロ仕様、エラーハンドリング、テスト構造、および新機能追加時のチェックリストについては、[REFERENCE.md](./REFERENCE.md) を必ず参照してください。

### 1. Makefileの構造化
- 大きなMakefile（1000行以上）は機能別に分割する
- メインMakefileはincludeディレクティブと最小限のターゲットのみを含む
- 分割ファイルは`mk/`ディレクトリに格納する

### 2. ファイル命名規則
- 分割ファイル名は機能を表す英語名.mkとする
- ファイル名は**小文字のみ**を使用
- 複合語は**ハイフン1つ**で区切る（例: `sticky-keys.mk`）
- アンダースコアは使用しない
- 略語は避け、意味が明確な名前を使用する

### 3. include順序
メインMakefileでのinclude順序は以下の論理構造を遵守：
1. Core: `variables.mk`, `idempotency.mk`, `help.mk`, `presets.mk`
2. Infrastructure: `bitwarden.mk`
3. Functional: `system.mk`, `fonts.mk`, `install.mk`, `setup.mk`, `gnome.mk`, etc.
4. Meta: `main.mk`, `stages.mk`, `menu.mk`, `shortcuts.mk`, `deprecated-targets.mk`
5. AI & Tools: `cursor.mk`, `claude.mk`, `gemini.mk`, `opencode.mk`, etc.
6. Testing: `test.mk`

### 4. コーディング規則とメッセージ
- アクション-対象の形式：`setup-vim`, `install-homebrew`
- 動詞から始める：`install-`, `setup-`, `clean-`, `backup-`, `check-`, `test-`
- 絵文字を使用したフレンドリーなエコーメッセージを使用：
    - `🚀 セットアップを開始中...`
    - `📦 パッケージをインストール中...`
    - `✅ 完了`
    - `⚠️ 警告`
    - `❌ エラー`

### 5. 冪等性管理
`idempotency.mk`のマクロを使用して、時間のかかる処理の二重実行を防ぐ：
```makefile
@if $(call check_marker,target-name); then 
    echo "$(call IDEMPOTENCY_SKIP_MSG,target-name)"; 
    exit 0; 
fi
# ...
@$(call create_marker,target-name,1.0.0)
```
</instructions>

## Guidelines
<instructions>
- 新規ファイル追加時は `variables.mk` の PHONY リストを必ず更新すること。
- 1ファイルが200行を超えたら、更なる分割を検討すること。
</instructions>
