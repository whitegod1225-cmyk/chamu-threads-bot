"""
tag_consultation.py
育児相談の要約を蓄積するツール。

重要な運用ルール:
  ネット上の相談投稿（Yahoo知恵袋・ガールズちゃんねるなど）を自動収集・コピーしない。
  著作権侵害のリスクがあるため、このツールでは行わない。
  必ず「ちゃむ。が自分の言葉で要約したテキスト」だけを入力すること。
  このスクリプトは、その要約に対して悩みタクソノミーのタグ付けを支援するだけ。

使い方:
  python tag_consultation.py add --summary "夜泣きがひどくて母親が限界だった相談。子は8ヶ月。"
  → AIがタクソノミーに沿ったタグ（大分類/中分類/年齢帯/親の状態）を提案 →
    y（そのまま保存）/ n（キャンセル）/ edit（修正して保存）で確認 → 保存

  python tag_consultation.py list --unused
  → まだ note記事・Threads投稿に使っていない相談だけを表示

  python tag_consultation.py mark-used --id C-0001 --note-id N-0012
  → 採用した相談を使用済みにマーク
"""

import os
import sys
import json
import argparse
import time
import urllib.request

TOKEN_ENV = "ANTHROPIC_API_KEY"
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

HERE = os.path.dirname(__file__)
LOG_PATH = os.path.join(HERE, "consultation_log.json")
TAXONOMY_PATH = os.path.join(HERE, "taxonomy_categories.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_api_key():
    key = os.environ.get(TOKEN_ENV)
    if not key:
        sys.exit(f"エラー: 環境変数 {TOKEN_ENV} を設定してください。")
    return key


def call_claude(system_prompt, user_prompt):
    key = get_api_key()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 500,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return text


def suggest_tags(summary):
    taxonomy = load_json(TAXONOMY_PATH, {})
    system_prompt = (
        "あなたは育児相談の分類アシスタントです。与えられた相談要約に対して、"
        "以下のタクソノミーの中から最も近い「大分類」と「中分類」を1つずつ選び、"
        "対象年齢帯と親の状態タグを推定してください。"
        "出力は必ずJSONのみ。前置き・後書きなし。"
        f"タクソノミー: {json.dumps(taxonomy, ensure_ascii=False)}\n"
        "出力フィールド: 大分類, 中分類, 対象年齢帯, 親の状態タグ"
    )
    raw = call_claude(system_prompt, summary)
    cleaned = raw.strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def cmd_add(args):
    summary = args.summary
    if len(summary) > 800:
        print("警告: 要約が長すぎます（800字超）。別テキストのコピペになっていないか確認してください。")

    print("AIによるタグ提案を取得中...")
    try:
        tags = suggest_tags(summary)
    except Exception as e:
        sys.exit(f"タグ提案の取得に失敗しました: {e}")

    print(json.dumps(tags, ensure_ascii=False, indent=2))
    ans = input("この内容で保存しますか？ (y/n/edit): ").strip().lower()
    if ans == "edit":
        for key in list(tags.keys()):
            new_val = input(f"{key} [{tags[key]}]: ").strip()
            if new_val:
                tags[key] = new_val
    elif ans != "y":
        print("保存をキャンセルしました。")
        return

    log = load_json(LOG_PATH, [])
    new_id = f"C-{len(log)+1:04d}"
    record = {
        "id": new_id,
        "date": time.strftime("%Y-%m-%d"),
        "summary": summary,
        "大分類": tags.get("大分類"),
        "中分類": tags.get("中分類"),
        "対象年齢帯": tags.get("対象年齢帯"),
        "親の状態タグ": tags.get("親の状態タグ"),
        "used_in_note": None,
        "used_in_threads": None,
    }
    log.append(record)
    save_json(LOG_PATH, log)
    print(f"保存しました: {new_id}")


def cmd_list(args):
    log = load_json(LOG_PATH, [])
    if args.unused:
        log = [r for r in log if not r.get("used_in_note") and not r.get("used_in_threads")]
    if not log:
        print("該当する相談がありません。")
        return
    for r in log:
        used = []
        if r.get("used_in_note"): used.append(f"note:{r['used_in_note']}")
        if r.get("used_in_threads"): used.append(f"threads:{r['used_in_threads']}")
        used_str = f" [{', '.join(used)}]" if used else ""
        print(f"[{r['id']}] {r['date']} {r.get('大分類')}/{r.get('中分類')} - {r['summary'][:50]}...{used_str}")
    print(f"合計: {len(log)}件")


def cmd_mark_used(args):
    log = load_json(LOG_PATH, [])
    found = False
    for r in log:
        if r["id"] == args.id:
            if args.note_id:
                r["used_in_note"] = args.note_id
            if args.threads_id:
                r["used_in_threads"] = args.threads_id
            found = True
            break
    if not found:
        sys.exit(f"エラー: ID {args.id} が見つかりませんでした。")
    save_json(LOG_PATH, log)
    print(f"{args.id} を使用済みにマークしました。")


def main():
    parser = argparse.ArgumentParser(description="相談要約の蓄積・タグ付けツール")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="相談要約を1件追加")
    p_add.add_argument("--summary", required=True, help="自分の言葉で書いた要約（元投稿のコピー禁止）")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="蓄積した相談一覧を表示")
    p_list.add_argument("--unused", action="store_true", help="まだ note/投稿に未使用のものだけ表示")
    p_list.set_defaults(func=cmd_list)

    p_mark = sub.add_parser("mark-used", help="相談を記事/投稿で使用済みにマーク")
    p_mark.add_argument("--id", required=True)
    p_mark.add_argument("--note-id", default=None)
    p_mark.add_argument("--threads-id", default=None)
    p_mark.set_defaults(func=cmd_mark_used)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
