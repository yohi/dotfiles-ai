# 2026-03-26 最適化設定（GPT/Claude/Gemini 役割特化型）デザインドキュメント

## 1. 概要
2026年3月時点の最新LLM（GPT-5.4, Claude 4.6, Gemini 3.1）の特性を最大限に活かし、コーディング、計画立案、広域探索のバランスを最適化した `oh-my-openagent.jsonc` の構成案です。

## 2. アーキテクチャと役割分担

### 2.1 モデル選定の根拠
- **Claude 4.6 Sonnet**: プログラミング知能において最も信頼性が高く、`thinking` 機能を有効にすることで難解なバグ修正や複雑な実装を確実に遂行します。
- **GPT-5.4 Pro**: 高度な推論と命令遵守能力を持ち、プロジェクト全体の整合性を保つための計画（Plan）フェーズでリーダーシップを発揮します。
- **Gemini 3.1 Pro / Flash-Lite**: 100万トークンの広大なコンテキスト窓を活用し、大規模なコードベースの全貌把握（Explore）や履歴の要約（Compaction）を高速かつ低コストで行います。
- **GPT-5.4 mini**: 軽量かつ最新のエージェント機能を備えており、日常的なコマンド実行（Quick/Run）のデフォルトとして運用します。

### 2.2 具体的な割り当て
- **実装 (`build`)**: Claude 4.6 Sonnet (Thinking有効)
- **設計・計画 (`plan`)**: GPT-5.4 Pro (ReasoningEffort: High)
- **広域探索 (`explore`)**: Gemini 3.1 Pro (MaxPromptTokens: 1,000,000)
- **標準・実行 (`quick`, `run`)**: GPT-5.4 mini

## 3. 設定ファイル構成 (oh-my-openagent.jsonc)

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/refs/heads/dev/dist/oh-my-opencode.schema.json",
  "new_task_system_enabled": true,
  "default_run_agent": "openai/gpt-5.4-mini",
  "hashline_edit": true,
  "model_fallback": true,
  "agents": {
    "build": {
      "model": "anthropic/claude-4-6-sonnet",
      "thinking": {
        "type": "enabled",
        "budgetTokens": 16000
      }
    },
    "plan": {
      "model": "openai/gpt-5.4-pro",
      "reasoningEffort": "high"
    }
  },
  "categories": {
    "quick": {
      "model": "openai/gpt-5.4-mini"
    },
    "explore": {
      "model": "google/gemini-3.1-pro",
      "max_prompt_tokens": 1000000
    }
  },
  "experimental": {
    "preemptive_compaction": true,
    "aggressive_truncation": false
  }
}
```

## 4. テストと検証
1. 設定ファイルがスキーマに準拠していることを確認する。
2. `oh-my-openagent.jsonc` をルートに作成し、プラグインが正しく各モデルを認識してロードすることを確認する。
