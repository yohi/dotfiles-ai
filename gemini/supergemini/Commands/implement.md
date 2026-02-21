# /sg:implement コマンド

## 説明
新機能やコンポーネントの設計・実装を行います。

## 使用法
```
/sg:implement <機能名> [オプション]
```

## オプション
- `--lang=<言語>`: 実装に使用するプログラミング言語を指定します (デフォルト: プロジェクトの主要言語)
- `--framework=<フレームワーク>`: 使用するフレームワークを指定します
- `--test`: テストコードも一緒に実装します
- `--doc`: ドキュメントも一緒に生成します
- `--pattern=<パターン>`: 実装に使用する設計パターンを指定します

## 例
```
/sg:implement ユーザー認証機能
/sg:implement --lang=typescript --framework=react ショッピングカート
/sg:implement --test --doc ブログ投稿API
/sg:implement --pattern=repository データアクセス層
```

## 注意事項
- 実装する機能の要件を明確にすると、より適切なコードが生成されます
- 既存のコードベースの構造や命名規則に従った実装を行います
- 大規模な機能は適切なモジュールに分割して実装されます

## 内部動作
1. 機能要件の分析
2. 適切な設計パターンの選択
3. コードの生成
4. （オプション）テストコードの生成
5. （オプション）ドキュメントの生成
6. レビューと最適化

## 出力例

```typescript
/**
 * ユーザー認証サービス
 * @module AuthService
 */

import { User } from './types';
import { hashPassword, comparePasswords } from './utils/security';
import { db } from './database';

export class AuthService {
  /**
   * ユーザーの認証を行う
   * @param email ユーザーのメールアドレス
   * @param password ユーザーのパスワード
   * @returns 認証結果とユーザー情報
   */
  async authenticate(email: string, password: string): Promise<{
    success: boolean;
    user?: User;
    message?: string;
  }> {
    try {
      // ユーザーの検索
      const user = await db.users.findOne({ email });

      if (!user) {
        return {
          success: false,
          message: 'ユーザーが見つかりません'
        };
      }

      // パスワードの検証
      const isValid = await comparePasswords(password, user.passwordHash);

      if (!isValid) {
        return {
          success: false,
          message: 'パスワードが正しくありません'
        };
      }

      return {
        success: true,
        user: {
          id: user.id,
          name: user.name,
          email: user.email,
          role: user.role
        }
      };

    } catch (error) {
      console.error('認証エラー:', error);
      return {
        success: false,
        message: '認証中にエラーが発生しました'
      };
    }
  }
}
```
