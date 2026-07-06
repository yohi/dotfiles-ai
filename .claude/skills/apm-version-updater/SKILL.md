---
name: apm-version-updater
description: Checks and updates the pinned dependency versions and commit hashes in THIS repository's apm.yml -- the APM skill git refs (owner/repo#tag), the npm plugins under `plugin:`, and the MCP server packages under `dependencies.mcp` (npm versions and git+https commit hashes) -- and always summarizes what changed between the current and latest version of each before writing anything. Use whenever the user wants to bump, update, refresh, upgrade, or check for newer versions or commit hashes of apm.yml dependencies, plugins, or MCP servers; asks whether the apm.yml pins are outdated; or wants a version-diff / changelog summary for them, even if they do not name this skill or say 'apm.yml' explicitly. Do NOT use for updating LLM model whitelists in apm.yml (use the update-opencode-models skill for that), for package.json / uv / other lockfile bumps, for GitHub Actions version updates, or for adding brand-new MCP server entries.
---

# apm.yml バージョン更新スキル

## Context / 目的

このリポジトリ (`dotfiles-ai`) の [apm.yml](../../../apm.yml) は、外部スキル・プラグイン・MCP サーバーのバージョンを固定する **SSOT（Single Source of Truth）** です。ここに固定されている版数やコミットハッシュを最新へ更新するのは、手作業だと (1) 各依存の最新版を registry ごとに調べ、(2) スコープ付き npm 名やコミットハッシュを取り違えずに書き換え、(3) 何が変わったのかを確認する、という地味で間違えやすい作業になります。

このスキルはその一連を安全に回すためのものです。**「最新版の検出」は決定的なスクリプトに任せ**、**「バージョン間で何が変わったか」の説明は人間が読んで判断できる形で必ず提示**し、**apm.yml への書き込みはユーザーの承認後にだけ**行います。

## いつ使うか

- 「apm.yml のバージョンを最新にして」「依存を更新して」「古くなってない?」
- 「chronos-graph のハッシュを最新コミットに」「nexus を上げて」「プラグインを bump して」
- 更新に伴って「何が変わったか教えて」「変更点を出して」と言われたとき

## 前提と安全設計（なぜそうするか）

- **SSOT を壊さない**: `apm.yml` から `opencode.jsonc` や `mcp/config.yaml` が生成されます。生成物を直接いじらず、常に `apm.yml` を最小差分で書き換えます。YAML 全体を再整形すると巨大な差分になりレビュー不能になるため、対象行だけを置換します。
- **必ず差分提示 → 承認 → 適用**: ユーザーが望んでいるのは「勝手に上がる」ことではなく「何が上がるか分かった上で上げる」ことです。更新テーブルと各依存の変更点を先に出し、承認を得てから書き込みます。
- **`@latest` / 未固定は既定で据え置き**: `@latest` や版数なしの依存は意図的に最新追従にしている可能性が高いため、現状の解決先を報告するだけに留め、勝手にピン留めしません。ユーザーが「固定したい」と言った場合のみ具体バージョンへ固定します。
- **git 操作はしない**: コミット/プッシュはこのスキルでは実行せず、Conventional Commits（日本語）のコミットメッセージ案を提示するに留めます（このリポジトリの Git 運用ルールに従う）。
- **再同期・検証は案内のみ**: `apm.yml` 更新後に必要な `make apm-install` などは、実行せず手順として案内します（自動実行するとネットワークや生成物への影響が大きいため）。

## ワークフロー

<instructions>

### 1. 現状インベントリの取得

同梱スクリプトで `apm.yml` 内の「版数/ハッシュが固定された依存」を機械的に洗い出します。スコープ付き npm 名（`@yohi/justice@2.3.0`）やコミットハッシュの取り違えを防ぐため、手でパースせずスクリプトを使ってください。

```bash
python .claude/skills/apm-version-updater/scripts/check_updates.py --json
```

- `--json`: 機械可読な結果（後段の編集で正確な行・現在値を参照するために使う）。
- 人間向けの表がほしいときは引数なしで実行。
- ネットワークを使わず在庫だけ見たいときは `--no-network`。

検出される種別:
- `plugin` … トップレベル `plugin:` の npm パッケージ（例 `@yohi/justice@2.3.0`, `oh-my-openagent@4.15.1`）
- `mcp-npm` … MCP サーバーの `args` にある npm 指定（例 `@yohi/nexus@1.22.0`）
- `mcp-git` … MCP の `git+https://....git@<hash>` 形式のコミットハッシュ（例 chronos-graph）
- `apm-skill` … `dependencies.apm` の `owner/repo#<tag>` 形式（例 `obra/superpowers#v6.0.2`）
- `latest` … `@latest` 追従（情報表示のみ、既定では変更しない）

### 2. 最新バージョン / ハッシュの解決

スクリプトが種別ごとに best-effort で解決します（失敗時は `unresolved` と表示し、決してクラッシュしません）。解決手段は種別により異なります:

- npm (`plugin` / `mcp-npm`): `npm view <name> version`
- git tag (`apm-skill`): `git ls-remote --tags` から最新の semver タグ
- git hash (`mcp-git`): `git ls-remote <url> HEAD` の先頭コミット

`unresolved` になった依存（private パッケージやネットワーク不通など）は、無理に推測せず「解決できなかった」とユーザーに伝えます。

### 3. バージョン間差分の説明を生成【このスキルの最重要ステップ】

更新候補（`update = true`）の各依存について、現在版と最新版の間で **何が変わったか** を日本語で簡潔に要約します。単なる版数の羅列ではなく、ユーザーが「上げてよいか」を判断できる材料を出すのが目的です。情報源の取り方は種別ごとに異なります。詳しい取得レシピは [references/dependency-inventory.md](references/dependency-inventory.md) を参照してください。要点:

- npm パッケージ: `npm view <name> repository.url` で GitHub リポジトリを特定し、`gh release view <newtag> --repo <owner/repo>` のリリースノート、または `https://github.com/<owner/repo>/compare/<old>...<new>` の比較を使う。
- apm-skill (git tag): `gh release view <newtag> --repo <owner/repo>`、無ければ compare ビュー。
- mcp-git (commit hash): `gh api repos/<owner/repo>/compare/<oldsha>...<newsha>` のコミット一覧、または対象 URL を shallow fetch して `git log --oneline <old>..<new>`。

破壊的変更（BREAKING CHANGE、major バージョンの上昇）は特に目立たせます。リリースノートが取得できない依存は「変更点は取得できなかった（比較 URL: ...）」と正直に書き、リンクだけでも提示します。

### 4. 更新サマリの提示とユーザー承認

「出力フォーマット」の通りに、更新テーブル + 各依存の変更点 + 参照 URL をまとめて提示し、**適用してよいか承認を求めます**。ここで一旦止まってユーザーの返答を待ちます。ユーザーが一部だけ適用したい場合（例:「nexus 以外」）に対応できるよう、依存ごとに識別しやすく並べます。

### 5. apm.yml への適用（承認後のみ）

承認された依存についてのみ、`apm.yml` の該当行を最小差分で書き換えます。

- 版数だけ / ハッシュだけを置換し、周囲の引用符・インデント・`[all]` などの extras は保持する。
- スクリプトの `--json` が返す行番号と現在値を突き合わせ、置換対象を取り違えない。
- `@latest` / 未固定は、ユーザーが明示的に固定を求めた場合を除き触らない。

### 6. 次アクションの案内（自動実行しない）

適用後、ユーザーが自分で走らせるための手順を案内します（このスキルは実行しません）:

- `make apm-install` — 依存を再解決し `apm.lock.yaml`（コミットハッシュ含む）を更新。
- MCP の版数を変えた場合は `make sync-mcp`、スキル/プラグインを変えた場合は `make sync-agents`。
- コミット案（Conventional Commits・日本語）を提示。例: `chore(deps): apm.yml の依存を最新化 (nexus 1.22.0->1.23.0 ほか)`

</instructions>

## 出力フォーマット

更新サマリは必ず次の構成で出します。まず全体テーブル、続いて依存ごとの変更点、最後に承認依頼です。

```
## apm.yml 更新サマリ

| 種別 | 依存 | 現在 | 最新 | 更新 |
|------|------|------|------|------|
| plugin | @yohi/justice | 2.3.0 | 2.4.1 | あり |
| mcp-git | yohi/chronos-graph | cb1f33f | a1b2c3d | あり |
| mcp-npm | @yohi/nexus | 1.22.0 | 1.22.0 | なし |
| plugin | @nick-vi/opencode-type-inject | latest | (latest 追従) | 据え置き |

### @yohi/justice: 2.3.0 -> 2.4.1
- 主な変更点:
  - <箇条書きで要約>
  - <BREAKING があれば明示>
- 参照: https://github.com/<owner/repo>/compare/v2.3.0...v2.4.1

### yohi/chronos-graph: cb1f33f -> a1b2c3d
- 主な変更点:
  - <コミット要約>
- 参照: https://github.com/yohi/chronos-graph/compare/cb1f33f...a1b2c3d

---
上記を apm.yml に適用してよいですか?（一部のみ・全部・見送り を選べます）
```

適用後は、変更した行と「次アクション」（`make apm-install` ほか）+ コミットメッセージ案を短く報告します。

## 参照

- [references/dependency-inventory.md](references/dependency-inventory.md) — 依存の種類別「最新取得」「差分取得」レシピと、現在の apm.yml インベントリのスナップショット。
- [scripts/check_updates.py](scripts/check_updates.py) — 検出 + 最新解決スクリプト（ASCII のみ・stdlib のみ）。
