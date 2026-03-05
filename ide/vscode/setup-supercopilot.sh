#!/bin/bash

# SuperCopilot Framework インストールスクリプト
# VSCode/GitHub Copilotのペルソナ自動選択機能を設定します
#
# Note: This script supports both Linux and macOS.
# For best results, install jq: brew install jq (macOS) or apt install jq (Linux)

# 色の定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

if [ "$EUID" -eq 0 ]; then
  echo -e "${RED}エラー: このスクリプトは root (sudo) 権限で実行しないでください${NC}"
  echo -e "一般ユーザーの ~/.vscode/settings.json を更新するため、通常ユーザーとして実行する必要があります。"
  exit 1
fi

# 現在のディレクトリを確認
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}SuperCopilot Framework セットアップを開始します...${NC}"
echo -e "${YELLOW}dotfiles ディレクトリ: ${REPO_ROOT}${NC}"

# 1. .vscodeディレクトリの作成
echo -e "\n${BLUE}1. .vscodeディレクトリを確認/作成しています...${NC}"
if [ ! -d "$HOME/.vscode" ]; then
  echo -e "   ${YELLOW}~/.vscodeディレクトリが存在しないため、作成します${NC}"
  mkdir -p "$HOME/.vscode"
  if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✓ ~/.vscodeディレクトリを作成しました${NC}"
  else
    echo -e "   ${RED}✗ ~/.vscodeディレクトリの作成に失敗しました${NC}"
    exit 1
  fi
else
  echo -e "   ${GREEN}✓ ~/.vscodeディレクトリは既に存在します${NC}"
fi

# 2. シンボリックリンクの作成
echo -e "\n${BLUE}2. SuperCopilot設定のシンボリックリンクを作成しています...${NC}"
if [ -e "$HOME/.vscode/supercopilot" ]; then
  if ! [ -L "$HOME/.vscode/supercopilot" ]; then
    echo -e "   ${YELLOW}既存のファイル/ディレクトリをバックアップします${NC}"
    mv "$HOME/.vscode/supercopilot" "$HOME/.vscode/supercopilot.bak.$(date +%s)"
  else
    echo -e "   ${YELLOW}既存のシンボリックリンクを削除します${NC}"
    rm "$HOME/.vscode/supercopilot"
  fi
fi

ln -sf "$REPO_ROOT/vscode/settings" "$HOME/.vscode/supercopilot"
if [ $? -eq 0 ]; then
  echo -e "   ${GREEN}✓ シンボリックリンクを作成しました${NC}"
  echo -e "   ${GREEN}  $REPO_ROOT/vscode/settings -> $HOME/.vscode/supercopilot${NC}"
else
  echo -e "   ${RED}✗ シンボリックリンクの作成に失敗しました${NC}"
  exit 1
fi

# 3. settings.jsonの設定確認と生成
echo -e "\n${BLUE}3. VSCode設定を確認しています...${NC}"
VSCODE_SETTINGS="$HOME/.vscode/settings.json"
userHome="${HOME}"
CONFIG_JSON='{"github.copilot.advanced": {"preProcessors": {"chat": {"path": "'"${userHome}"'/.vscode/supercopilot/supercopilot-main.js", "function": "preprocessCopilotPrompt"}}}}'

# jqが利用可能かチェック
if command -v jq >/dev/null 2>&1; then
  echo -e "   ${GREEN}✓ jq が利用可能です。安全なJSON操作を使用します${NC}"

  if [ -f "$VSCODE_SETTINGS" ]; then
    echo -e "   ${GREEN}✓ VSCode設定ファイルが見つかりました${NC}"

    # 設定が既にあるか確認
    if jq -e '.github.copilot.advanced.preProcessors.chat | has("path")' "$VSCODE_SETTINGS" >/dev/null 2>&1 && \
       jq -r '.github.copilot.advanced.preProcessors.chat.path' "$VSCODE_SETTINGS" | grep -q "supercopilot-main.js"; then
      echo -e "   ${GREEN}✓ SuperCopilot設定は既に追加されています${NC}"
    else
      echo -e "   ${YELLOW}SuperCopilot設定を追加します...${NC}"

      # 既存ファイルのバックアップ作成
      cp "$VSCODE_SETTINGS" "${VSCODE_SETTINGS}.backup"

      # VSCODE_SETTINGSが空、空白のみ、または空オブジェクトかを判定して初期化する
      if [ ! -s "$VSCODE_SETTINGS" ] || [ -z "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" ] || [ "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" = "{}" ] || jq -e '. == {}' "$VSCODE_SETTINGS" >/dev/null 2>&1; then
        echo "{}" > "$VSCODE_SETTINGS"
      fi

      # 既存のsettings.jsonと新しい設定をマージ
      if jq --argjson config "$CONFIG_JSON" '. * $config' "$VSCODE_SETTINGS" > "${VSCODE_SETTINGS}.tmp"; then
        mv "${VSCODE_SETTINGS}.tmp" "$VSCODE_SETTINGS"

        # JSON構文の検証
        if jq empty "$VSCODE_SETTINGS" >/dev/null 2>&1; then
          echo -e "   ${GREEN}✓ settings.jsonに設定を追加しました${NC}"
          rm -f "${VSCODE_SETTINGS}.backup"
        else
          echo -e "   ${RED}✗ JSON構文エラーが発生しました。設定を復元します${NC}"
          # バックアップがあれば復元
          if [ -f "${VSCODE_SETTINGS}.backup" ]; then
            mv "${VSCODE_SETTINGS}.backup" "$VSCODE_SETTINGS"
          fi
          exit 1
        fi
      else
        echo -e "   ${RED}✗ 設定の追加に失敗しました${NC}"
        exit 1
      fi
    fi
  else
    echo -e "   ${YELLOW}VSCode設定ファイルが見つかりません。新規作成します...${NC}"
    # 新しいsettings.jsonファイルを作成
    mkdir -p "$(dirname "$VSCODE_SETTINGS")"
    echo "$CONFIG_JSON" | jq . > "$VSCODE_SETTINGS"

    if jq empty "$VSCODE_SETTINGS" >/dev/null 2>&1; then
      echo -e "   ${GREEN}✓ 新しいsettings.jsonファイルを作成しました${NC}"
    else
      echo -e "   ${RED}✗ settings.jsonの作成に失敗しました${NC}"
      exit 1
    fi
  fi
else
  echo -e "   ${YELLOW}jq が利用できません。従来のsed方式を使用します${NC}"
  CONFIG_ENTRY='"github.copilot.advanced": { "preProcessors": { "chat": { "path": "'"${userHome}"'/.vscode/supercopilot/supercopilot-main.js", "function": "preprocessCopilotPrompt" } } }'

  if [ -f "$VSCODE_SETTINGS" ]; then
    echo -e "   ${GREEN}✓ VSCode設定ファイルが見つかりました${NC}"

    # 設定が既にあるか確認
    if grep -q "supercopilot-main.js" "$VSCODE_SETTINGS"; then
      echo -e "   ${GREEN}✓ SuperCopilot設定は既に追加されています${NC}"
    else
      echo -e "   ${YELLOW}SuperCopilot設定を追加します...${NC}"

      # settings.jsonの末尾の閉じ括弧の前に設定を挿入
      # 空のファイルまたは内容がない場合、もしくは "{}" のみのファイル
      if [ ! -s "$VSCODE_SETTINGS" ] || [ "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" = "" ]; then
        echo "{" > "$VSCODE_SETTINGS"
        echo "  $CONFIG_ENTRY" >> "$VSCODE_SETTINGS"
        echo "}" >> "$VSCODE_SETTINGS"
        echo -e "   ${GREEN}✓ 新しいsettings.jsonファイルを作成しました${NC}"
      elif [ "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" = "{}" ]; then
        echo "{" > "$VSCODE_SETTINGS"
        echo "  $CONFIG_ENTRY" >> "$VSCODE_SETTINGS"
        echo "}" >> "$VSCODE_SETTINGS"
        echo -e "   ${GREEN}✓ settings.jsonに設定を追加しました${NC}"
      else
        # 末尾が}で終わるか確認
        if grep -q "}" "$VSCODE_SETTINGS"; then
          # 最後の閉じ括弧を見つけて、その前に設定を追加
          # Note: Using actual newline in sed replacement for BSD sed compatibility
          if sed '$ s/}/,\
  '"$CONFIG_ENTRY"'\
}/' "$VSCODE_SETTINGS" > "$VSCODE_SETTINGS.tmp"; then
            if mv "$VSCODE_SETTINGS.tmp" "$VSCODE_SETTINGS"; then
              echo -e "   ${GREEN}✓ settings.jsonに設定を追加しました${NC}"
            else
              echo -e "   ${RED}✗ 設定の追加に失敗しました（mvエラー）${NC}"
              rm -f "$VSCODE_SETTINGS.tmp"
              exit 1
            fi
          else
            echo -e "   ${RED}✗ 設定の追加に失敗しました（sedエラー）${NC}"
            rm -f "$VSCODE_SETTINGS.tmp"
            exit 1
          fi
        else
          # JSONが不完全な場合（} が見つからない）
          cp "$VSCODE_SETTINGS" "$VSCODE_SETTINGS.bak"
          echo -e "   ${YELLOW}警告: '}' が見つからないため VSCODE_SETTINGS ($VSCODE_SETTINGS) は不正な JSON の可能性があります。${NC}"
          echo -e "   ${YELLOW}バックアップを $VSCODE_SETTINGS.bak に作成しました。${NC}"
          
          # parse attempt (use jq if available)
          if command -v jq >/dev/null 2>&1 && jq empty "$VSCODE_SETTINGS" >/dev/null 2>&1; then
            # jq is available and parsing succeeded, which is unexpected if no } found,
            # but we still shouldn't append blindly if we can't find '}' with grep.
            echo -e "   ${RED}✗ ファイル末尾を特定できないため自動追記を中止しました。手動で以下の CONFIG_ENTRY を追加してください:${NC}"
            echo -e "   ${YELLOW}$CONFIG_ENTRY${NC}"
            exit 1
          else
            # parsing fails or jq unavailable
            echo -e "   ${RED}✗ ファイルのパースに失敗しました。VSCODE_SETTINGS を手動で修正し、以下の CONFIG_ENTRY を設定してください:${NC}"
            echo -e "   ${YELLOW}$CONFIG_ENTRY${NC}"
            exit 1
          fi
        fi
      fi
    fi
  else
    echo -e "   ${YELLOW}VSCode設定ファイルが見つかりません。新規作成します...${NC}"
    # 新しいsettings.jsonファイルを作成
    mkdir -p "$(dirname "$VSCODE_SETTINGS")"
    cat > "$VSCODE_SETTINGS" << EOF
{
  $CONFIG_ENTRY
}
EOF
    echo -e "   ${GREEN}✓ 新しいsettings.jsonファイルを作成しました${NC}"
  fi
fi

# 4. 完了メッセージ
echo -e "\n${GREEN}SuperCopilot Frameworkのセットアップが完了しました！${NC}"
echo -e "${BLUE}使用方法:${NC}"
echo -e "  - ファイルタイプと質問内容から自動的にペルソナが選択されます"
echo -e "  - 明示的にペルソナを指定: ${YELLOW}@architect システムの設計について教えて${NC}"
echo -e "  - コマンドで指定: ${YELLOW}design システムアーキテクチャ${NC}"
echo -e "\n${BLUE}詳細な使用方法はこちらをご覧ください:${NC}"
echo -e "${YELLOW}${REPO_ROOT}/vscode/settings/README.md${NC}"
