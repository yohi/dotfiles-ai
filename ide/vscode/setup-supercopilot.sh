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
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

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

ln -sf "$REPO_ROOT/ide/vscode/settings" "$HOME/.vscode/supercopilot"
if [ $? -eq 0 ]; then
  echo -e "   ${GREEN}✓ シンボリックリンクを作成しました${NC}"
  echo -e "   ${GREEN}  $REPO_ROOT/ide/vscode/settings -> $HOME/.vscode/supercopilot${NC}"
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

    # JSONC (コメント付きJSON) 対応: 一時的にコメントを除去したファイルを作成
    SANITIZED_SETTINGS=$(mktemp)
    if command -v node >/dev/null 2>&1; then
      # Node.js を使用してコメントと末尾のカンマを安全に除去 (文字列リテラルを考慮)
      node -e '
        const fs = require("fs");
        const content = fs.readFileSync(0, "utf8");
        let result = "";
        let i = 0;
        let inString = null;
        let inComment = null;
        
        while (i < content.length) {
          const char = content[i];
          const next = content[i + 1];
          
          if (inComment === "single") {
            if (char === "\n") inComment = null;
          } else if (inComment === "multi") {
            if (char === "*" && next === "/") { inComment = null; i++; }
          } else {
            if (inString) {
              if (char === "\\" ) { result += char + (next || ""); i++; }
              else if (char === inString) inString = null;
              result += char;
            } else {
              if (char === "/" && next === "/") { inComment = "single"; i++; }
              else if (char === "/" && next === "*") { inComment = "multi"; i++; }
              else if (char === "\"" || char === "\x27" || char === "\x60") { inString = char; result += char; }
              else result += char;
            }
          }
          i++;
        }
        // 末尾のカンマを除去
        result = result.replace(/,\s*([\]}])/g, "$1");
        process.stdout.write(result);
      ' < "$VSCODE_SETTINGS" > "$SANITIZED_SETTINGS" 2>/dev/null
    else
      # Node がない場合は perl で同様の処理を行う (文字列リテラルを考慮)
      perl -0777 -ne '
        $i = 0; $in_str = ""; $in_cmt = ""; $res = "";
        while ($i < length($_)) {
          $c = substr($_, $i, 1); $n = substr($_, $i+1, 1);
          if ($in_cmt eq "s") { if ($c eq "\n") { $in_cmt = ""; } }
          elsif ($in_cmt eq "m") { if ($c eq "*" && $n eq "/") { $in_cmt = ""; $i++; } }
          else {
            if ($in_str) {
              if ($c eq "\\\\") { $res .= $c . $n; $i++; }
              elsif ($c eq $in_str) { $in_str = ""; }
              $res .= $c;
            } else {
              if ($c eq "/" && $n eq "/") { $in_cmt = "s"; $i++; }
              elsif ($c eq "/" && $n eq "*") { $in_cmt = "m"; $i++; }
              elsif ($c =~ /["\x27\x60]/) { $in_str = $c; $res .= $c; }
              else { $res .= $c; }
            }
          }
          $i++;
        }
        $res =~ s/,\s*([\]}])/$1/g;
        print $res;
      ' "$VSCODE_SETTINGS" > "$SANITIZED_SETTINGS" 2>/dev/null
    fi

    # サニタイズ結果のバリデーション
    if [ ! -f "$SANITIZED_SETTINGS" ] || [ ! -s "$SANITIZED_SETTINGS" ] || ! jq empty "$SANITIZED_SETTINGS" >/dev/null 2>&1; then
      echo -e "   ${RED}✗ 設定ファイルの解析に失敗しました。JSONが不正か、サニタイズに失敗しました${NC}"
      rm -f "$SANITIZED_SETTINGS"
      exit 1
    fi

    # 設定が既にあるか確認 (サニタイズ済みのファイルを使用)
    if jq -e '.github.copilot.advanced.preProcessors.chat | has("path")' "$SANITIZED_SETTINGS" >/dev/null 2>&1 && \
       jq -r '.github.copilot.advanced.preProcessors.chat.path' "$SANITIZED_SETTINGS" | grep -q "supercopilot-main.js"; then
      echo -e "   ${GREEN}✓ SuperCopilot設定は既に追加されています${NC}"
      rm -f "$SANITIZED_SETTINGS"
    else
      echo -e "   ${YELLOW}SuperCopilot設定を追加します...${NC}"

      # 既存ファイルのバックアップ作成
      cp "$VSCODE_SETTINGS" "${VSCODE_SETTINGS}.backup"

      # VSCODE_SETTINGSが空、空白のみ、または空オブジェクトかを判定して初期化する
      # (サニタイズ済みのファイルで判定)
      if [ ! -s "$SANITIZED_SETTINGS" ] || [ -z "$(cat "$SANITIZED_SETTINGS" | tr -d '[:space:]')" ] || [ "$(cat "$SANITIZED_SETTINGS" | tr -d '[:space:]')" = "{}" ] || jq -e '. == {}' "$SANITIZED_SETTINGS" >/dev/null 2>&1; then
        echo "{}" > "$VSCODE_SETTINGS"
        cp "$VSCODE_SETTINGS" "$SANITIZED_SETTINGS"
      fi

      # 既存のsettings.jsonと新しい設定をマージ (サニタイズ済みのファイルを使用してマージ結果を生成)
      if jq --argjson config "$CONFIG_JSON" '. * $config' "$SANITIZED_SETTINGS" > "${VSCODE_SETTINGS}.tmp"; then
        mv "${VSCODE_SETTINGS}.tmp" "$VSCODE_SETTINGS"
        rm -f "$SANITIZED_SETTINGS"

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

      # Backup settings.json
      [ -f "$VSCODE_SETTINGS" ] && cp "$VSCODE_SETTINGS" "$VSCODE_SETTINGS.bak"

      # settings.jsonの末尾の閉じ括弧の前に設定を挿入
      # 空のファイルまたは内容がない場合、もしくは "{}" のみのファイル
      if [ ! -s "$VSCODE_SETTINGS" ] || [ "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" = "" ]; then
        if { echo "{"; echo "  $CONFIG_ENTRY"; echo "}"; } > "$VSCODE_SETTINGS.tmp" && mv "$VSCODE_SETTINGS.tmp" "$VSCODE_SETTINGS"; then
          rm -f "$VSCODE_SETTINGS.bak"
          echo -e "   ${GREEN}✓ 新しいsettings.jsonファイルを作成しました${NC}"
        else
          echo -e "   ${RED}✗ 設定の追加に失敗しました${NC}"
          [ -f "$VSCODE_SETTINGS.bak" ] && mv "$VSCODE_SETTINGS.bak" "$VSCODE_SETTINGS"
          rm -f "$VSCODE_SETTINGS.tmp"
          exit 1
        fi
      elif [ "$(cat "$VSCODE_SETTINGS" | tr -d '[:space:]')" = "{}" ]; then
        if { echo "{"; echo "  $CONFIG_ENTRY"; echo "}"; } > "$VSCODE_SETTINGS.tmp" && mv "$VSCODE_SETTINGS.tmp" "$VSCODE_SETTINGS"; then
          rm -f "$VSCODE_SETTINGS.bak"
          echo -e "   ${GREEN}✓ settings.jsonに設定を追加しました${NC}"
        else
          echo -e "   ${RED}✗ 設定の追加に失敗しました${NC}"
          [ -f "$VSCODE_SETTINGS.bak" ] && mv "$VSCODE_SETTINGS.bak" "$VSCODE_SETTINGS"
          rm -f "$VSCODE_SETTINGS.tmp"
          exit 1
        fi
      else
        # 末尾が}で終わるか確認
        if grep -q "}" "$VSCODE_SETTINGS"; then
          # 最後の閉じ括弧を見つけて、その前に設定を追加
          # Note: Using actual newline in sed replacement for BSD sed compatibility
          SAFE_CONFIG_ENTRY=$(echo "$CONFIG_ENTRY" | sed 's/&/\\&/g; s/|/\\|/g')
          if sed '$ s|}|,\
  '"$SAFE_CONFIG_ENTRY"'\
}|' "$VSCODE_SETTINGS" > "$VSCODE_SETTINGS.tmp"; then
            if mv "$VSCODE_SETTINGS.tmp" "$VSCODE_SETTINGS"; then
              rm -f "$VSCODE_SETTINGS.bak"
              echo -e "   ${GREEN}✓ settings.jsonに設定を追加しました${NC}"
            else
              echo -e "   ${RED}✗ 設定の追加に失敗しました（mvエラー）${NC}"
              [ -f "$VSCODE_SETTINGS.bak" ] && mv "$VSCODE_SETTINGS.bak" "$VSCODE_SETTINGS"
              rm -f "$VSCODE_SETTINGS.tmp"
              exit 1
            fi
          else
            echo -e "   ${RED}✗ 設定の追加に失敗しました（sedエラー）${NC}"
            [ -f "$VSCODE_SETTINGS.bak" ] && mv "$VSCODE_SETTINGS.bak" "$VSCODE_SETTINGS"
            rm -f "$VSCODE_SETTINGS.tmp"
            exit 1
          fi
        else
          # JSONが不完全な場合（} が見つからない）
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
echo -e "${YELLOW}${REPO_ROOT}/ide/vscode/settings/README.md${NC}"
