# CLAUDE.md ── ちゃむ。自動運用システム設定

## ⚠️ 最重要ルール①：型A（自己紹介型）10投稿ごと挿入ルール

**post-queue.mdに投稿を追加するときは必ず以下をチェックする。**

1. キューの末尾から逆算して**直近10投稿に型Aが含まれているか**確認する
2. 含まれていない場合は `/intro-writer` で型Aを1本生成してから追加する
3. 含まれている場合は「あとX投稿で次の型Aが必要」とユーザーに報告する

対象スキル：`/writer` `/affiliate-writer` `/zu-writer` `/intro-writer` すべて

---

## ⚠️ 最重要ルール②：post-queue.md を更新したら必ず git push する
post-queue.md・next-topics.md・knowledgeファイルを変更した後は、
必ず以下を実行してGitHubに反映させること。
反映しないとGitHub Actionsが変更を認識できず、自動投稿が止まる。

```
git add skills/queue/post-queue.md （変更したファイルを指定）
git commit -m "chore: ..."
git push origin main
```

**Claudeへの指示**: post-queue.mdを編集した際は、作業完了の報告とともに
必ずユーザーに `git push` を促すこと。

## このプロジェクトについて
Threadsアカウント「ちゃむ。」の投稿を自動化するシステム。
6つのエージェントがファイルを介して連携して動く。

## 読み込むファイル一覧
- skills/knowledge/01_profile.md（人物設定）
- skills/knowledge/02_target.md（ターゲット）
- skills/knowledge/03_writing.md（文体ルール）
- skills/knowledge/04_knowledge.md（コンテンツジャンル）
- skills/knowledge/05_affiliate.md（アフィリエイト方針）
- skills/knowledge/06_schedule.md（投稿スケジュール）
- skills/knowledge/07_ng-rules.md（NGルール）
- skills/knowledge/08_strategy.md（戦略）
- skills/knowledge/09_references.md（参考投稿ストック）
- skills/knowledge/10_idea-generation.md（バズテーマ独自案生成プロンプト集）
- skills/knowledge/11_monetize-prompts.md（マネタイズ・成長プロンプト集）
- skills/knowledge/affiliate-research/（アフィリエイト投稿方法の参考記事ストック ※_index.mdを先に読むこと）
- skills/knowledge/affiliate-examples/（アフィリエイト投稿の文体・構成サンプル集 ※/affiliate-writerが型として参照する ※_index.mdを先に読むこと）
- skills/knowledge/14_zu-writer.md（カピおじ図解プロンプト生成パラメータ ※/zu-writerが参照する）

## キューファイル
- skills/queue/next-topics.md（通常投稿の次のテーマ）
- skills/queue/post-queue.md（投稿キュー ※通常投稿・アフィリエイト投稿どちらも可）
- skills/queue/post-history.md（通常投稿履歴）
- skills/queue/analysis-latest.md（最新分析結果）
- skills/queue/affiliate-topics.md（アフィリエイト商品候補リスト ※next-topics.mdのアフィリエイト版）
- skills/queue/affiliate-queue.md（アフィリエイト投稿の下書きエリア ※文体調整後にpost-queue.mdへ移動する）
- skills/queue/affiliate-history.md（アフィリエイト投稿履歴・効果追跡）

## スキル一覧

### /researcher
YouTubeやInstagramで育児系のバズコンテンツをリサーチして、
ちゃむ。のジャンルで使えるネタ・構成・知識をまとめてファイルに保存する。
- 検索キーワードは04_knowledge.mdのテーマカテゴリから自動選択
- 前回調べた内容と重複しないようにする
- 結果はskills/knowledge/research_latest.mdに保存
- 次回調べるべきキーワードも提案する

### /analyst
post-history.mdの投稿データを分析して、
次に書くべきテーマを3つ提案してnext-topics.mdに保存する。
- 一番伸びた投稿と伸びなかった投稿を特定する
- 伸びなかった理由を1行目・構成・テーマの観点で分析する
- 次のテーマは「テーマ名・切り口・1行目の案」をセットで書く
- 抽象的なアドバイスは禁止。必ず具体的な文章で書く

### /writer
next-topics.mdからテーマを1つ選んでThreads投稿を3本作り、
post-queue.mdに追加する。
- 01_profile.md〜08_strategy.mdを全部読み込んでから書く
- 09_references.mdのバズ投稿から構成を1つ参考にする（丸パクリ禁止）
- 1行目は5案出して一番強いものを選ぶ
- 本文200〜350文字
- コメント欄用の続きも書く（本文で完結させない）
- 07_ng-rules.mdのセルフチェックを必ず実行する
- 作った投稿はpost-queue.mdに追記する

### /poster
post-queue.mdの一番上の投稿をThreads APIで投稿する。
- 投稿前に07_ng-rules.mdのチェックを実行する
- 本文を投稿後、コメント欄の続きをセルフリプライで投稿する
- 投稿完了後、post-queue.mdから該当投稿を削除する
- post-history.mdに投稿日時とpost_idを記録する
- 1回の実行で1投稿のみ。複数投稿しない
- APIエラーは1回だけリトライ。2回失敗したら止める

### /fetcher
post-history.mdを読んで、まだデータ取得していない投稿の
エンゲージメント（いいね・コメント・リポスト・表示数）をThreads APIで取得する。
- 投稿から24時間以上経ったものだけ対象にする
- 取得したデータをpost-history.mdの該当行に追記する
- metrics_fetchedをtrueに変更する
- コメントの中から「質問」を自動で見つけてanalysis-latest.mdに追記する

### /replyer
post-history.mdを読んで、対応パターンの投稿についたコメントへの返答文を生成する。

**対応する投稿パターン（これ以外はスキップ）**
- 型3・型8（ハック集・NG/OK型）→ 番号コメント・保存報告への返答
- 型9（助けて募集型）→ 経験シェアコメントへの返答
- シリーズ型（投稿237〜241）→ 「続き楽しみ」「見てます」系への返答
- 型12（フォロー価値提示型）→ フォロー感謝コメントへの返答

**対応しない投稿パターン（必ずスキップ）**
- 型2（敗因報告型）・型7（概念誤用型）・型11（謎の場面目撃型）
- 「静かにいいね」系の型A・型F投稿
- 深い感情的相談・医療・発達に関わる質問

**返答ルール**
- 1〜2行以内。3行以上は書かない
- ちゃむ。の文体で書く。語尾は毎回変える
- 「ありがとうございます」は使わない→「ありがとう」「嬉しい」に変換
- AIっぽい定型文（「参考になれば嬉しいです」等）は全面禁止
- 番号のみのコメントには番号を引用して返す（「❸！コメントありがとう☻」等）
- 同じ返答パターンを3件以上連続で使わない
- 投稿から1時間以内のコメントを最優先で処理する
- 24時間以上経過したコメントは対象外

**実行方法**
1. post-history.mdから直近48時間以内の「対応パターン」投稿を抽出する
2. Threads APIでそれらのコメントを取得する
3. 未返答コメントに対して返答文を生成し、一覧として出力する
4. 出力を確認後、手動またはAPI経由で返信する

### /supervisor
全ファイルの状態をチェックして、自動運用が正常に動いているか診断する。
- 投稿が2日以上止まっていないか確認する
- next-topics.mdのテーマが残り1つ以下なら警告する
- post-queue.mdの投稿が5件以上溜まっていたら警告する
- metrics_fetchedがfalseのまま48時間以上経過している投稿を警告する
- 問題があれば原因と次にやるべきことを具体的に提案する
- 結果をsupervisor-report.mdに保存する

## 環境変数
- THREADS_ACCESS_TOKEN：Threads APIのアクセストークン（.envに保存）
- THREADS_USER_ID：ThreadsのユーザーID（.envに保存）
