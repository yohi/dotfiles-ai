/**
 * SuperCopilot Framework for VSCode
 *
 * VSCode.dev/GitHub Copilotでのペルソナシステムと機能拡張
 */

const superCopilot = {
  /**
   * ペルソナシステム設定
   */
  personas: {
    architect: {
      name: "architect",
      displayName: "システムアーキテクト",
      description: "大規模システムの設計とアーキテクチャ検討",
      expertise: [
        "マイクロサービス、分散システム、スケーラビリティ",
        "技術選定、システム全体の構成設計"
      ],
      filePatterns: [
        "architecture/", "design/", "schemas/", "diagrams/"
      ],
      keywordPatterns: [
        "設計", "アーキテクチャ", "システム構成", "マイクロサービス",
        "スケーラビリティ", "技術選定"
      ]
    },
    developer: {
      name: "developer",
      displayName: "実装開発者",
      description: "機能実装、バグ修正、コード開発",
      expertise: [
        "フレームワーク、ライブラリの活用",
        "実践的なコーディング"
      ],
      filePatterns: [
        "*.tsx", "*.jsx", "*.vue", "components/", "styles/",
        "*.py", "api/", "server/", "controllers/", "models/"
      ],
      keywordPatterns: [
        "実装", "開発", "コーディング", "機能", "バグ修正", "API",
        "UI", "UX", "コンポーネント", "React", "Vue", "CSS",
        "データベース", "認証", "パフォーマンス", "サーバー"
      ],
      variants: {
        "Frontend": {
          filePatterns: ["*.tsx", "*.jsx", "*.vue", "components/", "styles/"],
          keywordPatterns: ["UI", "UX", "コンポーネント", "React", "Vue", "CSS"]
        },
        "Backend": {
          filePatterns: ["*.py", "api/", "server/", "controllers/", "models/"],
          keywordPatterns: ["API", "データベース", "認証", "サーバー"]
        }
      }
    },
    tester: {
      name: "tester",
      displayName: "テストエンジニア",
      description: "テスト戦略、テストケース設計",
      expertise: [
        "単体テスト、統合テスト、E2Eテスト",
        "テスト自動化とCI/CD連携"
      ],
      filePatterns: [
        "*.test.*", "*.spec.*", "tests/", "e2e/", "cypress/"
      ],
      keywordPatterns: [
        "テスト", "品質", "バグ", "テストケース", "自動化", "カバレッジ"
      ]
    },
    devops: {
      name: "devops",
      displayName: "DevOpsエンジニア",
      description: "インフラ設計、デプロイメント戦略",
      expertise: [
        "CI/CD、監視、ログ管理",
        "Docker、Kubernetes、クラウドサービス"
      ],
      filePatterns: [
        "Dockerfile", "*.yaml", "k8s/", "terraform/", ".github/"
      ],
      keywordPatterns: [
        "デプロイ", "インフラ", "CI/CD", "Docker", "Kubernetes", "監視"
      ]
    },
    analyst: {
      name: "analyst",
      displayName: "コードアナリスト",
      description: "コード品質分析、パフォーマンス最適化",
      expertise: [
        "リファクタリング、技術的負債の解決",
        "コードレビューとコード改善"
      ],
      filePatterns: [],
      keywordPatterns: [
        "分析", "最適化", "リファクタリング", "パフォーマンス改善", "コードレビュー"
      ]
    }
  },

  /**
   * コマンドシステム設定
   */
  commands: {
    // 分析系コマンド
    "analyze": {
      description: "コード分析、問題特定、改善提案",
      defaultPersona: "analyst"
    },
    "explain": {
      description: "コードの動作説明、アルゴリズム解説",
      defaultPersona: "developer"
    },
    "troubleshoot": {
      description: "バグ解析、エラー原因特定、解決策提示",
      defaultPersona: "developer"
    },

    // 開発系コマンド
    "implement": {
      description: "機能実装、新規開発",
      defaultPersona: "developer"
    },
    "improve": {
      description: "リファクタリング、最適化",
      defaultPersona: "analyst"
    },
    "build": {
      description: "ビルド、コンパイル、パッケージング",
      defaultPersona: "devops"
    },

    // 設計系コマンド
    "design": {
      description: "アーキテクチャ設計、システム設計",
      defaultPersona: "architect"
    },
    "estimate": {
      description: "作業工数見積もり、スケジュール算出",
      defaultPersona: "architect"
    },

    // 管理系コマンド
    "task": {
      description: "タスク分解、作業計画",
      defaultPersona: "developer"
    },
    "workflow": {
      description: "ワークフロー設計、プロセス改善",
      defaultPersona: "devops"
    },
    "document": {
      description: "ドキュメント生成、仕様書作成",
      defaultPersona: "developer"
    },

    // ツール系コマンド
    "test": {
      description: "テスト作成、テスト実行計画",
      defaultPersona: "tester"
    },
    "git": {
      description: "Git操作、ブランチ戦略",
      defaultPersona: "devops"
    },
    "cleanup": {
      description: "コード整理、不要ファイル削除",
      defaultPersona: "analyst"
    },
    "load": {
      description: "プロジェクト構造分析、依存関係把握",
      defaultPersona: "analyst"
    },
    "index": {
      description: "コードベース索引化、関連性分析",
      defaultPersona: "analyst"
    }
  },

  /**
   * 基本ルール設定
   */
  rules: {
    language: "ja", // デフォルト言語
    codeQuality: {
      followSOLID: true,
      followDRY: true,
      errorHandling: true,
      securityConsideration: true,
      performanceEvaluation: true
    },
    developmentProcess: {
      incrementalImplementation: true,
      testDrivenDevelopment: true,
      continuousIntegration: true,
      codeReview: true,
      documentation: true
    }
  },

  /**
   * コマンドカテゴリ設定
   */
  commandCategories: {
    '分析系': ['analyze', 'explain', 'troubleshoot'],
    '開発系': ['implement', 'improve', 'build'],
    '設計系': ['design', 'estimate'],
    '管理系': ['task', 'workflow', 'document'],
    'ツール系': ['test', 'git', 'cleanup', 'load', 'index']
  },

  /**
   * 設定の整合性を検証する関数
   * @param {Object} config - 検証するSuperCopilot設定オブジェクト
   * @returns {Object} { isValid: boolean, errors: string[] }
   */
  validateConfiguration: function (config) {
    const errors = [];

    // 必須プロパティの存在チェック
    const requiredProperties = ['personas', 'commands', 'rules', 'commandCategories'];
    for (const prop of requiredProperties) {
      if (!config[prop] || typeof config[prop] !== 'object') {
        errors.push(`必須プロパティ '${prop}' が存在しないか、オブジェクトではありません`);
      }
    }

    if (config.personas) {
      // ペルソナの整合性チェック
      for (const [personaKey, persona] of Object.entries(config.personas)) {
        if (!persona.name || !persona.displayName || !persona.description) {
          errors.push(`ペルソナ '${personaKey}' に必須フィールドが不足しています`);
        }
        if (!Array.isArray(persona.expertise) || persona.expertise.length === 0) {
          errors.push(`ペルソナ '${personaKey}' の expertise が配列でないか空です`);
        }
        if (!Array.isArray(persona.filePatterns) || !Array.isArray(persona.keywordPatterns)) {
          errors.push(`ペルソナ '${personaKey}' の filePatterns または keywordPatterns が配列ではありません`);
        }
      }
    }

    if (config.commands && config.personas) {
      // コマンドとペルソナの整合性チェック
      for (const [commandKey, command] of Object.entries(config.commands)) {
        if (!command.description) {
          errors.push(`コマンド '${commandKey}' に description が設定されていません`);
        }
        if (command.defaultPersona && !config.personas[command.defaultPersona]) {
          errors.push(`コマンド '${commandKey}' の defaultPersona '${command.defaultPersona}' が存在しません`);
        }
      }
    }

    if (config.commandCategories && config.commands) {
      // コマンドカテゴリの整合性チェック
      const allCategorizedCommands = [];
      for (const [category, commands] of Object.entries(config.commandCategories)) {
        if (!Array.isArray(commands)) {
          errors.push(`コマンドカテゴリ '${category}' が配列ではありません`);
          continue;
        }
        for (const command of commands) {
          allCategorizedCommands.push(command);
          if (!config.commands[command]) {
            errors.push(`カテゴリ '${category}' 内のコマンド '${command}' が commands で定義されていません`);
          }
        }
      }

      // 未分類のコマンドをチェック
      const definedCommands = Object.keys(config.commands);
      const uncategorizedCommands = definedCommands.filter(cmd => !allCategorizedCommands.includes(cmd));
      if (uncategorizedCommands.length > 0) {
        errors.push(`未分類のコマンドがあります: ${uncategorizedCommands.join(', ')}`);
      }
    }

    if (config.rules) {
      // ルール設定の検証
      if (config.rules.language && typeof config.rules.language !== 'string') {
        errors.push('rules.language は文字列である必要があります');
      }
      if (config.rules.codeQuality && typeof config.rules.codeQuality !== 'object') {
        errors.push('rules.codeQuality はオブジェクトである必要があります');
      }
      if (config.rules.developmentProcess && typeof config.rules.developmentProcess !== 'object') {
        errors.push('rules.developmentProcess はオブジェクトである必要があります');
      }
    }

    return {
      isValid: errors.length === 0,
      errors: errors
    };
  }
};

/**
 * 設定の初期化時検証
 */
function initializeSuperCopilot() {
  const validation = superCopilot.validateConfiguration(superCopilot);

  if (!validation.isValid) {
    const errorMessage = `SuperCopilot設定に問題があります:\n${validation.errors.join('\n')}`;

    // 環境に応じたエラーハンドリング
    if (typeof console !== 'undefined') {
      console.error(errorMessage);
      console.warn('SuperCopilotは部分的な機能のみ提供されます');
    }

    // デバッグ用に検証結果を追加
    superCopilot._validationResult = validation;

    // 本番環境では例外をスローしない（部分的な機能提供を許可）
    if (typeof process !== 'undefined' && process.env.NODE_ENV === 'development') {
      throw new Error(errorMessage);
    }
  } else {
    if (typeof console !== 'undefined' && typeof process !== 'undefined' && process.env.NODE_ENV === 'development') {
      console.log('SuperCopilot設定の検証が完了しました');
    }
    superCopilot._validationResult = validation;
  }

  return superCopilot;
}

// 初期化と検証の実行
const validatedSuperCopilot = initializeSuperCopilot();

// エクスポート設定
if (typeof module !== 'undefined') {
  module.exports = validatedSuperCopilot;
}

// ブラウザ環境で利用する場合
if (typeof window !== 'undefined') {
  window.superCopilot = validatedSuperCopilot;
}
