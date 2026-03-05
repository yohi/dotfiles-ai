/**
 * SuperCopilot Framework - コマンド処理システム
 *
 * VSCode/GitHub Copilot向けのコマンド処理機能
 */

const superCopilot = require('./supercopilot');
const { PersonaSelector } = require('./persona-selector');

/**
 * コマンド処理クラス
 */
class CommandsHandler {
  constructor(config = superCopilot) {
    this.config = config;
    this.personaSelector = new PersonaSelector(config);
  }

  /**
   * テキスト内のコマンドを検出
   * @param {string} text - ユーザー入力テキスト
   * @returns {Object|null} 検出されたコマンド情報、または null
   */
  detectCommand(text) {
    if (!text) return null;

    // コマンドの検出（単語として存在するか確認）
    for (const [cmdKey, cmdInfo] of Object.entries(this.config.commands)) {
      const commandRegex = new RegExp(`\\b${cmdKey}\\b`, 'i');
      if (commandRegex.test(text)) {
        return {
          name: cmdKey,
          ...cmdInfo
        };
      }
    }

    return null;
  }

  /**
   * コマンドに対応するプロンプト接頭辞を生成
   * @param {string} commandName - コマンド名
   * @param {string} queryText - ユーザー入力全体
   * @returns {string} プロンプト接頭辞
   */
  generateCommandPrompt(commandName, queryText) {
    if (!commandName || !this.config.commands[commandName]) {
      return '';
    }

    const command = this.config.commands[commandName];
    const defaultPersonaKey = command.defaultPersona || 'developer';
    const persona = this.config.personas[defaultPersonaKey];

    // コマンドに対応するペルソナの特定
    const personaInfo = {
      persona: persona,
      reason: `"${commandName}"コマンドに基づく選択`
    };

    // ペルソナプロンプトを生成
    const personaPrompt = this.personaSelector.generatePersonaPrompt(personaInfo);

    // コマンド固有のプロンプト接頭辞を追加
    let commandPrompt = `${personaPrompt}`;

    // コマンド名に基づいて動作を調整
    switch (commandName) {
      case 'analyze':
        commandPrompt += `コード分析を行います。以下の点に注目して評価します：\n\n`;
        commandPrompt += `- コード品質\n`;
        commandPrompt += `- パフォーマンス\n`;
        commandPrompt += `- セキュリティ\n`;
        commandPrompt += `- 保守性\n`;
        commandPrompt += `- リファクタリング推奨点\n\n`;
        break;

      case 'explain':
        commandPrompt += `コードの動作説明を行います：\n\n`;
        commandPrompt += `- アルゴリズムの解説\n`;
        commandPrompt += `- 処理フロー\n`;
        commandPrompt += `- 重要な箇所の詳細\n\n`;
        break;

      case 'implement':
        commandPrompt += `機能実装を行います：\n\n`;
        commandPrompt += `- 実装方針\n`;
        commandPrompt += `- コード例\n`;
        commandPrompt += `- テスト方針\n\n`;
        break;

      case 'design':
        commandPrompt += `設計を行います：\n\n`;
        commandPrompt += `- アーキテクチャ概要\n`;
        commandPrompt += `- コンポーネント構成\n`;
        commandPrompt += `- データフロー\n`;
        commandPrompt += `- 技術選定理由\n\n`;
        break;

      // 他のコマンドも同様に定義可能

      default:
        // デフォルトの場合は何も追加しない
        break;
    }

    return commandPrompt;
  }

  /**
   * テキスト内のコマンドを処理し、適切なプロンプトを生成
   * @param {string} text - ユーザー入力テキスト
   * @param {string} filePath - 現在開いているファイルパス
   * @returns {string} 処理後のプロンプト
   */
  processText(text, filePath = '') {
    // コマンドの検出
    const command = this.detectCommand(text);

    if (command) {
      // コマンドが検出された場合、そのコマンド用のプロンプトを生成
      return this.generateCommandPrompt(command.name, text);
    } else {
      // コマンドがない場合は、ファイルとテキストからペルソナを自動選択
      const personaInfo = this.personaSelector.selectOptimalPersona(filePath, text);
      return this.personaSelector.generatePersonaPrompt(personaInfo);
    }
  }

  /**
   * すべてのコマンド一覧を取得
   * @returns {Array} コマンド一覧
   */
  getCommandsList() {
    return Object.entries(this.config.commands).map(([key, info]) => ({
      name: key,
      ...info
    }));
  }

  /**
   * コマンド使用方法のヘルプテキストを生成
   * @returns {string} ヘルプテキスト
   */
  generateHelpText() {
    let helpText = `# SuperCopilot コマンド一覧\n\n`;

    // 設定からカテゴリを取得
    const categories = this.config.commandCategories || {};

    // カテゴリごとに出力
    for (const [category, commands] of Object.entries(categories)) {
      helpText += `## ${category}コマンド\n\n`;

      for (const cmdName of commands) {
        if (this.config.commands[cmdName]) {
          const cmd = this.config.commands[cmdName];
          helpText += `- **${cmdName}**: ${cmd.description}\n`;
        }
      }

      helpText += '\n';
    }

    return helpText;
  }
}

// エクスポート設定
if (typeof module !== 'undefined') {
  module.exports = {
    CommandsHandler
  };
}

// ブラウザ環境で利用する場合
if (typeof window !== 'undefined') {
  window.CommandsHandler = CommandsHandler;
}
