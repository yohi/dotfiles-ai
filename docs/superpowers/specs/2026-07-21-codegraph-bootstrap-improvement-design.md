# CodeGraph Bootstrap Wrapper 改善設計書

- **Date**: 2026-07-21
- **Status**: Draft (Pending Review)
- **Scope**: `_scripts/codegraph-bootstrap.sh`、`_scripts/test-codegraph-bootstrap.sh`、`apm.yml` 関連設定の改善

---

## 1. 概要

本設計書は、`dotfiles-ai` リポジトリで利用している CodeGraph MCP サーバーのブートストラップラッパー `_scripts/codegraph-bootstrap.sh` を、より堅牢で運用しやすい形に改善するための設計です。

既存のラッパーは以下を実現しています：

- `.codegraph/` ディレクトリが存在しない場合に `codegraph init` を自動実行
- その後 `codegraph serve --mcp` へ `exec` で引き継ぐ
- `flock` による複数 MCP クライアント同時起動時の競合防止
- `flock` 未搭載環境（macOS など）へのフォールバック
- `codegraph init` 失敗時の部分初期化ディレクトリのクリーンアップ
- `codegraph init` 実行中の stdin を `/dev/null` へリダイレクトし、MCP プロトコルバイトを保護

本改善では、上記の基本機能を維持しつつ、**堅牢性**、**テスト品質**、**運用性**の3つの観点から機能を追加します。

---

## 2. 背景と目的

### 2.1 背景

CodeGraph MCP サーバーは、AI エージェントがコードベースを理解する際に「ファイルを読む」ではなく「シンボルや呼び出し関係を直接問い合わせる」ことを可能にする重要な MCP サーバーです。`dotfiles-ai` では `apm.yml` を SSOT とし、CodeGraph の MCP エントリを `_scripts/codegraph-bootstrap.sh` へ向けることで、初回利用時の自動初期化を実現しています。

しかし、以下の点で運用時の負担やリスクが残っています：

- 診断ログと MCP プロトコル出力の分離が不十分
- `codegraph` コマンド不在時や `codegraph init` タイムアウト時の挙動が未定義に近い
- 手動での状態確認やトラブルシュート用の補助モードがない
- テストカバレッジに並行起動やタイムアウト系ケースが含まれていない

### 2.2 目的

- MCP プロトコル出力を汚染せず、かつ運用者が問題を追跡できるログ機構を提供する
- `codegraph` コマンド不在、タイムアウト、並行起動などのエッジケースを安全に処理する
- `--status`、`--dry-run` モードを提供し、CI や手動確認に利用できるようにする
- 回帰テストを拡充し、CI に組み込む

---

## 3. 改善後のアーキテクチャ

### 3.1 全体構成

```text
[MCP Client] ──stdio──▶ [_scripts/codegraph-bootstrap.sh]
                                      │
                                      ├── 診断・進捗ログ ──▶ .codegraph/logs/bootstrap.log
                                      │
                                      ├── ロック制御 (.codegraph-bootstrap.lock)
                                      │
                                      ├── codegraph init (初回のみ)
                                      │
                                      └── exec codegraph serve --mcp
                                                  │
                                                  └── stdout/stdin: MCP プロトコル専用
```

### 3.2 各コンポーネントの責務

| コンポーネント | 責務 |
|---|---|
| `_scripts/codegraph-bootstrap.sh` | リポジトリルート解決、`.codegraph/` 存在確認、初回 init、MCP サーバー起動、診断ログ書き出し |
| `.codegraph-bootstrap.lock` | `flock` による並行起動排他 |
| `.codegraph/logs/bootstrap.log` | 構造化された診断ログ（タイムスタンプ、フェーズ、メッセージ） |
| `codegraph` CLI | 実際のインデックス生成と MCP サーバー処理（変更なし） |

### 3.3 データフロー

1. **起動**: MCP クライアントが `_scripts/codegraph-bootstrap.sh serve --mcp` を実行
2. **事前検証**: `codegraph` コマンドが PATH に存在するか確認。リポジトリルートへ `cd`
3. **ロック取得**: `.codegraph-bootstrap.lock` への `flock`（なければフォールバック）
4. **初回判定**: `.codegraph/` が存在しない場合のみ `codegraph init` を実行。stdin を `/dev/null` へリダイレクトし、タイムアウト適用
5. **失敗時クリーンアップ**: init 失敗時に作成途中の `.codegraph/` を削除
6. **MCP サーバー exec**: ロック解放後、`exec codegraph serve --mcp`。以降、stdin/stdout は純粋に MCP プロトコルバイトのみを通す

---

## 4. 機能仕様

通常の MCP サーバー起動。初回のみ `codegraph init` を実行後、`codegraph serve --mcp` へ `exec` する。
引数 `serve --mcp` 以外が渡された場合は、`codegraph` CLI へそのまま転送しない。未知のモード引数は stderr へエラーを出力して exit 1 する。

### 4.2 `--status` モード

```bash
_scripts/codegraph-bootstrap.sh --status
```

以下を診断して終了する：

- `codegraph` コマンドの有無
- `.codegraph/` ディレクトリの有無
- `.codegraph-bootstrap.lock` の有無
- 最後に記録されたブートストラップ結果（成功/失敗/不明）

出力先：stdout（人間が読む用途）。終了コード：正常時 0、異常時 1。

### 4.3 `--dry-run` モード

```bash
_scripts/codegraph-bootstrap.sh --dry-run serve --mcp
```

実際の `codegraph init` / `codegraph serve` は行わず、「この引数で実行されると何が起きるか」を表示して終了する。CI での導入確認に利用する。

### 4.4 環境変数

| 環境変数 | 説明 | デフォルト |
|---|---|---|
| `CODEGRAPH_INIT_TIMEOUT` | `codegraph init` のタイムアウト秒数 | `300` |
|| `CODEGRAPH_LOG_LEVEL` | ログの詳細度 (`silent`, `error`, `warn`, `info`, `debug`) | `info` |
|| `CODEGRAPH_BOOTSTRAP_LOG` | ログファイルのパス | `$REPO_ROOT/.codegraph-bootstrap.log` |
| `CODEGRAPH_NO_DAEMON` | ファイルウォッチャー無効化（CodeGraph 側設定と整合） | — |

---

| `.codegraph-bootstrap.lock` 作成不可 | warn ログを出力して続行。並行起動時の重複 init は `codegraph init` の冪等性に委ねる | stderr + bootstrap.log |
| `flock` 未取得 | 待機して再試行（デフォルト最大30秒） | bootstrap.log |
| `codegraph init` タイムアウト | 子プロセスを kill、部分初期化を削除、exit 1 | stderr + bootstrap.log |
| `codegraph init` 失敗 | 部分 `.codegraph/` を削除、exit 1 | stderr + bootstrap.log |
| シグナル受信（SIGINT/SIGTERM） | ロック解放、子プロセスへフォワード、exit | bootstrap.log |

---

## 6. テスト計画

### 6.1 既存テストの維持

- 初回起動で `.codegraph/` 作成と `serve --mcp` 起動
- 2回目以降は `init` をスキップ
- init 失敗時の部分ディレクトリ削除
- macOS 等 `flock` 不在時のフォールバック

### 6.2 追加テスト

1. `codegraph` コマンド不在時のエラーメッセージと終了コード検証
2. `codegraph init` タイムアウト時のクリーンアップ動作
3. 並行起動（2プロセス同時）で `codegraph init` が1回のみ実行されること
4. `--status` モード: `.codegraph/` 有無・`codegraph` 有無を正しく報告
5. `--dry-run` モード: init/serve ともに実行されないこと
6. ログファイル出力: タイムスタンプとフェーズ情報が含まれること
7. stdin が `codegraph init` 実行中に閉じられていること（MCP プロトコル保護）

### 6.3 CI 組み込み

- 既存の GitHub Actions ワークフローに `bash _scripts/test-codegraph-bootstrap.sh` を追加
- `make test` 系ターゲットがあればそこにも追加を検討

---

## 7. 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `_scripts/codegraph-bootstrap.sh` | ラッパー本体を改善（ログ、タイムアウト、モード追加） |
| `_scripts/test-codegraph-bootstrap.sh` | 新規テストケース追加 |
| `.gitignore` | `.codegraph/logs/` を追加（既存 `.codegraph-bootstrap.lock` は維持） |
| `.github/workflows/*.yml` | CI にテスト実行を追加 |
| `docs/superpowers/specs/2026-07-21-codegraph-bootstrap-improvement-design.md` | 本設計書 |

---

## 8. 非対象・将来検討

本設計書の範囲外とし、将来検討する可能性がある項目：

- CodeGraph 自体のバージョン管理や `codegraph upgrade` 連携
- `.codegraph/` の不在時にエージェントへ「初期化中」の進捗通知を返す仕組み
- リモートリポジトリや大規模モノレポ向けの lazy indexing 戦略

---

## 9. 承認待ち

本設計書に問題がなければ、次のステップとして `writing-plans` スキルを用いて実装計画を作成します。
