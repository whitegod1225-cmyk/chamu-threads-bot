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
import sys
 
import os
from dotenv import load_dotenv
if Path(".env").exists():
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="cp932")
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")
 
QUEUE_FILE = Path(__file__).parent / "post-queue.md"
DONE_FILE  = Path(__file__).parent / "post-history.md"
LOG_FILE   = Path(__file__).parent / "post-log.txt"
LOCK_FILE  = Path(__file__).parent / "post.lock"
 
 
def log(msg):
    """ログファイルとコンソールに同時出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
 
 
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
    header = (
        "# post-queue.md ── 投稿待ちキュー\n"
        "ライターが作成した投稿をここに追加する。\n"
        "ポスターは一番上の投稿を取り出してThreadsに投稿する。\n"
        "投稿済みのものはここから削除してpost-history.mdに移す。\n\n"
        "---\n\n"
    )
    QUEUE_FILE.write_text(
        header + "\n\n---\n\n".join(posts) + "\n",
        encoding="utf-8"
    )
 
 
def append_done(block, post_id=None, error=None):
    """投稿済みブロックをpost-history.mdへ追記"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = f"投稿ID: {post_id}" if post_id else f"エラー: {error}"
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(f"<!-- 処理日時: {timestamp} | {status} -->\n{block}\n\n---\n\n")
 
 
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
 
 
def acquire_lock():
    """二重起動防止ロック。すでに実行中なら False を返す"""
    if LOCK_FILE.exists():
        # ロックファイルが古すぎる場合（30分超）は強制解除
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age > 1800:
            log(f"古いロックファイルを強制削除（{int(age)}秒経過）")
            LOCK_FILE.unlink()
        else:
            return False
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True
 
 
def release_lock():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
 
 
def has_placeholder(text):
    """【リンク】などの未置換プレースホルダーが残っていないか確認"""
    return "【リンク】" in text or "【URL】" in text
 
 
def main():
    log("===== post.py 起動 =====")
 
    # ── 二重起動チェック ──
    if not acquire_lock():
        log("別のプロセスが実行中のため終了します（二重起動防止）")
        sys.exit(0)
 
    try:
        posts = load_queue()
        if not posts:
            log("投稿がありません。終了します。")
            return
 
        log(f"キュー件数: {len(posts)}件")
 
        block = posts[0]
        body = extract_body(block)
        reply = extract_reply(block)
 
        # ── 本文なしチェック ──
        if not body:
            log("本文が見つかりません。スキップしてhistoryへ移動します。")
            append_done(block, error="本文なし・スキップ")
            save_queue(posts[1:])
            log(f"残りキュー: {len(posts)-1}件")
            return
 
        # ── 【リンク】プレースホルダーチェック ──
        if has_placeholder(body) or (reply and has_placeholder(reply)):
            log("【リンク】プレースホルダーが残っています。手動でURLを入力後、再実行してください。")
            log(f"対象ブロック: {block[:80]}...")
            # キューには残したまま終了（手動対応待ち）
            sys.exit(0)
 
        post_id = None
        try:
            log(f"投稿開始:\n{body}")
            post_id = api_post(body)
            log(f"投稿完了！ ID: {post_id}")
 
            if reply:
                log(f"セルフリプライ開始:\n{reply}")
                reply_id = api_reply(reply, post_id)
                log(f"リプライ完了！ ID: {reply_id}")
 
        except Exception as e:
            log(f"APIエラー: {e}")
            # エラーでもキューから移動（同じ投稿の繰り返し防止）
            append_done(block, error=str(e))
            save_queue(posts[1:])
            log(f"エラーのためスキップ。残りキュー: {len(posts)-1}件")
            sys.exit(1)
 
        # 正常完了時の移動
        append_done(block, post_id=post_id)
        save_queue(posts[1:])
        log(f"キュー移動完了。残りキュー: {len(posts)-1}件")
 
    finally:
        release_lock()
 
 
if __name__ == "__main__":
    main()