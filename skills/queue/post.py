import random
import time

# ±10分のランダム待機（-600秒〜+600秒）
wait = random.randint(-600, 600)
if wait > 0:
    print(f"{wait}秒待機します...")
    time.sleep(wait)
import urllib.request
import urllib.parse
import json
import re
from datetime import datetime
from pathlib import Path

import os
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "THAAX6Vv488utBUVJxVDBwU3drMElFVXNfSHpyRUJ1VTlpSF9NcjA4OG9kQTh")
USER_ID = os.environ.get("THREADS_USER_ID", "34618526867762918")

QUEUE_FILE = Path(__file__).parent / "post-queue.md"
DONE_FILE  = Path(__file__).parent / "post-history.md"

def load_queue():
    text = QUEUE_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    posts = [b.strip() for b in blocks if re.search(r"## 投稿\d+", b)]
    return posts

def extract_body(block):
    m = re.search(r"\*\*本文\*\*\n(.+?)(?=\n\*\*|$)", block, re.DOTALL)
    return m.group(1).strip() if m else None

def extract_reply(block):
    m = re.search(r"\*\*コメント欄（セルフリプライ用）\*\*\n(.+?)$", block, re.DOTALL)
    return m.group(1).strip() if m else None

def save_queue(posts):
    header = "# post-queue.md ── 投稿待ちキュー\nライターが作成した投稿をここに追加する。\nポスターは一番上の投稿を取り出してThreadsに投稿する。\n投稿済みのものはここから削除してpost-history.mdに移す。\n\n---\n\n"
    QUEUE_FILE.write_text(header + "\n\n---\n\n".join(posts) + "\n", encoding="utf-8")

def append_done(block):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(f"<!-- 投稿済み: {timestamp} -->\n{block}\n\n---\n\n")

def api_post(text):
    base = "https://graph.threads.net/v1.0"
    params1 = urllib.parse.urlencode({
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN
    }).encode()
    req1 = urllib.request.Request(f"{base}/{USER_ID}/threads", data=params1, method="POST")
    with urllib.request.urlopen(req1) as res:
        container_id = json.loads(res.read())["id"]

    params2 = urllib.parse.urlencode({
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }).encode()
    req2 = urllib.request.Request(f"{base}/{USER_ID}/threads_publish", data=params2, method="POST")
    with urllib.request.urlopen(req2) as res:
        return json.loads(res.read())["id"]

def api_reply(text, reply_to_id):
    base = "https://graph.threads.net/v1.0"
    params1 = urllib.parse.urlencode({
        "media_type": "TEXT",
        "text": text,
        "reply_to_id": reply_to_id,
        "access_token": ACCESS_TOKEN
    }).encode()
    req1 = urllib.request.Request(f"{base}/{USER_ID}/threads", data=params1, method="POST")
    with urllib.request.urlopen(req1) as res:
        container_id = json.loads(res.read())["id"]

    params2 = urllib.parse.urlencode({
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }).encode()
    req2 = urllib.request.Request(f"{base}/{USER_ID}/threads_publish", data=params2, method="POST")
    with urllib.request.urlopen(req2) as res:
        return json.loads(res.read())["id"]

def main():
    posts = load_queue()
    if not posts:
        print("投稿がありません。")
        return

    block = posts[0]
    body = extract_body(block)
    reply = extract_reply(block)

    if not body:
        print("本文が見つかりません。")
        return

    print(f"投稿します:\n{body}\n")
    post_id = api_post(body)
    print(f"投稿完了！ ID: {post_id}")

    if reply:
        print(f"セルフリプライ:\n{reply}\n")
        reply_id = api_reply(reply, post_id)
        print(f"リプライ完了！ ID: {reply_id}")

    append_done(block)
    save_queue(posts[1:])
    print(f"残りキュー: {len(posts)-1}件")

if __name__ == "__main__":
    main()