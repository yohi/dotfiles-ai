"""
SuperGemini Hooks Module

このモジュールはSuperGeminiのフック機能を提供します。

フックシステムは以下の機能を提供します:
- プラグイン拡張のためのフックポイント定義
- イベント駆動型の処理実行
- カスタム処理の挿入ポイント

主な用途:
- プロンプト処理の前後での追加処理
- レスポンス生成時のカスタムフィルタリング
- 外部システムとの連携
- ログ記録やモニタリング

使用例:
    from supergemini.hooks import register_hook, execute_hooks

    # フックの登録
    @register_hook('before_response')
    def custom_filter(data):
        # カスタム処理
        return modified_data

    # フックの実行
    result = execute_hooks('before_response', input_data)
"""

__version__ = "1.0.0"


class HookRegistry:
    """フック登録とトリガー管理クラス"""

    def __init__(self):
        self.hooks = {}

    def register(self, event_name, callback):
        """フックを登録"""
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        self.hooks[event_name].append(callback)

    def execute(self, event_name, data=None):
        """指定されたイベントのフックを実行"""
        if event_name in self.hooks:
            for callback in self.hooks[event_name]:
                data = callback(data) if data is not None else callback()
        return data


# グローバルフックレジストリ
_hook_registry = HookRegistry()


def register_hook(event_name):
    """デコレータ形式でフックを登録"""

    def decorator(func):
        _hook_registry.register(event_name, func)
        return func

    return decorator


def execute_hooks(event_name, data=None):
    """フックを実行"""
    return _hook_registry.execute(event_name, data)


def list_hooks():
    """登録されているフックの一覧を取得"""
    return dict(_hook_registry.hooks)


# Export main components
__all__ = [
    "HookRegistry",
    "register_hook",
    "execute_hooks",
    "list_hooks",
]
