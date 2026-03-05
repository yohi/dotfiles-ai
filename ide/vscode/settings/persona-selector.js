/**
 * SuperCopilot Framework - ペルソナ自動選択システム
 *
 * VSCode/GitHub Copilot向けのペルソナ自動選択機能
 */

const superCopilot = require('./supercopilot');

/**
 * ペルソナ自動選択クラス
 */
class PersonaSelector {
  constructor(config = superCopilot) {
    this.config = config;
    this.currentPersona = null;
    this.currentVariant = null;
  }

  /**
   * ファイルパターンマッチングのヘルパー関数
   * @param {string} filePath - ファイルパス
   * @param {string} pattern - マッチパターン
   * @returns {boolean} マッチするかどうか
   */
  matchesPattern(filePath, pattern) {
    if (pattern.endsWith('/')) {
      // ディレクトリパターン
      return filePath.includes(pattern);
    } else if (pattern.startsWith('*.')) {
      // 拡張子パターン
      const extension = pattern.replace('*.', '');
      return filePath.endsWith(`.${extension}`);
    } else {
      // 完全一致
      return filePath.includes(pattern);
    }
  }

  /**
   * 正規表現エスケープ
   * @param {string} str - エスケープ対象の文字列
   * @returns {string} エスケープ済み文字列
   */
  escapeRegExp(str) {
    if (!str) return '';
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /**
   * ファイルパスに基づいてペルソナを選択
   * @param {string} filePath - ファイルパス
   * @returns {Object|null} 選択されたペルソナ
   */
  selectPersonaByFile(filePath) {
    if (!filePath) return null;

    // 各ペルソナのファイルパターンを検査
    for (const [personaKey, persona] of Object.entries(this.config.personas)) {
      // パターンが一致するか確認
      const matches = persona.filePatterns.some(pattern =>
        this.matchesPattern(filePath, pattern)
      );

      if (matches) {
        // バリアントチェック
        if (persona.variants) {
          for (const [variantKey, variant] of Object.entries(persona.variants)) {
            const variantMatches = variant.filePatterns.some(pattern =>
              this.matchesPattern(filePath, pattern)
            );

            if (variantMatches) {
              return {
                ...persona,
                variantKey,
                variant
              };
            }
          }
        }

        return persona;
      }
    }

    return null;
  }

  /**
   * ユーザーの質問内容からペルソナを選択
   * @param {string} queryText - ユーザーの質問またはリクエスト
   * @returns {Object} 選択されたペルソナ情報
   */
  selectPersonaByQuery(queryText) {
    if (!queryText) return null;

    // 手動指定の優先確認（例: @architect として...）
    const manualMatch = queryText.match(/@([a-z]+)(\s+\(([A-Za-z]+)\))?/);
    if (manualMatch) {
      const personaKey = manualMatch[1];
      const variantName = manualMatch[3]; // 例: @developer (Frontend) の "Frontend" 部分

      if (this.config.personas[personaKey]) {
        const selectedPersona = this.config.personas[personaKey];

        // バリアントが指定されているか確認
        if (variantName && selectedPersona.variants && selectedPersona.variants[variantName]) {
          return {
            ...selectedPersona,
            variantKey: variantName,
            variant: selectedPersona.variants[variantName]
          };
        }

        return selectedPersona;
      }
    }

    // コマンド指定の確認
    for (const [cmdKey, cmd] of Object.entries(this.config.commands)) {
      const commandRegex = new RegExp(`\\b${cmdKey}\\b`, 'i');
      if (commandRegex.test(queryText) && cmd.defaultPersona) {
        return this.config.personas[cmd.defaultPersona];
      }
    }

    // キーワードパターンによる自動選択
    const matchScores = {};
    const variantScores = {}; // 分離されたバリアントスコア

    for (const [personaKey, persona] of Object.entries(this.config.personas)) {
      matchScores[personaKey] = 0;

      // 基本キーワードマッチング
      persona.keywordPatterns.forEach(keyword => {
        if (!keyword) return;
        try {
          const keywordRegex = new RegExp(`\\b${this.escapeRegExp(keyword)}\\b`, 'i');
          if (keywordRegex.test(queryText)) {
            matchScores[personaKey] += 1;
          }
        } catch (e) { }
      });

      // バリアントのキーワードもチェック
      if (persona.variants) {
        for (const [variantKey, variant] of Object.entries(persona.variants)) {
          let variantScore = 0;

          variant.keywordPatterns.forEach(keyword => {
            if (!keyword) return;
            try {
              const keywordRegex = new RegExp(`\\b${this.escapeRegExp(keyword)}\\b`, 'i');
              if (keywordRegex.test(queryText)) {
                variantScore += 1;
              }
            } catch (e) { }
          });

          // バリアントスコアが高い場合は記録
          if (variantScore > 0) {
            if (!variantScores[personaKey]) variantScores[personaKey] = {};
            variantScores[personaKey][variantKey] = variantScore;
          }
        }
      }
    }

    // 最高スコアのペルソナを特定
    let highestScore = 0;
    let selectedPersonaKey = 'analyst'; // デフォルトはアナリスト

    for (const [personaKey, score] of Object.entries(matchScores)) {
      if (score > highestScore) {
        highestScore = score;
        selectedPersonaKey = personaKey;
      }
    }

    const selectedPersona = this.config.personas[selectedPersonaKey];

    // バリアントの中で最高スコアがあれば選択
    if (variantScores[selectedPersonaKey]) {
      let highestVariantScore = 0;
      let selectedVariantKey = null;

      for (const [variantKey, score] of Object.entries(variantScores[selectedPersonaKey])) {
        if (score > highestVariantScore) {
          highestVariantScore = score;
          selectedVariantKey = variantKey;
        }
      }

      if (selectedVariantKey) {
        return {
          ...selectedPersona,
          variantKey: selectedVariantKey,
          variant: selectedPersona.variants[selectedVariantKey]
        };
      }
    }

    return selectedPersona;
  }

  /**
   * ファイルとクエリの両方を考慮して最適なペルソナを選択
   * @param {string} filePath - 現在開いているファイルのパス
   * @param {string} queryText - ユーザーの質問またはリクエスト
   * @returns {Object} 選択されたペルソナと選択理由
   */
  selectOptimalPersona(filePath, queryText) {
    // ユーザーの質問から手動指定のペルソナを優先
    const queryPersona = this.selectPersonaByQuery(queryText);
    if (queryPersona && queryText.includes(`@${queryPersona.name}`)) {
      return {
        persona: queryPersona,
        reason: '明示的なペルソナ指定'
      };
    }

    // コマンド指定がある場合
    for (const [cmdKey, cmd] of Object.entries(this.config.commands)) {
      const commandRegex = new RegExp(`\\b${cmdKey}\\b`, 'i');
      if (queryText && commandRegex.test(queryText) && cmd.defaultPersona) {
        return {
          persona: this.config.personas[cmd.defaultPersona],
          reason: `"${cmdKey}"コマンドに基づく選択`
        };
      }
    }

    // ファイルタイプによるペルソナ選択
    const filePersona = this.selectPersonaByFile(filePath);
    const queryPersonaScore = this._calculateQueryPersonaScore(queryText);

    // クエリスコアがファイルベースの選択より高い場合はクエリベースの選択を優先
    if (queryPersonaScore.score > 1 && queryPersona) {
      return {
        persona: queryPersona,
        reason: `質問内容"${queryPersonaScore.matchedKeywords.join('", "')}"に基づく選択`
      };
    }

    // それ以外の場合はファイルタイプに基づく選択
    if (filePersona) {
      return {
        persona: filePersona,
        reason: `ファイルタイプ${filePath ? `"${filePath}"` : ''}に基づく選択`
      };
    }

    // デフォルトはアナリスト
    return {
      persona: this.config.personas.analyst,
      reason: 'デフォルト選択（特定のコンテキストなし）'
    };
  }

  /**
   * クエリテキストに基づくペルソナスコアを計算
   * @private
   * @param {string} queryText - ユーザーの質問またはリクエスト
   * @returns {Object} スコア情報
   */
  _calculateQueryPersonaScore(queryText) {
    if (!queryText) return { score: 0, matchedKeywords: [] };

    const matchScores = {};
    const matchedKeywords = {};

    for (const [personaKey, persona] of Object.entries(this.config.personas)) {
      matchScores[personaKey] = 0;
      matchedKeywords[personaKey] = [];

      // 基本キーワードマッチング
      persona.keywordPatterns.forEach(keyword => {
        if (!keyword) return;
        try {
          const keywordRegex = new RegExp(`\\b${this.escapeRegExp(keyword)}\\b`, 'i');
          if (keywordRegex.test(queryText)) {
            matchScores[personaKey] += 1;
            matchedKeywords[personaKey].push(keyword);
          }
        } catch (e) { }
      });

      // バリアントのキーワードもチェック
      if (persona.variants) {
        for (const [variantKey, variant] of Object.entries(persona.variants)) {
          variant.keywordPatterns.forEach(keyword => {
            if (!keyword) return;
            try {
              const keywordRegex = new RegExp(`\\b${this.escapeRegExp(keyword)}\\b`, 'i');
              if (keywordRegex.test(queryText)) {
                matchScores[personaKey] += 1;
                matchedKeywords[personaKey].push(keyword);
              }
            } catch (e) { }
          });
        }
      }
    }

    // 最高スコアのペルソナを特定
    let highestScore = 0;
    let selectedPersonaKey = null;

    for (const [personaKey, score] of Object.entries(matchScores)) {
      if (score > highestScore) {
        highestScore = score;
        selectedPersonaKey = personaKey;
      }
    }

    return {
      score: highestScore,
      matchedKeywords: selectedPersonaKey ? matchedKeywords[selectedPersonaKey] : []
    };
  }

  /**
   * 選択されたペルソナに基づいてプロンプト接頭辞を生成
   * @param {Object} personaInfo - selectOptimalPersona()で得られたペルソナ情報
   * @returns {string} Copilotに送信するプロンプト接頭辞
   */
  generatePersonaPrompt(personaInfo) {
    if (!personaInfo || !personaInfo.persona) return '';

    const { persona, reason } = personaInfo;
    let personaName = persona.displayName;
    let promptText = '';

    // バリアントがある場合はバリアント名も含める
    if (persona.variantKey) {
      personaName = `${personaName} (${persona.variantKey})`;
    }

    // プロンプトを構築
    promptText = `🎯 **@${persona.name}${persona.variantKey ? ` (${persona.variantKey})` : ''} として回答します**\n\n`;
    promptText += `[選択理由: ${reason}]\n\n---\n\n`;

    return promptText;
  }
}

// エクスポート設定
if (typeof module !== 'undefined') {
  module.exports = {
    PersonaSelector
  };
}

// ブラウザ環境で利用する場合
if (typeof window !== 'undefined') {
  window.PersonaSelector = PersonaSelector;
}
