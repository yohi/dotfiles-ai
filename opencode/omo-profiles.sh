#!/bin/bash

# oh-my-opencode プロファイル切り替え関数
# 使い方: source ./opencode/omo-profiles.sh && omo-set-profile hybrid

function omo-set-profile() {
  local profile=$1
  case $profile in
    "hybrid") # 最強のハイブリッド：品質とエージェント能力のベストミックス
      export ULTRABRAIN_MODEL="anthropic/claude-4-6-opus"
      export CRAFTSMAN_MODEL="openai/gpt-5-3-codex"
      export DEEP_MODEL="opencode/glm-5-free"
      export VISUAL_MODEL="google/gemini-3-1-pro"
      export QUICK_MODEL="opencode/minimax-m2-5-free"
      echo "🚀 Profile: [Hybrid] Set - Balanced Excellence"
      ;;
      
    "reasoning") # 深考モード：難解なバグ修正、アルゴリズム設計、複雑なリサーチ
      export ULTRABRAIN_MODEL="openai/gpt-5-4-thinking"
      export CRAFTSMAN_MODEL="anthropic/claude-4-6-opus"
      export DEEP_MODEL="opencode/kimi-k2-5-free"
      export VISUAL_MODEL="google/gemini-3-1-pro"
      export QUICK_MODEL="openai/gpt-5-4-mini"
      echo "🧠 Profile: [Reasoning] Set - Slow but Extremely Deep"
      ;;

    "frontier-asia") # アジア・フロンティア：高速、多機能、コスト効率
      export ULTRABRAIN_MODEL="opencode/glm-5-free"
      export CRAFTSMAN_MODEL="opencode/minimax-m2-5-free"
      export DEEP_MODEL="opencode/kimi-k2-5-free"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="opencode/mimo-v2-flash-free"
      echo "🌏 Profile: [Frontier-Asia] Set - High speed, low cost, agent-focused"
      ;;

    "creative-ui") # UI/UX 開発：デザインの正確性とマルチモーダル検証
      export ULTRABRAIN_MODEL="anthropic/claude-4-6-opus"
      export CRAFTSMAN_MODEL="anthropic/claude-4-6-sonnet"
      export DEEP_MODEL="opencode/mimo-v2-pro-free"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="google/gemini-3-1-flash-lite"
      echo "🎨 Profile: [Creative-UI] Set - Optimized for Visuals & Design"
      ;;

    "speed") # スピード優先：単純作業、大量のリファクタリング、ドキュメント生成
      export ULTRABRAIN_MODEL="anthropic/claude-4-6-sonnet"
      export CRAFTSMAN_MODEL="opencode/minimax-m2-5-free"
      export DEEP_MODEL="opencode/glm-5-free"
      export VISUAL_MODEL="google/gemini-3-1-flash-lite"
      export QUICK_MODEL="opencode/mimo-v2-flash-free"
      echo "⚡ Profile: [Speed] Set - High throughput for routine tasks"
      ;;

    "gpt-first") # GPT-First (Efficient): GPT-5.4を脳に、無料モデルを脇役に
      export ULTRABRAIN_MODEL="openai/gpt-5-4"
      export CRAFTSMAN_MODEL="openai/gpt-5-3-codex"
      export DEEP_MODEL="opencode/glm-5-free"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="openai/gpt-5-4-mini"
      echo "🤖 Profile: [GPT-First] Set - GPT-5.4 Brain with OpenCode Free Support"
      ;;

    *)
      echo "Usage: omo-set-profile [hybrid|reasoning|frontier-asia|creative-ui|speed|gpt-first]"
      return 1
      ;;
  esac

  # テンプレートから設定ファイルを生成
  local template_path="./opencode/oh-my-opencode.jsonc.template"
  local output_path="./opencode/oh-my-opencode.jsonc"
  
  if [ -f "$template_path" ]; then
    # 環境変数を展開して上書き生成
    envsubst < "$template_path" > "$output_path"
    echo "📄 Config generated: $output_path"
  else
    echo "⚠️ Warning: Template not found at $template_path"
  fi
}

# 読み込み時にデフォルトをセット
omo-set-profile hybrid
