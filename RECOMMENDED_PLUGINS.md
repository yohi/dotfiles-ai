# OpenCode プラグイン & 可視化戦略レポート

**Last verified: 2026-06-16**

本レポートは、`oh-my-openagent` v4.10.0 を中心とした現在の高度な開発環境を補完し、サブエージェントの動きを「透明化」しつつ「効率を最大化」するためのガイドです。

---

## 1. サブエージェントの可視化戦略 (推奨)

外部ダッシュボードは現在メンテナンスが限定的なため、**v4標準の oh-my-openagent 監視手法**を採用することを強く推奨します。

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

## 2. 推奨機能拡張プラグイン (URL・互換性情報付)

認証（Auth）系を除外し、現在の「長期自律・マルチエージェント」構成に不足している機能を補います。

### **① コンテキストの最適化**
*   **プラグイン名**: **opencode-dynamic-context-pruning**
*   **役割**: 古いツール出力を整理し、トークンを節約します。
*   **互換性**: `oh-my-openagent` v4.10.0 以上に対応 (アクティブにメンテナンス中)
*   **メリット**: 長時間セッションでも推論精度が落ちない「賢さの維持」に貢献します。
*   **URL**: [https://github.com/Opencode-DCP/opencode-dynamic-context-pruning](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning)

### **② 型安全性の向上**
*   **プラグイン名**: **opencode-type-inject**
*   **役割**: ファイル読み取り時にTypeScript等の型定義を自動注入します。
*   **互換性**: `oh-my-openagent` v4.10.0 以上に対応 (アクティブにメンテナンス中)
*   **メリット**: 実装エージェントが「インポート先の型」を暗黙的に理解し、コード品質が向上します。
*   **URL**: [https://github.com/nick-vi/opencode-type-inject](https://github.com/nick-vi/opencode-type-inject)

### **③ 高速編集と一括検索**
*   **プラグイン名**: **opencode-morph-plugin**
*   **役割**: Morph技術による高速な一括修正とSemantic Search。
*   **互換性**: `oh-my-openagent` v4.10.0 以上に対応 (アクティブにメンテナンス中)
*   **メリット**: 大規模なdotfilesのリファクタリング待ち時間をほぼゼロにします。
*   **URL**: [https://github.com/morphllm/opencode-morph-plugin](https://github.com/morphllm/opencode-morph-plugin)

### **④ プライバシーとセキュリティ**
*   **プラグイン名**: **opencode-vibeguard**
*   **役割**: LLMへの送信前に機密情報（APIキー等）を自動置換。
*   **互換性**: `oh-my-openagent` v4.10.0 以上に対応 (アクティブにメンテナンス中)
*   **メリット**: 外部モデルを使いつつ、ローカルの機密を安全に保護します。
*   **URL**: [https://github.com/inkdust2021/opencode-vibeguard](https://github.com/inkdust2021/opencode-vibeguard)

### **⑤ インタラクティブ操作の解放**
*   **プラグイン名**: **opencode-pty**
*   **役割**: エージェントが対話型CLIツールをバックグラウンドで操作可能に。
*   **互換性**: `oh-my-openagent` v4.10.0 以上に対応 (コア機能として安定稼働中)
*   **URL**: [https://opencode.ai/docs/ecosystem/](https://opencode.ai/docs/ecosystem/) (Ecosystemドキュメントページ)

---

## 3. 導入の優先順位

1.  **[監視]** `opencode.jsonc` で **Team Mode** と **Tmux** を有効化（即座に可視化が可能）。
2.  **[知能]** **`Type Inject`** を導入して型安全性を強化。
3.  **[節約]** **`Dynamic Context Pruning`** で長期セッションの安定性を確保。

以上の構成により、現在お使いの `oh-my-openagent` のポテンシャルを最大限に引き出すことが可能です。

---

## 4. 非推奨・廃止時の対応

万が一、上記の推奨プラグインが非推奨または廃止された場合、以下の代替手段またはフォールバック手順を検討してください。

*   **opencode-dynamic-context-pruning (DCP) の非推奨化時**:
    - `oh-my-openagent` に組み込まれている標準の `context_compaction` 機能を有効化し、上限トークン数制限を調整することで代替します。
*   **opencode-type-inject の非推奨化時**:
    - 手動による型シグネチャのLSP検索や、型定義を記述した `.d.ts` ファイルをエージェントへの指示プロンプト経由で直接読み込ませる方法へ切り替えます。
*   **opencode-morph-plugin の非推奨化時**:
    - 標準の `search_grep` と `replace_file_content` の組み合わせによる順次適用にフォールバックします。
*   **opencode-vibeguard の非推奨化時**:
    - ローカル環境の `.env` や秘密情報を分離し、CI/CDなどの自動ステージング以外では外部モデルの利用を控え、完全にローカルなモデル（Ollama経由など）での実行へシフトします。
*   **opencode-pty の非推奨化時**:
    - バックグラウンド実行が必要な開発サーバー等は、エージェント実行前にホスト側のシェル上で事前に起動しておく運用（事前起動アプローチ）へフォールバックします。
