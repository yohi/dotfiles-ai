help: ## 利用可能なターゲットを一覧表示します
	@echo "🎯 使用可能なコマンド:"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) _mk/*.mk | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}'
