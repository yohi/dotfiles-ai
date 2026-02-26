# 冪等性管理と共通ユーティリティのマクロ定義 (Injected by dotfiles-core)

MARKER_DIR := $(HOME)/.make_markers

# マーカーの作成: $(call create_marker,name,version)
define create_marker
	@mkdir -p "$(MARKER_DIR)"
	@echo "$(2)" > "$(MARKER_DIR)/$(1).version"
	@touch "$(MARKER_DIR)/$(1)"
endef

# マーカーの存在確認: $(call check_marker,name)
define check_marker
	test -f "$(MARKER_DIR)/$(1)"
endef

# コマンドの存在確認: $(call check_command,command)
define check_command
	command -v $(1) >/dev/null 2>&1
endef

# スキップメッセージの表示: $(call IDEMPOTENCY_SKIP_MSG,name)
define IDEMPOTENCY_SKIP_MSG
@echo "✅ $(1) は既に完了しているためスキップします。"
endef

# 共通ターゲット: Node.jsの確認
ifeq ($(REQUIRE_NODEJS),1)
.PHONY: check-nodejs
check-nodejs:
	@command -v node >/dev/null 2>&1 || { echo "❌ Node.js がインストールされていません"; exit 1; }
endif
