# oh-my-opencode.jsonc テンプレート更新レポート

**作成日**: 2026-04-24
**対象ファイル**: `components/dotfiles-ai/opencode/oh-my-opencode.jsonc.template`

## 1. はじめに

### 目的
3リポジトリ (`oh-my-openagent`, `superpowers`, `justice`) を跨ぐ日常運用に適したベストプラクティス構成へ	template を更新する。

### 優先軸
- **安定性重視**: モデル可用性と挙動の一貫性を最優先

## 2. 調査概要

### 調査したモデル
| モデル | -provider | 状態 |
|--------|-----------|------|
| gpt-5.5 | OpenAI | API 未公開 (ChatGPT/Codex のみ) |
| gpt-5.4 | OpenAI | ✅ API 利用可能 |
| gpt-5.4-pro | OpenAI | ✅ API 利用可能 |
| gpt-5.4-mini | OpenAI | ✅ API 利用可能 |
| big-pickle | OpenCode独自 | alias、不明 |
| minimax-m2.5-free | MiniMax | ✅ API 利用可能 |
| ling-2.6-flash-free | Azure | ✅ |
| hy3-preview-free | Hyper | ✅ |
| nemotron-3-super-free | NVIDIA | ✅ |
| kimi-k2.5 | MoonshotAI | ✅ NVIDIA 経由 |
| minimax-m2.7 | MiniMax | ✅ |

## 3. 修正内容

### 3.1 ファイル構造の修正
- 破損していた 重複ブロック (219-244行目) を削除
- 末尾の 余分な `}` を削除

### 3.2 エージェントのモデル修正

| エージェント | 旧モデル | 新モデル | 理由 |
|------------|---------|---------|------|
| `atlas` | `gpt-5.4-mini` | `kimi-k2.5` | 環境整合維持の安定性 |
| `oracle` | `gpt-5.5` | `gpt-5.4` | API 未公開のため |
| `librarian` | (既存) | - | 言及を削除 |

### 3.3 カテゴリのモデル修正

| カテゴリ | 旧モデル | 新モデル | 理由 |
|---------|---------|---------|------|
| `deep` | `big-pickle` | `gpt-5.4` | alias 不明 |
| `quick` | `nemotron-3-super-free` | `gpt-5.4-mini` | 本来の軽量用途 |
| `writing` | `minimax-m2.5-free` | `gemini-3-flash` | 文書最適化 |
| `unspecified-low` | `qwen3.6-plus-free` | `gpt-5.4-mini` | 統一感 |

### 3.4 美容上の修正
- 82行目のコメント 先頭に不足していた `//` を追加
- インデントを統一

## 4. 推奨構成 (最終)

### 4.1 オーケストレーション層
```json
{
  "sisyphus": "nvidia/moonshotai/kimi-k2.5",
  "prometheus": "nvidia/moonshotai/kimi-k2.5",
  "atlas": "nvidia/moonshotai/kimi-k2.5"
}
```

### 4.2 実装層
```json
{
  "hephaestus": "openai/gpt-5.4",
  "multimodal-looker": "nvidia/moonshotai/kimi-k2.5"
}
```

### 4.3 援助層
```json
{
  "explore": "nvidia/minimaxai/minimax-m2.7",
  "librarian": "openai/gpt-5.4-mini",
  "oracle": "openai/gpt-5.4"
}
```

### 4.4 カテゴリ
```json
{
  "ultrabrain": "openai/gpt-5.4",
  "deep": "openai/gpt-5.4",
  "quick": "openai/gpt-5.4-mini",
  "writing": "google/gemini-3-flash",
  "unspecified-low": "openai/gpt-5.4-mini"
}
```

## 5. 解決された課題

- ✅ gpt-5.4 API 未公開リスクを排除 (gpt-5.5から修正)
- ✅ big-pickle alias の不安定性を排除
- ✅ 無料モデルの意味の揺らぎを解消 (quick の低遅延用途へ)
- ✅ 3リポジトリを跨ぐワークフローでの一貫性を確保

## 6. 今後の展望

- `gpt-5.4-pro` や新モデルの追加検証
- `superpowers` との統合による計画/検証工程の优化
- `justice` の plan-task ブリッジとの親和性確認