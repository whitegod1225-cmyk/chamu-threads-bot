#!/usr/bin/env python3
"""
event-prep.py  ── イベント事前仕込みアシスタント（案2）

使い方:
  python event-prep.py --event マラソン --start 2026-07-05

機能:
  1. affiliate-topics.md からイベント対応フラグが一致する未投稿候補を抽出
  2. post-queue.md / post-history.md と照合して「まだ投稿文がない候補」を特定
  3. /affiliate-writer に渡すブリーフを出力
  4. 並び替えコマンドをガイド表示

完全な仕込みフロー:
  ① python event-prep.py --event マラソン --start 2026-07-05   # 候補確認・ブリーフ出力
  ② Claude に貼り付けて /affiliate-writer で投稿文生成
  ③ 生成した投稿に <!-- event: マラソン --> タグを追加して post-queue.md へ
  ④ python event-sort.py --event マラソン --start 2026-07-05   # キュー並び替え
  ⑤ git push
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

QUEUE_FILE   = Path(__file__).parent / "post-queue.md"
HISTORY_FILE = Path(__file__).parent / "post-history.md"
TOPICS_FILE  = Path(__file__).parent / "affiliate-topics.md"

# イベント名 → 推奨投稿型
EVENT_TYPE_MAP = {
    "マラソン":    "S-19（ネガティブニュース→緊急性転換型）またはS-18（読者共犯型）",
    "スーパーSALE": "S-4（速報興奮型）またはS-6（ターゲット断言まとめ型）",
    "5と0":        "S-8（衝動購入報告型）またはS-18（読者共犯型）",
    "値上げ前":    "S-19（ネガティブニュース→緊急性転換型）一択",
    "再入荷":      "S-4（速報興奮型）またはS-17（感情爆発後悔型）",
}

# イベント名 → 仕込み推奨リードタイム（日数）
EVENT_LEADTIME = {
    "マラソン":    2,
    "スーパーSALE": 3,
    "5と0":        1,
    "値上げ前":    0,  # 発表直後に即仕込み
    "再入荷":      0,
}


def read_file_safe(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def extract_candidates(topics_text, event_name):
    """affiliate-topics.md からイベント対応・未投稿候補を抽出"""
    blocks = re.split(r"\n---\n", topics_text)
    candidates = []
    for block in blocks:
        if not re.search(r"## 候補\d+", block):
            continue
        event_field = re.search(r"\*\*イベント対応\*\*：(.+)", block)
        if not event_field:
            continue
        if event_name not in event_field.group(1):
            continue
        status = re.search(r"\*\*ステータス\*\*：(.+)", block)
        if status and "投稿済み" in status.group(1):
            continue
        candidates.append(block.strip())
    return candidates


def get_queued_products(text):
    """post-queue.md / post-history.md から商品名を抽出"""
    return set(re.findall(r"\*\*商品名\*\*：(.+)", text))


def parse_candidate(block):
    def field(key):
        m = re.search(rf"\*\*{key}\*\*：(.+)", block)
        return m.group(1).strip() if m else "未記入"

    title_m = re.search(r"## (候補\d+：.+)", block)
    return {
        "title":   title_m.group(1).strip() if title_m else "不明",
        "product": field("商品名"),
        "url":     field("アフィリエイトURL"),
        "angle":   field("投稿アングル"),
        "season":  field("時期"),
    }


def main():
    parser = argparse.ArgumentParser(description="イベント事前仕込みアシスタント")
    parser.add_argument("--event", required=True, help="イベント名（例: マラソン）")
    parser.add_argument("--start", required=True, help="イベント開始日 YYYY-MM-DD")
    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    except ValueError:
        print(f"❌ 日付フォーマットエラー: {args.start}（正しい形式: YYYY-MM-DD）")
        sys.exit(1)

    today      = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_until = (start_date - today).days
    leadtime   = EVENT_LEADTIME.get(args.event, 3)

    print(f"\n📅 イベント「{args.event}」まで {days_until} 日（開始: {args.start}）")
    if days_until <= leadtime:
        print(f"⚠️  推奨仕込みリードタイム（{leadtime}日前）を過ぎています。今すぐ仕込んでください。")
    else:
        deadline = (start_date.replace() - __import__('datetime').timedelta(days=leadtime)).strftime("%m/%d")
        print(f"   仕込み推奨期限: {deadline}（{leadtime}日前）まで")

    topics_text  = read_file_safe(TOPICS_FILE)
    queue_text   = read_file_safe(QUEUE_FILE)
    history_text = read_file_safe(HISTORY_FILE)

    if not topics_text:
        print("\n❌ affiliate-topics.md が見つかりません。")
        sys.exit(1)

    candidates  = extract_candidates(topics_text, args.event)
    queued      = get_queued_products(queue_text + history_text)
    new_cands   = [parse_candidate(c) for c in candidates
                   if parse_candidate(c)["product"] not in queued]

    # キューに既にあるイベント投稿を確認
    event_in_queue = len(re.findall(rf"<!--\s*event:\s*{re.escape(args.event)}\s*-->", queue_text))

    print(f"\n【現在のキュー状況】")
    print(f"  イベントタグ「{args.event}」付き投稿: {event_in_queue} 本")
    print(f"  affiliate-topics.md 未投稿候補: {len(new_cands)} 本")

    if not new_cands:
        print("\n✅ 新規生成が必要な候補はありません。")
        if event_in_queue > 0:
            print(f"   event-sort.py で並び替えを実行してください:")
            print(f"   python event-sort.py --event {args.event} --start {args.start}")
        return

    recommended_type = EVENT_TYPE_MAP.get(args.event, "S-4（速報興奮型）")

    print(f"\n【生成が必要な投稿: {len(new_cands)} 本】")
    print(f"  推奨型: {recommended_type}\n")
    print("=" * 60)
    print("以下を Claude に貼り付けて /affiliate-writer を実行してください")
    print("=" * 60)

    for i, info in enumerate(new_cands, 1):
        print(f"\n--- 投稿候補 {i} / {len(new_cands)} ---")
        print(f"商品名     : {info['product']}")
        print(f"アフィURL  : {info['url']}")
        print(f"投稿アングル: {info['angle']}")
        print(f"推奨型     : {recommended_type}")
        print(f"イベント   : {args.event}（{args.start}開始）")
        print(f"※ 生成後の投稿ブロックの先頭に以下を追加:")
        print(f"  <!-- event: {args.event} -->")

    print("\n" + "=" * 60)
    print("\n【次のステップ】")
    print(f"  1. 上記ブリーフをClaudeに渡して投稿文を生成")
    print(f"  2. 投稿に <!-- event: {args.event} --> タグを追加")
    print(f"  3. post-queue.md に追記して git push")
    print(f"  4. python event-sort.py --event {args.event} --start {args.start}")


if __name__ == "__main__":
    main()
