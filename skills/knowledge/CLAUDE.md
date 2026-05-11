# CLAUDE.md ── ちゃむ。自動運用システム設定

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

## キューファイル
- skills/queue/next-topics.md（次のテーマ）
- skills/queue/post-queue.md（投稿待ちキュー）
- skills/queue/post-history.md（投稿履歴）
- skills/queue/analysis-latest.md（最新分析結果）

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
