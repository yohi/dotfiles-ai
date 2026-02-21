# SuperGemini ペルソナ設定

このディレクトリには、SuperGeminiのペルソナ設定ファイルが含まれています。

## ファイル構造

- `personas.json` - ペルソナの設定データ（JSON形式）
- `personas.md` - ペルソナの詳細なドキュメント（マークダウン形式）

## personas.json 設定形式

```json
{
  "personas": {
    "persona_name": {
      "name": "persona_name",
      "emoji": "絵文字",
      "title": "短いタイトル",
      "description": "ペルソナの説明",
      "specialties": [
        "専門分野1",
        "専門分野2",
        "..."
      ]
    }
  }
}
```

## 新しいペルソナの追加

1. `personas.json`に新しいペルソナエントリを追加
2. `supergemini/__init__.py`の`default_config`内の`personas`配列に名前を追加
3. 必要に応じて`personas.md`にドキュメントを追加

## 設定の同期

- `personas.json`ファイルは実行時に読み込まれるため、変更は即座に反映されます
- ペルソナ一覧の表示順序は`supergemini/__init__.py`の`default_config`の順序で決まります

## コマンド

- `python -m gemini personas` - ペルソナ一覧を表示
- `python -m gemini persona-detail <persona名>` - ペルソナの詳細情報を表示

## 利点

1. **保守性**: ペルソナ情報の変更がコードの再コンパイルなしで可能
2. **拡張性**: 新しいペルソナの追加が簡単
3. **一貫性**: 設定ファイルとドキュメントの同期が容易
4. **国際化**: 将来的に多言語対応が可能
