# Design Doc: OpenCode A2A Provider Integration (Local Path)

## Status
- **Date**: 2026-03-25
- **Author**: Gemini CLI
- **Status**: Approved

## Context
OpenCode で A2A (Agent to Agent) プロバイダーを利用可能にするため、ローカル開発環境にあるプロバイダーパッケージを `file://` プロトコルを使用して登録します。
ユーザーからの指示に基づき、最小限の構成（オプション省略、モデル指定省略、ベース設定変更なし）で統合を行います。

## Proposed Changes

### 1. `opencode/opencode.jsonc`
`provider` セクションに `opencode-geminicli-a2a` プロバイダーを追加します。

- **Provider Key**: `opencode-geminicli-a2a`
- **NPM Package Path**: `file:///home/y_ohi/program/opencode-geminicli-a2a`
- **Options**: 省略（デフォルト設定 127.0.0.1:41242 を使用）
- **Models**:
  - `gemini-3.1-pro-preview`: `true`
  - `gemini-3-flash-preview`: `true`
  - `gemini-2.5-pro`: `true`

## Implementation Plan
1. `opencode/opencode.jsonc` を編集し、`provider` セクションに上記設定を挿入する。
2. 変更内容に文法エラー（JSONC形式）がないか確認する。

## Verification Strategy
- `opencode.jsonc` の内容が正しく更新されていることを目視で確認する。
- (可能であれば) OpenCode の設定読み込みコマンド等で構文チェックを行う。
