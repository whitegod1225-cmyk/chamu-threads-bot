"""
threads_insights.py
/fetcher（fetcher.md）の代替 or 補助CLIツール。
Threads Graph APIから最新メトリクスを取得してthreads_metrics_cache.jsonに保存する。

/fetcher（fetch_threads.py）が存在する場合はそちらが正として動く。
このファイルは: /fetcherが使えない環境・スクリプト自動化・テスト用途のために存在する。

使い方:
  python threads_insights.py
  → THREADS_ACCESS_TOKEN, THREADS_USER_ID 環境変数を参照してAPIコール
  → threads_metrics_cache.json を上書き更新

環境変数:
  THREADS_ACCESS_TOKEN: Threads Graph APIのアクセストークン（長期トークン推奨）
  THREADS_USER_ID:      ThreadsユーザーID（数字）
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse

HERE = os.path.dirname(__file__)
CACHE_PATH = os.path.join(HERE, "threads_metrics_cache.json")
META_PATH = os.path.join(HERE, "post_meta.json")

GRAPH_BASE = "https://graph.threads.net/v1.0"
METRICS_FIELDS = "id,timestamp,text,media_type,permalink,views,likes,replies,reposts,quotes"
MAX_POSTS = 100


def get_env(key):
    val = os.environ.get(key)
    if not val:
        sys.exit(f"エラー: 環境変数 {key} を設定してください。")
    return val


def api_get(path, params):
    url = f"{GRAPH_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_posts(user_id, access_token):
    data = api_get(
        f"{user_id}/threads",
        {"fields": METRICS_FIELDS, "limit": MAX_POSTS, "access_token": access_token},
    )
    return data.get("data", [])


def fetch_insights(media_id, access_token):
    try:
        data = api_get(
            f"{media_id}/insights",
            {"metric": "views,likes,replies,reposts,quotes", "access_token": access_token},
        )
        result = {}
        for item in data.get("data", []):
            name = item.get("name")
            values = item.get("values", [])
            if values:
                result[name] = values[-1].get("value", 0)
        return result
    except Exception:
        return {}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    access_token = get_env("THREADS_ACCESS_TOKEN")
    user_id = get_env("THREADS_USER_ID")

    print(f"Threads APIからメトリクスを取得中...")
    try:
        posts = fetch_posts(user_id, access_token)
    except Exception as e:
        sys.exit(f"投稿一覧の取得に失敗: {e}")

    cache = load_json(CACHE_PATH, {})
    updated = 0

    for post in posts:
        media_id = post.get("id")
        if not media_id:
            continue

        record = {
            "id": media_id,
            "timestamp": post.get("timestamp"),
            "permalink": post.get("permalink"),
            "text_preview": (post.get("text") or "")[:80],
            "views": post.get("views") or 0,
            "likes": post.get("likes") or 0,
            "replies": post.get("replies") or 0,
            "reposts": post.get("reposts") or 0,
            "quotes": post.get("quotes") or 0,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        insights = fetch_insights(media_id, access_token)
        if insights:
            for k, v in insights.items():
                if k in record:
                    record[k] = v

        cache[media_id] = record
        updated += 1
        time.sleep(0.12)

    save_json(CACHE_PATH, cache)
    print(f"{updated}件のメトリクスを {CACHE_PATH} に保存しました。")
    print("次のステップ: python sync_to_sheet.py でxlsxに反映してください。")


if __name__ == "__main__":
    main()
