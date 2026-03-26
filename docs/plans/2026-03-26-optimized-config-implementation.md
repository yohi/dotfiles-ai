# 2026-03-26 最適化設定（GPT/Claude/Gemini 役割特化型）実装プラン

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 2026年3月版の最新モデル（GPT-5.4, Claude 4.6, Gemini 3.1）を役割ごとに配置した設定ファイルを適用し、動作を確認する。

**Architecture:** ルートディレクトリに `oh-my-openagent.jsonc` を新規作成し、エージェント（build, plan）とカテゴリ（quick, explore）にそれぞれのモデルを割り当てる。

**Tech Stack:** JSONC (JSON with Comments), OpenAgent Configuration System

---

### Task 1: 設定ファイルの作成

**Files:**
- Create: `oh-my-openagent.jsonc`

**Step 1: 設定ファイルの書き込み**

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/dev/assets/oh-my-opencode.schema.json",
  "new_task_system_enabled": true,
  "default_run_agent": "gpt-5.4-mini",
  "hashline_edit": true,
  "model_fallback": true,
  "agents": {
    "build": {
      "model": "claude-4-6-sonnet",
      "thinking": {
        "type": "enabled",
        "budgetTokens": 16000
      }
    },
    "plan": {
      "model": "gpt-5.4-pro",
      "reasoningEffort": "high"
    }
  },
  "categories": {
    "quick": {
      "model": "gpt-5.4-mini"
    },
    "explore": {
      "model": "gemini-3.1-pro",
      "max_prompt_tokens": 1000000
    }
  },
  "experimental": {
    "preemptive_compaction": true,
    "aggressive_truncation": false
  }
}
```

**Step 2: ファイルが作成されたことを確認**

Run: `ls -l oh-my-openagent.jsonc`
Expected: ファイルが存在し、内容が正しいこと。

**Step 3: コミット**

```bash
git add oh-my-openagent.jsonc
git commit -m "feat: 2026年3月版の最適化設定（GPT/Claude/Gemini役割特化型）を適用"
```

---

### Task 2: 設定の妥当性検証

**Files:**
- Read: `oh-my-openagent.jsonc`

**Step 1: JSON 構造の検証 (Dry Run)**

設定ファイルが有効な JSON 構造（コメントを無視）であることを確認します。

Run: `sed 's/\/\/.*$//' oh-my-openagent.jsonc | jq .`
Expected: エラーなくパースされ、内容が表示されること。

**Step 2: スキーマURLの確認**

Run: `grep '"$schema"' oh-my-openagent.jsonc`
Expected: `"https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/dev/assets/oh-my-opencode.schema.json"` と一致すること。

**Step 3: コミット**

```bash
git commit --allow-empty -m "test: 2026年3月版最適化設定の構造検証完了"
```
