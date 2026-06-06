import random
import time
import hashlib

import urllib.request
import urllib.parse
import urllib.error
import json
import re
from datetime import datetime
from pathlib import Path
import sys
import io

# Windows(cp932環境)でも絵文字を含む文字列を出力できるようにする
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
# CI環境(GitHub Actions)ではsecrets経由で環境変数が注入されるため.envは不要
if _env_path.exists() and not os.environ.get("CI"):
    for _enc in ("utf-8", "cp932", "utf-8-sig"):
        try:
            load_dotenv(dotenv_path=_env_path, encoding=_enc)
            break
        except UnicodeDecodeError:
            continue
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")

QUEUE_FILE = Path(__file__).parent / "post-queue.md"
DONE_FILE  = Path(__file__).parent / "post-history.md"
LOG_FILE   = Path(__file__).parent / "post-log.txt"
LOCK_FILE  = Path(__file__).parent / "post.lock"
HASH_FILE  = Path(__file__).parent / "last-post-hash.txt"


def log(msg):
    """ログファイルとコンソールに同時出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        # Windowsコンソール(cp932)が絵文字等を表示できない場合は代替文字で出力
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, errors="replace").decode(enc))
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


def extract_replies(block):
    """コメント欄を全て抽出して順番にリストで返す（1段・多段どちらも対応）"""
    sections = re.split(r"\n\*\*コメント欄.*?セルフリプライ用）\*\*\n", block)
    if len(sections) <= 1:
        return []
    return [s.strip() for s in sections[1:] if s.strip()]


def save_queue(posts):
    header = (
        "# post-queue.md ── 投稿待ちキュー\n"
        "ライターが作成した投稿をここに追加する。\n"
        "ポスターは一番上の投稿を取り出してThreadsに投稿する。\n"
        "投稿済みのものはここから削除してpost-history.mdに移す。\n\n"
        "> ⚠️ **【必須】このファイルを更新したら必ず `git push` すること**\n"
        "> GitHub Actionsはこのファイルの**GitHub上のバージョン**を読む。\n"
        "> pushしないと新しい投稿は一切自動投稿されない。\n\n"
        "---\n\n"
    )
    content = header + "\n\n---\n\n".join(posts) + "\n" if posts else header
    QUEUE_FILE.write_text(content, encoding="utf-8")


def append_done(block, post_id=None, error=None):
    """投稿済みブロックをpost-history.mdへ追記"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = f"投稿ID: {post_id}" if post_id else f"エラー: {error}"
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(f"<!-- 処理日時: {timestamp} | {status} -->\n{block}\n\n---\n\n")


def _urlopen(req, timeout=30):
    """urllib.request.urlopen のラッパー。HTTPErrorのレスポンスボディも取得する"""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"HTTP Error {e.code}: {e.reason} | response: {body}")


def api_post(text):
    base = "https://graph.threads.net/v1.0"
    params1 = urllib.parse.urlencode({
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN
    }).encode("utf-8")
    req1 = urllib.request.Request(f"{base}/{USER_ID}/threads", data=params1, method="POST")
    container_id = _urlopen(req1)["id"]

    # コンテナがThreads側に認識されるまで待機
    time.sleep(3)

    params2 = urllib.parse.urlencode({
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }).encode("utf-8")
    req2 = urllib.request.Request(f"{base}/{USER_ID}/threads_publish", data=params2, method="POST")
    return _urlopen(req2)["id"]


def api_reply(text, reply_to_id):
    base = "https://graph.threads.net/v1.0"
    params1 = urllib.parse.urlencode({
        "media_type": "TEXT",
        "text": text,
        "reply_to_id": reply_to_id,
        "access_token": ACCESS_TOKEN
    }).encode("utf-8")
    req1 = urllib.request.Request(f"{base}/{USER_ID}/threads", data=params1, method="POST")
    container_id = _urlopen(req1)["id"]

    # コンテナがThreads側に認識されるまで待機
    time.sleep(3)

    params2 = urllib.parse.urlencode({
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }).encode("utf-8")
    req2 = urllib.request.Request(f"{base}/{USER_ID}/threads_publish", data=params2, method="POST")
    return _urlopen(req2)["id"]


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


def get_body_hash(body):
    return hashlib.md5(body.encode("utf-8")).hexdigest()


def was_recently_posted(body):
    """直前の投稿と同じ本文なら True を返す（重複投稿防止）"""
    if not HASH_FILE.exists():
        return False
    return HASH_FILE.read_text(encoding="utf-8").strip() == get_body_hash(body)


def record_post_hash(body):
    HASH_FILE.write_text(get_body_hash(body), encoding="utf-8")


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
        replies = extract_replies(block)

        # ── 本文なしチェック ──
        if not body:
            log("本文が見つかりません。スキップしてhistoryへ移動します。")
            append_done(block, error="本文なし・スキップ")
            save_queue(posts[1:])
            log(f"残りキュー: {len(posts)-1}件")
            return

        # ── 【リンク】プレースホルダーチェック ──
        if has_placeholder(body) or any(has_placeholder(r) for r in replies):
            log("【リンク】プレースホルダーが残っています。手動でURLを入力後、再実行してください。")
            log(f"対象ブロック: {block[:80]}...")
            # キューには残したまま終了（手動対応待ち）
            sys.exit(0)

        # ── 重複投稿チェック ──
        if was_recently_posted(body):
            log("⚠️ 直前の投稿と同じ本文を検出。重複投稿を防ぐためスキップします。")
            append_done(block, error="重複投稿スキップ（直前と同一本文）")
            save_queue(posts[1:])
            log(f"残りキュー: {len(posts)-1}件")
            return

        # ── 本文投稿（最大2回リトライ） ──
        post_id = None
        last_error = None
        for attempt in range(2):
            try:
                log(f"投稿開始（試行{attempt + 1}回目）:\n{body}")
                post_id = api_post(body)
                log(f"投稿完了！ ID: {post_id}")
                last_error = None
                break
            except Exception as e:
                last_error = e
                log(f"投稿APIエラー（試行{attempt + 1}回目）: {e}")
                if attempt == 0:
                    log("5秒後にリトライします...")
                    time.sleep(5)

        if last_error is not None:
            append_done(block, error=str(last_error))
            save_queue(posts[1:])
            log(f"2回失敗のためスキップ。残りキュー: {len(posts)-1}件")
            sys.exit(1)

        # ── セルフリプライ（複数段チェーン対応・失敗しても本文投稿は成功しているのでキュー移動は行う） ──
        current_reply_to = post_id
        for i, reply_text in enumerate(replies):
            try:
                log(f"セルフリプライ{i+1}/{len(replies)}開始:\n{reply_text}")
                reply_id = api_reply(reply_text, current_reply_to)
                log(f"リプライ{i+1}完了！ ID: {reply_id}")
                current_reply_to = reply_id  # 次のリプライは前のリプライに連鎖
                if i < len(replies) - 1:
                    time.sleep(2)
            except Exception as e:
                log(f"リプライ{i+1}APIエラー（本文投稿は成功済み）: {e}")
                break

        # ── キュー移動（api_post成功時点で必ず実行） ──
        try:
            record_post_hash(body)
            append_done(block, post_id=post_id)
            save_queue(posts[1:])
            log(f"キュー移動完了。残りキュー: {len(posts)-1}件")
        except Exception as e:
            log(f"ファイル更新エラー（投稿はThreadsに公開済み）: {e}")
            sys.exit(1)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
