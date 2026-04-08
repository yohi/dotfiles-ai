# Design Spec: Makefile Reorganization (v2)

## 1. Goal
Makefileを「薄いエントリーポイント」として整理し、ロジックを `_mk/` 配下のモジュールに完全に委譲することで、メンテナンス性と拡張性を向上させる。
特に、親プロジェクト（`~/dotfiles`）から提供される共通ルール（`core.mk`, `help.mk`）との整合性を保ちつつ、本コンポーネント固有のワークフローを `main.mk` に集約する。

## 2. Architecture & File Roles

### 2.1. `Makefile` (Entry Point)
- **Role**: モジュールの統合とエントリーポイントの提供。
- **Changes**: 
  - ターゲットの実装（`install-ai`, `setup-ai` 等）を削除。
  - `_mk/` 配下のファイルを適切な順序で `include` するのみに留める。

### 2.2. `_mk/core.mk` & `_mk/help.mk` (Common Base)
- **Role**: 親プロジェクト（`~/dotfiles/common-mk`）から提供される共通ルールとヘルプ表示機能。
- **Constraint**: 原則として直接編集せず、リンクとして扱う（本プロジェクト固有の強化は `main.mk` で行う）。

### 2.3. `_mk/main.mk` (Component Orchestrator)
- **Role**: 本プロジェクト固有のワークフロー（`all`, `install`, `setup`, `clean`, `test`, `sync`, `status`）の定義と制御。
- **Changes**: 
  - 親プロジェクトの `dispatch` マクロから呼び出される標準ターゲットの実装をここで行う。
  - `Makefile` に残っていた `install-ai`, `setup-ai` 等のロジックをここに統合・整理する。

### 2.4. `_mk/*.mk` (Component Modules)
- **Role**: 各ツール（Claude, Gemini, Cursor等）に特化したターゲット定義。
- **Changes**: 既存のモジュール構造を維持。

## 3. Implementation Plan

1. **Step 1: `_mk/main.mk` の再構築**
   - `Makefile` にあるロジックを統合し、親プロジェクトが期待する標準ターゲット（`all`, `install`, `setup`, `sync`, `status`）を洗練させる。
2. **Step 2: `Makefile` の簡素化**
   - `include` 文のみの構成に変更。
3. **Step 3: `variables.mk` のクリーンアップ**
   - 不要な `.PHONY` 定義を削除し、変数定義に専念させる。

## 4. Verification Strategy
- `make help` が正しく全てのカテゴリ（Main / Common, AI Tools, IDE, etc.）を表示することを確認。
- `make all` (ドライラン: `make -n all`) で、期待通りの順序（install -> setup -> sync 等）でターゲットが呼び出されることを確認。
- 親プロジェクトの `make all` から正しく本コンポーネントが呼び出されることを確認。
