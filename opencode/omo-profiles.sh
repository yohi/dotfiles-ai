#!/bin/bash

# oh-my-opencode プロファイル切り替え関数
# 使い方: source ./opencode/omo-profiles.sh && omo-set-profile hybrid

function omo-set-profile() {
  local profile=$1
  case $profile in
    "hybrid") # 最強のハイブリッド：品質とエージェント能力のベストミックス
      export ULTRABRAIN_MODEL="anthropic/claude-opus-4-6"
      export CRAFTSMAN_MODEL="openai/gpt-5.3-codex"
      export DEEP_MODEL="opencode/big-pickle"
      export VISUAL_MODEL="google/gemini-3.1-pro"
      export QUICK_MODEL="opencode/minimax-m2.5-free"
      echo "🚀 Profile: [Hybrid] Set - Balanced Excellence"
      ;;
      
    "reasoning") # 深考モード：難解なバグ修正、アルゴリズム設計、複雑なリサーチ
      export ULTRABRAIN_MODEL="openai/gpt-5.4-thinking"
      export CRAFTSMAN_MODEL="anthropic/claude-opus-4-6"
      export DEEP_MODEL="opencode/big-pickle"
      export VISUAL_MODEL="google/gemini-3.1-pro"
      export QUICK_MODEL="openai/gpt-5.4-mini"
      echo "🧠 Profile: [Reasoning] Set - Slow but Extremely Deep"
      ;;

    "frontier-asia") # アジア・フロンティア：高速、多機能、コスト効率（完全無料枠）
      export ULTRABRAIN_MODEL="opencode/big-pickle"
      export CRAFTSMAN_MODEL="opencode/nemotron-3-super-free"
      export DEEP_MODEL="opencode/mimo-v2-pro-free"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="opencode/minimax-m2.5-free"
      echo "🌏 Profile: [Frontier-Asia] Set - High speed, low cost, agent-focused"
      ;;

    "creative-ui") # UI/UX 開発：デザインの正確性とマルチモーダル検証
      export ULTRABRAIN_MODEL="anthropic/claude-opus-4-6"
      export CRAFTSMAN_MODEL="anthropic/claude-sonnet-4-6"
      export DEEP_MODEL="opencode/mimo-v2-pro-free"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="google/gemini-3.1-flash-lite"
      echo "🎨 Profile: [Creative-UI] Set - Optimized for Visuals & Design"
      ;;

    "speed") # スピード優先：単純作業、大量のリファクタリング、ドキュメント生成
      export ULTRABRAIN_MODEL="anthropic/claude-sonnet-4-6"
      export CRAFTSMAN_MODEL="opencode/nemotron-3-super-free"
      export DEEP_MODEL="opencode/big-pickle"
      export VISUAL_MODEL="google/gemini-3.1-flash-lite"
      export QUICK_MODEL="opencode/minimax-m2.5-free"
      echo "⚡ Profile: [Speed] Set - High throughput for routine tasks"
      ;;

    "gpt-first") # GPT-First (Efficient): GPT-5.4を脳に、無料モデルを脇役に
      export ULTRABRAIN_MODEL="openai/gpt-5.4"
      export CRAFTSMAN_MODEL="openai/gpt-5.3-codex"
      export DEEP_MODEL="opencode/big-pickle"
      export VISUAL_MODEL="opencode/mimo-v2-omni-free"
      export QUICK_MODEL="openai/gpt-5.4-mini"
      echo "🤖 Profile: [GPT-First] Set - GPT-5.4 Brain with OpenCode Free Support"
      ;;

    *)
      echo "Usage: omo-set-profile [hybrid|reasoning|frontier-asia|creative-ui|speed|gpt-first]"
      return 1
      ;;
  esac

  # スクリプトの場所を基準にパスを解決
  local script_path="${BASH_SOURCE[0]:-$0}"
  local script_dir
  script_dir="$(dirname "$script_path")"
  
  # cd と pwd を分離し、エラーチェックを導入
  if ! script_dir="$(cd "$script_dir" && pwd)"; then
    echo "⚠️ Error: Could not determine script directory" >&2
    return 1
  fi
  local template_path="${script_dir}/oh-my-opencode.jsonc.template"
  local output_path="${script_dir}/oh-my-opencode.jsonc"
  local base_template_path="${script_dir}/opencode.jsonc.template"
  local base_output_path="${script_dir}/opencode.jsonc"
  
  if [ -f "$script_dir/../.env" ]; then
    # allexport の現在の状態を保存
    case "$-" in
      *a*) local restore_allexport="set -a" ;;
      *) local restore_allexport="set +a" ;;
    esac
    set -a
    # shellcheck source=/dev/null
    if ! source "$script_dir/../.env"; then
      echo "❌ Error: Failed to source $script_dir/../.env" >&2
      $restore_allexport
      return 1
    fi
    $restore_allexport
  fi

  # 環境変数を展開して上書き生成 (対象変数のみを置換)
  local vars_to_subst='$ULTRABRAIN_MODEL:$CRAFTSMAN_MODEL:$DEEP_MODEL:$VISUAL_MODEL:$QUICK_MODEL:$MCP_GATEWAY_TOKEN:$FLIXA_NPM_PACKAGE'
  
  if [ -f "$template_path" ] || [ -f "$base_template_path" ]; then
    if [ -z "${FLIXA_NPM_PACKAGE:-}" ]; then
      echo "⚠️  Warning: FLIXA_NPM_PACKAGE is not set. Using 'dummy' for substitution." >&2
      export FLIXA_NPM_PACKAGE="dummy"
    fi
  fi

  if [ -f "$template_path" ]; then
    if envsubst "$vars_to_subst" < "$template_path" > "$output_path"; then
      echo "📄 Config generated: $output_path"
    else
      echo "❌ Error: Failed to generate $output_path" >&2
      return 1
    fi
  fi

  if [ -f "$base_template_path" ]; then
    if envsubst "$vars_to_subst" < "$base_template_path" > "$base_output_path"; then
      echo "📄 Base Config generated: $base_output_path"
      # マージ処理: oh-my-opencode.jsonc から agents セクションを抽出し、
      # opencode.jsonc の "agent": { セクション内にマージする
      if [ -f "$output_path" ]; then
        echo "🔗 Merging agents from $output_path into 'agent' section of $base_output_path..."
        # 既存の "agent": { の次の行に、抽出したエージェント定義を挿入
        # 一時ファイルを使ってエージェント内容を抽出
        sed -n '/"agents": {/,/^  }/p' "$output_path" | sed '1d' | sed '$d' > agents_to_merge.tmp
        # 最後の要素にカンマが必要な場合があるので調整
        sed -i 's/    }/    },/' agents_to_merge.tmp
        # 挿入実行
        sed -i '/"agent": {/r agents_to_merge.tmp' "$base_output_path"
        rm agents_to_merge.tmp
        # カンマ重複（,,）を修正
        sed -i 's/},,/},/g' "$base_output_path"
      fi
    else
      echo "❌ Error: Failed to generate $base_output_path"
      return 1
    fi
  fi
}

# 読み込み時にデフォルトをセット
# omo-set-profile hybrid は、環境変数が準備できた段階で明示的に呼び出す必要があります。
