<div align="center">

[中文](README.zh.md) | [English](../README.md) | **日本語** | [한국어](README.ko.md)

</div>

<p align="center">
  <img src="../assets/hero.svg" alt="SearchOS — 単一の事実検索から全領域リサーチまで、引用付きのリレーショナル・スキーマ補完として統一" width="100%">
</p>

<h3 align="center">オープンドメイン情報探索のためのマルチエージェント協調システム</h3>

<p align="center">
  <a href="https://antins-labs.github.io/SearchOS/"><img src="https://img.shields.io/badge/🌐_Website-searchos-2563EB?style=for-the-badge" alt="Website"></a>
  <a href="https://arxiv.org/abs/2607.15257"><img src="https://img.shields.io/badge/arXiv-2607.15257-B31B1B?style=for-the-badge&amp;logo=arxiv&amp;logoColor=white" alt="arXiv: 2607.15257"></a>
  <a href="https://huggingface.co/papers/2607.15257"><img src="https://img.shields.io/badge/🤗_Hugging_Face-Paper-FFD21E?style=for-the-badge" alt="Hugging Face Paper"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/Built_with-LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/TUI-Textual-0B0B0B?style=for-the-badge&logo=gnometerminal&logoColor=white" alt="Textual TUI"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-0E9B9B?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <i>オペレーティングシステムがプロセスをスケジュールするように、検索をスケジュールする：
  オープンドメインの質問を正規化されたカバレッジマップへとコンパイルし、空のセルをパイプライン並列の
  サブエージェントに割り当て、すべてのエビデンスを出典とともに共有のエビデンスグラフへ書き込み、
  最後に<b>検索状態</b>から引用付きの答えを合成します —— 状態はシステムの中にあり、会話履歴の中にはありません。</i>
</p>

<p align="center">
  <img src="../assets/main.png" alt="SearchOS システム概要：マルチエージェント協調 + ミドルウェア + SOCM + スキルシステム" width="95%">
</p>

<p align="center">
  <a href="https://youtu.be/DZNXxMcxnMQ">
    <img src="../assets/searchos-demo.gif" alt="SearchOS デモ：ターミナル TUI から実クエリを発行 → マルチエージェントが並列でテーブルを埋める → Web フロントエンドで合成された回答を確認" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/DZNXxMcxnMQ">フルデモ動画（YouTube）</a></b>
</p>

<p align="center">
  <a href="https://youtu.be/wxy74AqykwY" title="SearchOS 製品ウォークスルーを見る（英語）">
    <img src="../assets/gallery/product-demo-en.jpg" alt="SearchOS 製品ウォークスルー：セットアップ、カバレッジ、エビデンス、修復、エクスポート" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/wxy74AqykwY">製品ウォークスルー（英語）</a></b>
</p>

> **▶️ クイックスタート：**
>
> ```bash
> ./install.sh && source .venv/bin/activate && searchos "2025年QS分野別ランキング各分野トップ5の大学とその出願締切"
> ```
>
> 初回実行時は自動的に**セットアップウィザード**が起動します：モデルプロバイダ（各社 coding plan / 従量課金 API / ローカルデプロイ）を選び、API キーを入力するだけで動きます。
> あるいは `searchos` でフルスクリーン TUI に入り、タスク派遣・ツールストリーム・カバレッジマップの成長をリアルタイムで確認できます。
> `./web/start.sh` で REST/WS API（`:8000`）+ Web フロントエンド（`:3000`）をワンコマンドで起動し、ブラウザから検索を発行してエージェントウォールとカバレッジマップをライブで見ることもできます。

## 📣 News

- **2026-07-17** — **SearchOS-V1 論文を arXiv で公開しました。** [arXiv](https://arxiv.org/abs/2607.15257) または [Hugging Face](https://huggingface.co/papers/2607.15257) でご覧ください。 📄
- **2026-07-11** — **より速く始め、より広く探し、すべての過程を見渡す。** 新しいワンコマンドインストーラーですぐに起動。並列 Explore waves がウェブをバッチ探索し、ライブ進捗とエンティティ別に整理されたエビデンスが、発見の流れを明確にします。スキルは強化された隔離ワーカー内で実行されるようになりました。 ⚡
- **2026-07-10** — **リサーチを、構造から。** 問いを描くだけで、SearchOS が探索・改善・書き出しまでできる、引用に裏付けられたリサーチへ変えます。 🧩
- **2026-07-09** — **続きは、離れたその場所から。** 会話も進捗もエビデンスもライブアクティビティも、そのまま戻ってきます。 ⏪
- **2026-07-08** — **すべての設定を、ひとつの場所に。** モデル、プロバイダ、検索、スキル、予算を、シンプルなコントロールセンターに集約しました。 ⚙️
- **2026-07-07** — **SearchOS、オープンソースで登場。** マルチエージェント検索、構造化リサーチ、TUI、Web UI。そのすべてを、すべての人へ。 🚀

## ✨ ハイライト

- 🗂️ **検索状態はシステム資産** — SOCM（Search-Oriented Context Management）がタスクキュー・エビデンスグラフ・カバレッジマップを全エージェント共有の永続状態に集約。スナップショット / 復元 / リプレイが可能で、会話履歴に埋もれません。
- 🧩 **カバレッジマップ駆動、リコール優先** — 質問を entity × attribute の正規化テーブルにモデル化し、全セルが出典付きの値で埋まるまで空セルを狙って派遣。
- ⚡ **パイプライン並列のサブエージェント** — search → open → find フェーズがエージェント間でオーバーラップ。総実行時間は直列の合計ではなく最も遅い単一チェーンに漸近。
- 🔗 **全セルに引用付き** — 抽出ミドルウェアが (entity, attribute, value, source) をエビデンスグラフへ自動記録。答えはセル単位で出典に遡れます。
- 🛡️ **センサーによるセーフティネット** — ツール呼び出しごとに 5 種類のループ / 停滞検出。まずリマインダーで軌道修正、改善しなければ別角度から再派遣。
- 🧰 **スキル + マルチプロバイダを標準装備** — access スキルがアンチボット / ログインウォールの難サイトを攻略、strategy スキルがランキング / マルチホップ / 曖昧性解消に対応。`SF_PROVIDER` 一行で任意のベンダーに接続。

> 📊 **WideSearch / GISA** の全 headline F1 でトップ。列挙型の **Set · F1 は次点ベースラインを +13.4 上回る**（詳細は[評価](#-評価)）。

## 🎥 Gallery

<table align="center">
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/dfzu9aeK0Cs" title="SearchOS-Web Demo · YouTube で見る">
        <img src="../assets/gallery/web-demo.jpg" alt="SearchOS-Web Demo" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-Web Demo</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/bS07neJm6FA" title="SearchOS-Web Demo 2 · YouTube で見る">
        <img src="https://img.youtube.com/vi/bS07neJm6FA/hqdefault.jpg" alt="SearchOS-Web Demo 2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-Web Demo 2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/YhJdc7Qhr1U" title="SearchOS-demo1 · YouTube で見る">
        <img src="../assets/gallery/demo1.jpg" alt="SearchOS-demo1" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo1</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/IA_-sO2avTA" title="SearchOS-demo3 · YouTube で見る">
        <img src="../assets/gallery/demo3.jpg" alt="SearchOS-demo3" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo3</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/HxCLoauXoYg" title="SearchOS-demo4 · YouTube で見る">
        <img src="../assets/gallery/demo4.jpg" alt="SearchOS-demo4" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo4</b></sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <a href="https://youtu.be/-QmjRr_3B1s" title="SearchOS-demo5 · YouTube で見る">
        <img src="../assets/gallery/demo5.jpg" alt="SearchOS-demo5" width="50%">
      </a>
      <br><sub>▶️ <b>SearchOS-demo5</b></sub>
    </td>
  </tr>
</table>

<p align="center"><sub>サムネイルをクリックすると YouTube で再生（デモは順次追加予定）</sub></p>

<!-- 動画を追加する場合：上の <td>…</td> ブロックをコピーし、youtu.be リンク・assets/gallery サムネイル・タイトルを差し替えてください -->

## 💡 Why SearchOS

汎用エージェントや Deep Search エージェントを長時間の検索タスクにそのまま使うと、よく次の失敗モードが現れます：

* **プロセスが不透明** — 中間の検索結果が何十ターンもの会話履歴に埋もれ、コンテキスト圧縮後に事実が失われやすい。実行途中に進捗が見えず、復元もリプレイもできない。
* **「無限ループ」しやすい** — 何を調べたか覚えていない：同じクエリを言い換えて何度も発行し、同じエンティティの属性を別のサブタスクで重複して検索する。
* **役割分担が曖昧** — サブエージェントが検索・読解・記憶・要約をすべて抱え込み、タスクが長くなると破綻する：抽出フィールドの基準が揃わず、出典が失われる。
* **入れない、探し方も分からない** — アンチボット・ログインウォール・深い階層に阻まれて難サイトが開けない。ランキング・マルチホップ・曖昧性解消のような複雑な問題は、検索回数を増やすだけでは解けない。

SearchOS はこの 4 つの失敗に、それぞれ機構レベルの解決策を与えます：

* **検索状態はシステムの中に、会話履歴の中ではなく** — SOCM がタスクキュー・エビデンスグラフ・カバレッジマップを共有の永続状態（`search_state.json`）に置き、いつでもスナップショット / 復元 / リプレイ可能。サブエージェントは三層コンテキスト（SOCM スナップショット → エピソード要約 → 直近のワーキングメモリ）で完全な履歴を置き換え、安定プレフィックスは prompt cache に優しい設計。
* **エンティティ単位のモデリング + ループを断つセンサー** — 主キー + 属性の正規化マルチテーブル（外部キー付き）で同じ事実は一度だけ取得し、派遣は常に空セルを狙う。LoopSensor がツール呼び出しごとに 5 種のループ検出を実施——まずリマインダーで軌道修正、改善しなければ `looped` として別角度から再派遣。
* **検索と抽出の分離** — サブエージェントは正しいページを見つけるだけ。ページを開くたびに judge モデルが (entity, attribute, value, source, confidence) をエビデンスグラフへ抽出し、単位正規化と原文への抜粋アンカーを実施——基準が一貫し、出典を追跡できる。
* **オープンドメイン情報検索に向けた、ロール整合型の三層スキルシステム** — 方法論、検索戦略、サイト単位の実行可能なアクセススキルを統一的に編成します（詳細は[スキルシステム](#-スキルシステム)）。

## 🧩 Framework

```
ユーザーのクエリ
   │
   ▼
┌─────────────────────────── Orchestrator（唯一の意思決定者）───────────────────────┐
│   Explore 偵察 → create_schema でカバレッジマップ構築 → enqueue_tasks 派遣        │
│   → check_agents ポーリング → 評価/調整 → カバレッジ十分または予算切れ → 合成     │
└──────┬──────────────────────────┬─────────────────────────────┬─────────────────┘
       ▼                          ▼                             ▼
  explore_agent              search_agent × N              writer_agent
 （クエリ分類 / hub ページ / （サブタスクごとに Web を     （SOCM を読み取り
   候補エンティティ /         検索、状態を直接             引用付きセクションを
   検索プラン）               書き込まない）                執筆）
       │                          │                             │
       └────────────┬─────────────┴─────────────────────────────┘
                    ▼
      三層ミドルウェア：Context → Sensor → Extraction
     （プロンプト組み立て / 予算・ループ監視 / judge による自動エビデンス抽出）
                    │
                    ▼
┌──────────── SOCM · Search-Oriented Context Management（共有検索状態）────────────┐
│  Frontier Memory   タスクキュー：priority + blocked_by DAG、3 種類のタスクが      │
│                    1 つのプールを共有                                             │
│  Evidence Graph    エビデンスグラフ：finding / source / confidence、             │
│                    support-conflict エッジ                                        │
│  Coverage Map      カバレッジマップ：entity × attribute、マルチテーブル +         │
│                    外部キー、列レベルの型 / フォーマット / バリデーション         │
│  Strategy Memory   戦略と失敗の記憶   ·   Writer Outline   ·   Budget             │
└───────────────────────────────────────────────────────────────────────────────────┘
```

1 セッションは次の 6 ステップをループします：

1. **Explore** — 偵察兵が先行：クエリタイプの判定、hub ページの特定、候補エンティティと検索プランの生成を行い、具体的な属性値は抽出しません。
2. **Schema** — Orchestrator がエンティティタイプごとに正規化されたカバレッジマップ（マルチテーブル + リレーション）を構築。Explore が発見したエンティティはすべてシード行として着席します。
3. **Dispatch** — ギャップを自己完結した自然言語のサブタスクに分割し、優先度と依存関係に従って search agent へ並列派遣します。
4. **Extract** — ページを開くたびに Extraction ミドルウェアが (entity, attribute, value, source, confidence) を自動抽出してエビデンスグラフに書き込み、カバレッジマップを点灯させます。
5. **Assess** — サブタスクをポーリングして回収：新エンティティをテーブルに追加、悪質なソースをブラックリスト化、コンフリクトは仲裁へ、空セルはターゲットを絞って補完します。
6. **Synthesize** — カバレッジの自己チェックを通過したら、SOCM からユーザーの求める形式に join し、1 件ずつ引用を付けて出力します。

### 出力はこんな形

すべてのセルに出典番号がアンカーされ、末尾に対応する出典が列挙されます——これが「引用付きのリレーショナル・スキーマ補完」の成果物としての姿です（実際の実行からの抜粋。クエリは中国語で*香港のここ数年の人気保険を整理して*）：

```markdown
### 香港の主要保険会社
| 会社       | 英語名          | 2024 APE ランク | 2023 保険料規模 |
|-----------|----------------|----------------|----------------|
| 友邦保険   | AIA [6]        | 第 1 位 [6]     | 871 億 HKD [6] |
| 保誠       | Prudential [6] | 第 2 位 [6]     | 653 億 HKD [6] |
| 匯豐保険   | HSBC Life [6]  | 第 3 位 [6]     | 555 億 HKD [6] |
| 宏利       | Manulife [6]   | 第 4 位 [6]     | 498 億 HKD [6] |

### 情報ソース
[6] https://www.ia.org.hk/tc/infocenter/press_releases/20250425.html, https://inews.hket.com/…
```

完全な成果物（trajectory・ページキャッシュ・SOCM 状態を含むリプレイ可能なディレクトリ）は `searchos_workspace/<タイムスタンプ>/` にあります。

## 🚀 インストール

Python ≥ 3.11 が必要です：

```bash
./install.sh                # 推奨：Python 環境 + Access Skills + Chromium + Web フロントエンド
source .venv/bin/activate

pip install -e .            # 手動：コア依存
pip install -e ".[access]"  # 手動：Access Skill 依存
pip install -e ".[eval]"    # 手動：評価依存
pip install -e ".[all]"     # 手動：すべてのオプション依存
```

フルインストーラーには Node.js ≥ 20.9 も必要です。`--core`、`--no-web`、`--all --dev` で構成を選べます。詳細は[インストールガイド](installation.md)を参照してください。

## ⚙️ 設定

**初回実行時は自動的にセットアップウィザードが起動します**：利用可能なモデル設定がなければ `searchos` がプロバイダと API キーを案内し、`.env` に保存します（`searchos --setup` で再設定）。Web Settings と TUI の `/model`、`/search`、`/config` は同じ `web_settings.json` を共有します。

シークレットは手動でも設定できます。[`.env.example`](../.env.example) を `.env` にコピーし、実際に使用する API キーだけを記入してください。プロバイダ、モデル、検索バックエンド、その他の実行設定はセットアップウィザード、Web Settings、または TUI で選択し、`web_settings.json` に保存します。

```bash
ZHIPU_API_KEY=xxx             # モデルプロバイダキーの例
SERPER_API_KEY=xxx            # 検索プロバイダキーの例
JINA_API_KEY=xxx              # オプション：Jina の取得クォータを拡張
```

全プリセット（各社のエンドポイント・モデル ID・キーの取得方法・既知の癖）は [`docs/providers.md`](../docs/providers.md) を参照してください。上級者向けに、`SF_PROVIDER` などの `SF_*` 環境変数だけで構成する方法も引き続きサポートしています。

すべての設定は `settings.py` に集約され、`SF_` プレフィックスの環境変数で上書きします。ネストしたフィールドは `__` で区切ります。モデルは**ロール**単位でバインドされ（11 ロール → モデルプロファイル）、プロバイダ混在、レート制御、アブレーション、コスト削減に対応します：

| よく使う設定 | 説明 |
| --- | --- |
| `SF_MODEL` / `SF_FAST_MODEL` | プリセットのメイン / 軽量モデルを上書き |
| `SF_API_BASE` | エンドポイントを上書き（国際版ドメインへの切替など） |
| `SF_SEARCH_PROVIDER` | 検索バックエンド：`serper` \| `tavily` \| `ragflow`（未設定なら既存キーから推定） |
| `SF_BROWSER_BACKEND` | フェッチバックエンド：`jina` \| `aiohttp` \| `crawl4ai` \| `search_engine` |
| `SF_ROLES__JUDGE=main` | 特定ロールのモデルプロファイルだけ付け替え（上級 / アブレーション） |
| `SF_PROFILES__MAIN__TEMPERATURE=0.3` | 単一プロファイルのフィールドレベル上書き（上級 / アブレーション） |
| `SF_PROFILES__MAIN__RPM=60` / `...__TPM=100000` | プロファイル単位のリクエスト/Token 制限 |
| `SF_MAX_PARALLEL_AGENTS` | サブエージェント並列上限（デフォルト 8） |
| `SF_ENABLE_EXPLORE_BATCH` / `SF_EXPLORE_MIN_WAVES` / `SF_EXPLORE_MAX_WAVES` | 並列 Explore と wave 範囲（デフォルト 2–3） |
| `SF_ENABLE_EXPLORE` / `SF_ENABLE_SKILLS` | アブレーションスイッチ：Explore / Skill を無効化 |
| `SF_SKIP_SYNTHESIS` | 評価モード：合成をスキップしてカバレッジマップから直接テーブルを出力 |

## 🧭 クイックスタート

| コマンド | 動作 |
| --- | --- |
| `python -m searchos "<query>"` | 単発クエリ。結果は `searchos_workspace/<タイムスタンプ>/output/report.md` に出力 |
| `python -m searchos` | フルスクリーン Textual TUI：リアルタイムパネル、実行中の介入、マルチターン追問、`/skill` スキル管理 |
| `python -m eval.run --benchmark widesearch --range 1-50` | 評価の実行（次節参照） |

### インタラクティブ TUI

`python -m searchos` でフルスクリーン画面に入ります：上部はリアルタイムダッシュボード（タスク派遣・サブエージェント状態・カバレッジマップの成長）、下部はツールストリーム。1 つの入力ボックスがタイミングによって自動的に振り分けられます：

| タイミング | 自然言語を入力すると |
| --- | --- |
| アイドル時 | 新しい検索実行を開始 |
| **実行中** | **リアルタイム介入（steering）**——テキストが即座に実行中の Orchestrator へ注入され、サブエージェントは中断されません。制約の追加（「2024 年のデータだけ」）、軌道修正、良いデータソースの提示に使えます |
| 実行終了後 | **マルチターン追問**——前ラウンドのカバレッジマップとエビデンスを引き継ぎます：答えが既にテーブルにあれば直接回答（再検索なし）、なければ既存テーブルを増分拡張し、ゼロから再構築しません |

スラッシュコマンドはいつでも使えます（実行中も有効）：

| コマンド | エイリアス / ショートカット | 動作 |
| --- | --- | --- |
| `/new` | `/clear` · `Ctrl-N` | 新しいトピック：会話履歴とカバレッジマップをクリアし、次の質問は新しいワークスペースから開始 |
| `/resume [session-id]` | `/load` | 会話、軌跡、カバレッジ、エビデンスを含む過去セッションを復元。ID 省略時は選択画面を表示 |
| `/effort [low\|medium\|high\|max]` | — | 投入レベル：イテレーション上限・並列数・エージェントごとの検索予算・実行時間制限・スキルルーティング top-k を一括調整。引数なしでインタラクティブセレクタが開き、実行中の変更は次ラウンドから有効 |
| `/skill` | — | スキル管理：引数なしでグループ化されたマルチセレクトダイアログを表示。サブコマンド `list`（一覧）、`only <名前…>`（ホワイトリスト、前方一致）、`on` / `off <名前…>`（有効/無効）、`all`（ルーターに戻す）で有効セットを細かく制御 |
| `/model` | — | Provider 接続、モデルカード、ロール、レート制限の共有設定 |
| `/search [auto\|serper\|tavily\|ragflow]` | — | 検索バックエンドの確認・切替 |
| `/config [key value]` | `/set` | 共有設定画面、または実行デフォルトの簡易変更 |
| `/verbose` | `/detail` · `Ctrl-T` | 簡易 / 詳細ツールストリームの切替 |
| `/stop` | `/cancel` · `Esc` | 現在の実行を中断（アイドル時の Esc はプログラム終了） |
| `/help` | `/?` | コマンドヘルプ |
| `/quit` | `/exit` · `Ctrl-D` | SearchOS を終了 |

`/effort` の 4 段階予算一覧（グローバル settings を変更し、現在のセッションに即時反映。並列サブエージェント数は 8 固定でレベルによって変わりません）：

| レベル | オーケストレーションイテレーション | エージェントごとの検索数 | 実行時間上限 | ルーティング top-k |
| --- | :---: | :---: | :---: | :---: |
| `low` | 25 | 10 | 10 min | 20 |
| `medium`（デフォルト） | 50 | 20 | 30 min | 40 |
| `high` | 100 | 35 | 60 min | 60 |
| `max` | 150 | 50 | 120 min | 80 |

## 🧰 スキルシステム

3 カテゴリのスキルが [`searchos/skills/library/`](../searchos/skills/library/) に統一配置されています：

| カテゴリ | 数量 | 説明 |
| --- | --- | --- |
| **access** | 248 | サイトレベルのデータ取得。ドメイン名で命名（例：`en_wikipedia_org`）。URL マッチで自動ルーティング、または typed ツールとしてサブエージェントが能動的に呼び出し |
| **strategy** | 40+ | 推論方法論：`ranking_top_n`、`entity_disambiguation`、`multi_hop_bridge`…。アンチパターンのチェックリストを添付可能 |
| **orchestrator** | 若干 | オーケストレーション層の方法論。playbook として丸ごと注入 |

実行時は LLM ルーターが access カタログをクエリ関連の top-k に事前フィルタリング（fail-open）。サブエージェント派遣時に携行できるスキルは最大 3 つ。どの access スキルにもマッチしないページは汎用の抽出ミドルウェアにフォールバックします。

```bash
SEARCHOS_SKILL_ONLY=en_wikipedia_org,ranking_top_n   # ホワイトリスト
SEARCHOS_SKILL_LAYERS_DISABLED=access                # 層単位で無効化
SEARCHOS_SKILLS_DISABLED=1                           # すべて無効化
```

セッション終了後、高頻度ドメインを自動マイニングして新しい access スキルを焼き込むこともできます（`SF_ENABLE_ACCESS_SKILL_GENERATION`、デフォルトはオフ）。

## 📊 評価

**WideSearch**（ワイドテーブル検索）と **GISA**（オープンドメイン情報検索）で、2 つのシングルエージェントベースライン（ReAct / Plan-and-Solve）と 3 つのマルチエージェントシステム（Table-as-Search / A-MapReduce / Web2BigTable）と比較。スコアはすべて **max@3**（各問題を 3 回実行して最良値、×100）、**太字**は各行の最高値。*Item* はセルごとに独立採点、*Row* は行全体の正解が必要です。

| Benchmark | 指標 | ReAct | Plan-and-Solve | Table-as-Search | A-MapReduce | Web2BigTable | **SearchOS** |
| --- | --- | :---: | :---: | :---: | :---: | :---: | :---: |
| WideSearch | Item · Precision | 82.9 | 83.8 | 82.4 | 83.1 | 78.3 | **83.9** |
| | Item · Recall | 70.2 | 72.9 | 73.5 | 74.2 | 73.4 | **79.7** |
| | Item · F1 | 72.9 | 75.2 | 75.4 | 76.0 | 73.8 | **80.3** |
| | Row · Precision | 58.0 | 58.7 | 57.1 | 56.9 | 57.5 | **59.0** |
| | Row · Recall | 48.8 | 50.2 | 51.6 | 49.8 | 54.0 | **55.8** |
| | Row · F1 | 50.9 | 52.2 | 52.7 | 51.4 | 54.5 | **56.5** |
| GISA | Table · Item · F1 | 74.8 | 71.2 | 73.4 | 72.5 | 68.1 | **76.9** |
| | Table · Row · F1 | 58.1 | 50.7 | 54.1 | 52.1 | 45.3 | **59.7** |
| | Set · F1 | 61.6 | 63.1 | 60.9 | 62.5 | 56.7 | **76.5** |
| | List · F1 | 67.1 | 53.8 | 54.2 | 57.4 | 65.5 | **68.1** |
| | Item · EM | 0.0 | 16.7 | 16.7 | 33.3 | **50.0** | **50.0** |

SearchOS は両ベンチマークの全 F1 でリードし、その向上は主に**リコール**によるものです——カバレッジマップ駆動の派遣が、すべてのスキーマセルに出典付きの値が入るまで空セルを埋め続けます。完全な集合を列挙する **Set · F1 は次点ベースラインを +13.4 上回りました**。

## 🗺️ ロードマップ

SearchOS は現在も活発に開発されています。以下は現時点での主な優先事項であり、プロジェクトや研究の進展に応じて変更される可能性があります。

- [ ] **SearchOS テクニカルレポート**——システム設計、階層型 Skill アーキテクチャ、評価手法、再現可能な実験結果を詳述したテクニカルレポートを公開します。
- [ ] **自動 Skill 生成パイプライン**——再利用可能な検索 Skill の発見、生成、検証、継続的な保守を担うエンドツーエンドのパイプラインを開発します。技術的な詳細は今後の研究で紹介する予定です。
- [ ] **マルチモーダル検索**——検索とエビデンスのグラウンディングを、テキストから画像、図表、音声、動画へ拡張します。
- [ ] **データソース対応の拡充**——学術、企業、各専門領域の情報源との連携を追加します。

> このロードマップは現在の優先事項を示すもので、リリース時期を確約するものではありません。GitHub Issues からの提案やコントリビューションを歓迎します。

## 🗂️ プロジェクト構成

```
searchos/
├── agents/        Orchestrator と Explore、Search、オプション Writer agent
├── harness/       SearchSession、Context/Sensor/Evidence Intake、修復計画、合成、テレメトリ
├── socm/          共有検索状態：Frontier / Evidence Graph / Coverage Map / Strategy
├── tools/         ロール別ツール：schema、tasks、writer、simple_browser …
├── skills/        契約/manifest、routing、隔離 runtime、creation/evolution、ライブラリ
├── tui/           Textual UI：ライブ表示、復元、設定、Skill、追問、介入
├── config/        Provider、モデルカード/ロール、レート制限、effort、共有設定 overlay
└── cli.py         `searchos` / `python -m searchos` エントリポイント

web/api/           FastAPI REST/WS：実行、履歴資産、snapshot/branch、repair、設定、Skill jobs
web/frontend/      Next.js 研究ワークスペース：composer、live run、evidence、versions、usage、history

eval/              評価フレームワーク：run.py エントリ、runner、benchmarks、scorers、reformat
datasets/          同梱の WideSearch / GISA ベンチマークデータ
eval_results/      評価出力（1 問 1 ディレクトリ、完全にリプレイ可能なセッション付き）
searchos_workspace/ インタラクティブ実行のセッションワークスペース（タイムスタンプディレクトリ）
```

## 👥 Authors

<p align="center">
  <strong>Yuyao Zhang</strong><sup>1,2,*,‡</sup> ·
  <strong>Junjie Gao</strong><sup>2,*</sup> ·
  <strong>Zhengxian Wu</strong><sup>2</sup> ·
  <strong>Jiaming Fan</strong><sup>2</sup> ·
  <strong>Jin Zhang</strong><sup>2</sup> ·
  <strong>Shihan Ma</strong><sup>2</sup> ·
  <strong>Yao Yao</strong><sup>2</sup> ·
  <strong>Weiran Qi</strong><sup>2</sup> ·
  <strong>Guiyu Ma</strong><sup>2</sup> ·
  <strong>Xingzhong Xu</strong><sup>2</sup> ·
  <strong>Kai Yang</strong><sup>2</sup> ·
  <strong>Ji-Rong Wen</strong><sup>1</sup> ·
  <strong>Zhicheng Dou</strong><sup>1,†</sup>
</p>

<p align="center"><sup>1</sup> Renmin University of China · <sup>2</sup> Ant Group</p>

## 🙏 Acknowledgements

SearchOS は、上記の著者とコントリビューターの協力によって開発されました。プロジェクトを通じた Ant Insurance の力強いサポートに感謝します。

## 📚 Citation

SearchOS が研究に役立った場合は、[論文](https://arxiv.org/abs/2607.15257)を引用してください：

```bibtex
@article{zhang2026searchos,
  title={SearchOS-V1: Towards Robust Open-Domain Information-Seeking Agent Collaboration},
  author={Zhang, Yuyao and Gao, Junjie and Wu, Zhengxian and Fan, Jiaming and Zhang, Jin and Ma, Shihan and Yao, Yao and Qi, Weiran and Jin, Chuyan and Ma, Guiyu and others},
  journal={arXiv preprint arXiv:2607.15257},
  year={2026}
}
```

## 📄 License

[MIT License](../LICENSE) の下で公開されています。ソースコード内のコメントに関する追加条項は [LEGAL.md](../LEGAL.md) を参照してください。
