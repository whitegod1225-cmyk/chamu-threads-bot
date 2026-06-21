#!/usr/bin/env python3
"""
product-scraper.py  ── 楽天商品検索API 商品候補自動収集スクリプト

機能:
  - 楽天市場の商品検索APIから育児・ベビー関連キーワードのTOP商品を取得
  - フィルタリング（レビュー数・評価・価格帯）
  - affiliate-topics.md・post-history.md との重複チェック
  - affiliate-topics.md に新規候補を追記

実行:
  python product-scraper.py           # 通常実行
  python product-scraper.py --dry-run # プレビューのみ（ファイル変更なし）

必要な環境変数（.env または GitHub Secrets）:
  RAKUTEN_APPLICATION_ID=your_app_id
  RAKUTEN_ACCESS_KEY=your_access_key
"""

import os
import re
import sys
import io
import time
import argparse
from pathlib import Path
from datetime import datetime

# Windows(cp932環境)でも絵文字を含む文字列を出力できるようにする
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

# ── 環境変数読み込み ───────────────────────────────
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists() and not os.environ.get("CI"):
    for _enc in ("utf-8", "cp932", "utf-8-sig"):
        try:
            load_dotenv(dotenv_path=_env_path, encoding=_enc)
            break
        except UnicodeDecodeError:
            continue

RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APPLICATION_ID")
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY")
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID")
RAKUTEN_APP_URL      = os.environ.get("RAKUTEN_APP_URL", "https://github.com")

# ── ファイルパス ───────────────────────────────────
TOPICS_FILE  = Path(__file__).parent / "affiliate-topics.md"
HISTORY_FILE = Path(__file__).parent / "post-history.md"
QUEUE_FILE   = Path(__file__).parent / "post-queue.md"

# ── 楽天商品検索API設定 ────────────────────────────
RAKUTEN_SEARCH_API = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401"

# 検索キーワード（育児・ベビー関連）
SEARCH_KEYWORDS = {
    "おむつ・衛生用品":   "おむつ ベビー",
    "ベビー服・肌着":     "ベビー服 肌着 新生児",
    "おもちゃ・知育":     "おもちゃ 知育 赤ちゃん",
    "マタニティ・授乳":   "マタニティ 授乳 グッズ",
    "ベビー用品全般":     "ベビー用品 育児 便利",
}

# ── フィルタリング基準 ─────────────────────────────
MIN_REVIEW_COUNT = 100
MIN_REVIEW_SCORE = 4.0
MIN_PRICE        = 1000
MAX_PRICE        = 15000
MAX_CANDIDATES   = 3

# ── APIリクエスト共通ヘッダー ──────────────────────
def _headers() -> dict:
    return {
        "Referer":    RAKUTEN_APP_URL,
        "Origin":     RAKUTEN_APP_URL.rstrip("/"),
        "User-Agent": "Mozilla/5.0 (compatible; chamu-scraper/2.0)",
    }


def fetch_items(keyword: str, category_name: str) -> list[dict]:
    """楽天商品検索APIでキーワード検索（レビュー数順）"""
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey":     RAKUTEN_ACCESS_KEY,
        "format":        "json",
        "keyword":       keyword,
        "hits":          30,
        "sort":          "-reviewCount",
    }
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    try:
        r = requests.get(RAKUTEN_SEARCH_API, params=params, headers=_headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("Items", [])
        print(f"  [{category_name}] {len(items)}件取得")
        return items
    except requests.HTTPError as e:
        _handle_http_error(e, category_name)
        return []
    except Exception as e:
        print(f"  [{category_name}] エラー: {e}")
        return []


def _handle_http_error(e: requests.HTTPError, category_name: str):
    code = e.response.status_code if e.response is not None else "?"
    body = e.response.text[:200] if e.response is not None else ""
    if code == 401:
        print(f"  [{category_name}] 401: RAKUTEN_APPLICATION_ID / RAKUTEN_ACCESS_KEY を確認してください")
    elif code == 403:
        print(f"  [{category_name}] 403: {body}")
    elif code == 429:
        print(f"  [{category_name}] 429: リクエスト上限超過。しばらく待って再実行してください")
    else:
        print(f"  [{category_name}] HTTP {code}: {body}")


# ── フィルタリング ─────────────────────────────────
def parse_item(raw: dict) -> dict | None:
    item = raw.get("Item", {})
    try:
        return {
            "name":          item["itemName"],
            "price":         int(item.get("itemPrice", 0)),
            "review_score":  float(item.get("reviewAverage", 0)),
            "review_count":  int(item.get("reviewCount", 0)),
            "item_url":      item.get("itemUrl", ""),
            "affiliate_url": item.get("affiliateUrl", ""),
            "shop_name":     item.get("shopName", ""),
        }
    except (KeyError, ValueError, TypeError):
        return None


def passes_filter(item: dict) -> bool:
    if item["review_count"] < MIN_REVIEW_COUNT:
        return False
    if item["review_score"] < MIN_REVIEW_SCORE:
        return False
    if not (MIN_PRICE <= item["price"] <= MAX_PRICE):
        return False
    return True


# ── 重複チェック ───────────────────────────────────
def load_existing_products() -> set[str]:
    existing = set()
    for path in [TOPICS_FILE, HISTORY_FILE, QUEUE_FILE]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for name in re.findall(r"\*\*商品名\*\*：(.+)", text):
                existing.add(name.strip()[:30])
    return existing


# ── affiliate-topics.md への追記 ──────────────────
def load_next_candidate_number() -> int:
    if not TOPICS_FILE.exists():
        return 1
    text = TOPICS_FILE.read_text(encoding="utf-8")
    numbers = [int(m) for m in re.findall(r"## 候補(\d+)：", text)]
    return max(numbers, default=0) + 1


def format_candidate(n: int, item: dict, category_name: str) -> str:
    short_name = item["name"][:30].strip()
    return (
        f"\n## 候補{n}：{category_name}／{short_name}\n"
        f"**商品名**：{item['name']}\n"
        f"**楽天URL**：{item['item_url']}\n"
        f"**アフィリエイトURL**：{item['affiliate_url'] or '（要取得）'}\n"
        f"**時期**：通年\n"
        f"**イベント対応**：マラソン / スーパーSALE\n"
        f"**投稿アングル**：（記入してください）\n"
        f"**ステータス**：候補\n"
        f"**スクレイプ情報**：評価{item['review_score']} / レビュー{item['review_count']}件 / {item['price']:,}円 / {item['shop_name']}\n"
    )


def append_to_topics(candidates: list[tuple[int, dict, str]]):
    text = TOPICS_FILE.read_text(encoding="utf-8") if TOPICS_FILE.exists() else ""
    additions = ""
    for n, item, category_name in candidates:
        additions += "\n---\n" + format_candidate(n, item, category_name)
    TOPICS_FILE.write_text(text.rstrip() + "\n" + additions + "\n", encoding="utf-8")


# ── メイン処理 ────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="楽天商品候補自動収集")
    parser.add_argument("--dry-run", action="store_true", help="プレビューのみ（ファイル変更なし）")
    args = parser.parse_args()

    if not RAKUTEN_APP_ID or not RAKUTEN_ACCESS_KEY:
        print("RAKUTEN_APPLICATION_ID / RAKUTEN_ACCESS_KEY が設定されていません。")
        sys.exit(1)

    print(f"\n楽天商品スクレイプ開始（{datetime.now().strftime('%Y-%m-%d %H:%M')}）")
    if args.dry_run:
        print("   ※ --dry-run モード: ファイルは変更されません\n")

    existing = load_existing_products()
    print(f"   除外済み商品: {len(existing)}件\n")

    all_items: list[tuple[dict, str]] = []
    for category_name, keyword in SEARCH_KEYWORDS.items():
        items = fetch_items(keyword, category_name)
        for raw in items:
            item = parse_item(raw)
            if item:
                all_items.append((item, category_name))
        time.sleep(1)

    print(f"\n取得合計: {len(all_items)}件")

    passed: list[tuple[dict, str]] = []
    seen_names: set[str] = set()
    for item, category_name in all_items:
        if not passes_filter(item):
            continue
        key = item["name"][:30]
        if key in existing or key in seen_names:
            continue
        seen_names.add(key)
        passed.append((item, category_name))

    print(f"フィルタ通過: {len(passed)}件")

    if not passed:
        print("\n新規候補が見つかりませんでした。フィルタ基準を緩めるか、来週再実行してください。")
        return

    passed.sort(key=lambda x: x[0]["review_score"] * x[0]["review_count"], reverse=True)
    selected = passed[:MAX_CANDIDATES]

    next_n = load_next_candidate_number()
    candidates = [(next_n + i, item, cat) for i, (item, cat) in enumerate(selected)]

    print(f"\n【追加する候補: {len(candidates)}本】\n")
    for n, item, cat in candidates:
        print(f"  候補{n}：{item['name'][:40]}")
        print(f"         評価{item['review_score']} / レビュー{item['review_count']}件 / {item['price']:,}円")
        print(f"         カテゴリ: {cat}\n")

    if args.dry_run:
        print("（--dry-run: ファイルは変更されていません）")
        return

    append_to_topics(candidates)
    print(f"affiliate-topics.md に {len(candidates)} 件を追記しました")
    print("\n次のステップ:")
    print("  1. affiliate-topics.md を開いて投稿アングルを記入する")
    print("  2. 楽天アフィリエイトポータルでアフィリエイトURLを取得して記入する")
    print("  3. /affiliate-writer で投稿文を生成する")


if __name__ == "__main__":
    main()
