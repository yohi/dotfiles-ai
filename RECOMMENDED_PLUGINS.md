# OpenCode プラグイン & 可視化戦略レポート (2026年最新版)

本レポートは、`oh-my-openagent` v4.10.0 を中心とした現在の高度な開発環境を補完し、サブエージェントの動きを「透明化」しつつ「効率を最大化」するためのガイドです。

---

## 1. サブエージェントの可視化戦略 (推奨)

外部ダッシュボードは現在メンテナンスが限定的なため、**v4標準の監視手法**を採用することを強く推奨します。

### **Team Mode (内蔵 Tmux 統合監視)**
*   **概要**: 実行時に Tmux のペインを自動分割し、複数のエージェントが並列で動く様子をリアルタイムに表示します。
*   **メリット**:
    *   **リアルタイム性**: `Sisyphus`（司令塔）の指示が各サブエージェント（`Hephaestus`等）に伝わり、それぞれの思考ログが流れる様子を直接目視できます。
    *   **環境の一貫性**: 外部ツールを介さず、開発ターミナル内で完結します。
*   **設定例 (`opencode.jsonc`)**:
    ```jsonc
    {
      "team_mode": { "enabled": true, "auto_sync": true },
      "tmux": { "enabled": true, "layout": "main-vertical" }
    }
    ```

---

## 2. 推奨機能拡張プラグイン (URL付)

認証（Auth）系を除外し、現在の「長期自律・マルチエージェント」構成に不足している機能を補います。

### **① コンテキストの最適化**
*   **プラグイン名**: **opencode-dynamic-context-pruning**
*   **役割**: 古いツール出力を整理し、トークンを節約します。
*   **メリット**: 長時間セッションでも推論精度が落ちない「賢さの維持」に貢献します。
*   **URL**: [https://github.com/Opencode-DCP/opencode-dynamic-context-pruning](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning)

### **② 型安全性の向上**
*   **プラグイン名**: **opencode-type-inject**
*   **役割**: ファイル読み取り時にTypeScript等の型定義を自動注入します。
*   **メリット**: 実装エージェントが「インポート先の型」を暗黙的に理解し、コード品質が向上します。
*   **URL**: [https://github.com/nick-vi/opencode-type-inject](https://github.com/nick-vi/opencode-type-inject)

### **③ 高速編集と一括検索**
*   **プラグイン名**: **opencode-morph-plugin**
*   **役割**: Morph技術による高速な一括修正とSemantic Search。
*   **メリット**: 大規模なdotfilesのリファクタリング待ち時間をほぼゼロにします。
*   **URL**: [https://github.com/morphllm/opencode-morph-plugin](https://github.com/morphllm/opencode-morph-plugin)

### **④ プライバシーとセキュリティ**
*   **プラグイン名**: **opencode-vibeguard**
*   **役割**: LLMへの送信前に機密情報（APIキー等）を自動置換。
*   **メリット**: 外部モデルを使いつつ、ローカルの機密を安全に保護します。
*   **URL**: [https://github.com/inkdust2021/opencode-vibeguard](https://github.com/inkdust2021/opencode-vibeguard)

### **⑤ インタラクティブ操作の解放**
*   **プラグイン名**: **opencode-pty**
*   **役割**: エージェントが対話型CLIツールをバックグラウンドで操作可能に。
*   **URL**: [https://opencode.ai/docs/ja/ecosystem/](https://opencode.ai/docs/ja/ecosystem/) (Ecosystem内)

---

## 3. 導入の優先順位

1.  **[監視]** `opencode.jsonc` で **Team Mode** と **Tmux** を有効化（即座に可視化が可能）。
2.  **[知能]** **`Type Inject`** を導入して型安全性を強化。
3.  **[節約]** **`Dynamic Context Pruning`** で長期セッションの安定性を確保。

以上の構成により、現在お使いの `oh-my-openagent` のポテンシャルを最大限に引き出すことが可能です。
