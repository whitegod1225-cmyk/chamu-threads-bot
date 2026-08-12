# flow-tracking.md ── 流入元追跡（UTM相当）

note.comのリンクに `?from=XX` パラメータを付けることで、
どこからの流入がnoteアクセスを生んでいるかを手動で把握する。

> **運用の考え方**：note.comは`?from=`を解析しない。
> このファイルで「いつ・どこにリンクを置いたか」を記録しておき、
> noteのアクセス数増減とつき合わせて流入源を推定する。

---

## リンク配置マスタ

| 配置場所 | `?from=`マーカー | 対象note | 設置日 | 備考 |
|---------|---------------|---------|-------|------|
| Threadsプロフィール欄 | `from=profile` | （設置したnoteのURL） | 未設置 | bio内リンク1本のみ |
| ピン留め投稿（固定投稿） | `from=pin` | （設置したnoteのURL） | 未設置 | 最新の重要noteをpin |
| 発達note01 末尾CTA | `from=note01` | note02以降へのリンク | 未設置 | 無料note連鎖誘導 |
| 発達note02 末尾CTA | `from=note02` | note03以降へのリンク | 未設置 | 無料note連鎖誘導 |
| 発達note03 末尾CTA | `from=note03` | note04へのリンク | 未設置 | 無料note連鎖誘導 |
| 発達note04 末尾CTA | `from=note04` | 有料note（設置時更新） | 未設置 | 最終誘導 |
| Threads投稿（発達テーマ） | `from=th_hattatsu` | 発達シリーズnote | キュー投稿時に付与 | 投稿ごと共通マーカー |
| Threads投稿（声かけテーマ） | `from=th_koe` | 声かけnote | キュー投稿時に付与 | |
| Threads投稿（アフィリ）| `from=th_affi` | （対象note） | キュー投稿時に付与 | アフィリ投稿は別マーカー |

---

## 発達シリーズ note URL（マーカー付き）

| # | タイトル | 素のURL | `?from=profile` 付きURL |
|---|---------|--------|------------------------|
| 01 | 発達の統計データ | `https://note.com/hot_phlox7660/n/n52f7d149156e` | `...n52f7d149156e?from=profile` |
| 02 | 発達検査を受ける前に | `https://note.com/hot_phlox7660/n/nce2c5917013d` | `...nce2c5917013d?from=profile` |
| 03 | 療育って何をするの？ | `https://note.com/hot_phlox7660/n/n770680e4079d` | `...n770680e4079d?from=profile` |
| 04 | 相談先の選び方 | `https://note.com/hot_phlox7660/n/n6e5dc9b4f8a5` | `...n6e5dc9b4f8a5?from=profile` |

---

## 手動追跡ログ

投稿にnoteリンクを貼ったとき、ここに記録する。
その後noteのアクセス数と照合して流入推定をする。

| 記録日 | 配置場所 | リンク先note# | 使用マーカー | noteアクセス増（翌日確認） |
|-------|---------|------------|-----------|----------------------|
| （例）2026-08-12 | Threads投稿（発達） | note04 | `from=th_hattatsu` | 未確認 |

---

## 運用ルール

1. **新しいnoteをリンクに貼るとき**
   - このファイルの「リンク配置マスタ」に行を追加する
   - `?from=XX` の`XX`は上のマーカー一覧から選ぶ
   - 投稿番号ベースのマーカーは不要（テーマ別で十分）

2. **Threads投稿でnoteを誘導するとき**
   - コメント欄のURLに必ずマーカーを付与する
   - `/writer` がnote誘導投稿を作るときはこのファイルから該当マーカーを参照する

3. **月次確認**（`/knowledge-review`と同時）
   - 手動追跡ログの「noteアクセス増」列を埋める
   - アクセスが多いマーカー = 効いている配置 → その配置を優先する

---

## 次ステップ（受け皿ができたら更新）

LINE公式アカウントまたはOpenChatができた場合：
- そのURLにも同様に `?from=XX` を付与して配置マスタを更新する
- `from=line_profile`（プロフのLINEリンク）、`from=line_pin`（ピン留めのLINEリンク）等

