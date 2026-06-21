#!/usr/bin/env python3
"""
event-sort.py  ── イベント連動キュー並び替えスクリプト

使い方:
  python event-sort.py --event マラソン --start 2026-07-05
  python event-sort.py --event マラソン --start 2026-07-05 --dry-run  # プレビューのみ

イベントタグの書き方（post-queue.md 内の投稿に追記）:
  <!-- event: マラソン -->
  <!-- event: スーパーSALE -->
  <!-- event: 5と0 -->
  <!-- event: 値上げ前 -->
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

QUEUE_FILE = Path(__file__).parent / "post-queue.md"

HEADER = (
    "# post-queue.md ── 投稿待ちキュー\n"
    "ライターが作成した投稿をここに追加する。\n"
    "ポスターは一番上の投稿を取り出してThreadsに投稿する。\n"
    "投稿済みのものはここから削除してpost-history.mdに移す。\n\n"
    "> ⚠️ **【必須】このファイルを更新したら必ず `git push` すること**\n"
    "> GitHub Actionsはこのファイルの**GitHub上のバージョン**を読む。\n"
    "> pushしないと新しい投稿は一切自動投稿されない。\n\n"
    "---\n\n"
)


def load_posts():
    text = QUEUE_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    posts = [b.strip() for b in blocks if re.search(r"## 投稿[\w-]+", b)]
    return posts


def get_event_tag(block):
    m = re.search(r"<!--\s*event:\s*(.+?)\s*-->", block)
    return m.group(1).strip() if m else "通常"


def get_post_id(block):
    m = re.search(r"## 投稿([\w-]+)", block)
    return m.group(1) if m else "?"


def save_posts(posts):
    content = HEADER + "\n\n---\n\n".join(posts) + "\n" if posts else HEADER
    QUEUE_FILE.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="イベント連動キュー並び替え")
    parser.add_argument("--event",   required=True, help="イベント名（例: マラソン）")
    parser.add_argument("--start",   required=True, help="イベント開始日 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（ファイル変更なし）")
    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    except ValueError:
        print(f"❌ 日付フォーマットエラー: {args.start}（正しい形式: YYYY-MM-DD）")
        sys.exit(1)

    posts = load_posts()
    if not posts:
        print("キューが空です。")
        return

    event_posts  = [p for p in posts if get_event_tag(p) == args.event]
    normal_posts = [p for p in posts if get_event_tag(p) != args.event]

    if not event_posts:
        print(f"⚠️  イベントタグ「{args.event}」の投稿が見つかりません。")
        print(f"   post-queue.md の該当投稿に以下を追記してください:")
        print(f"   <!-- event: {args.event} -->")
        return

    # 1日1投稿として、イベント前日に投稿が来るよう計算
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_until = (start_date - today).days
    # 前日に配置。当日以降なら末尾に移動
    insert_pos = max(0, min(days_until - 1, len(normal_posts)))

    new_order = normal_posts[:insert_pos] + event_posts + normal_posts[insert_pos:]

    # プレビュー表示
    print(f"\n📅 イベント「{args.event}」開始: {args.start}（今日から {days_until} 日後）")
    print(f"   イベント向け投稿 {len(event_posts)} 本 → {insert_pos + 1} 番目に配置\n")
    print("【並び替え後のキュー】")
    for i, post in enumerate(new_order):
        pid  = get_post_id(post)
        tag  = get_event_tag(post)
        mark = f"  ← 🎯 {args.event}" if tag == args.event else ""
        print(f"  {i+1:2d}. 投稿{pid}{mark}")

    if args.dry_run:
        print("\n（--dry-run モード: ファイルは変更されていません）")
        return

    save_posts(new_order)
    print(f"\n✅ 並び替え完了")
    print("次のステップ: git add skills/queue/post-queue.md && git commit -m 'chore: イベント連動キュー並び替え' && git push")


if __name__ == "__main__":
    main()
