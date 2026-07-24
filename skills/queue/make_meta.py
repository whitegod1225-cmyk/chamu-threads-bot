"""
make_meta.py — post-history.md からメタ情報のみ抽出して
post-history-meta.md（軽量テーブル形式）を生成する。

使い方:
  python make_meta.py            # post-history-meta.md を再生成
  python make_meta.py --sheet    # 生成後にスプレッドシートへも同期

fetcher.py からも import して使う。
"""
import re
import sys
import io
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
HISTORY_FILE = BASE / "post-history.md"
META_FILE    = BASE / "post-history-meta.md"
JST = timezone(timedelta(hours=9))


def parse_history(text):
    """post-history.md をブロック単位でパースしてメタ情報のリストを返す"""
    blocks = re.split(r'(?=<!-- )', text)
    records = []

    for block in blocks:
        num_m = re.search(r'## 投稿(\w+)', block)
        if not num_m:
            continue
        post_num = num_m.group(1)

        # 投稿日時・Threads投稿ID
        dt_m = re.search(r'処理日時: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', block)
        if not dt_m:
            dt_m = re.search(r'投稿済み: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', block)
        posted_at = dt_m.group(1) if dt_m else "-"

        pid_m = re.search(r'投稿ID: (\d+)', block)
        post_id = pid_m.group(1) if pid_m else "-"

        # テーマ・カテゴリ（テーマは40字で切る）
        theme_m = re.search(r'\*\*テーマ\*\*[：:]\s*(.+)', block)
        theme = (theme_m.group(1).strip()[:40] + "…") if theme_m and len(theme_m.group(1).strip()) > 40 else (theme_m.group(1).strip() if theme_m else "-")

        cat_m = re.search(r'\*\*カテゴリ\*\*[：:]\s*(.+)', block)
        category = cat_m.group(1).strip() if cat_m else "-"

        # メトリクス（fetcher.pyが書き込んだ値）
        def get(pattern, default="-"):
            m = re.search(pattern, block)
            return m.group(1) if m else default

        views    = get(r'views=(\d+)')
        likes    = get(r'likes=(\d+)')
        replies  = get(r'replies=(\d+)')
        reposts  = get(r'reposts=(\d+)')
        resonance = get(r'resonance_score=(\d+)')
        quality   = get(r'quality_score=([\d.]+)%')
        hook_type = get(r'hook_type=([^\s/\n⚠]+)')
        cta_type  = get(r'cta_type=([^\s/\n⚠]+)')
        fetched   = "true" if "metrics_fetched: true" in block else "false"

        records.append({
            "投稿番号":   post_num,
            "投稿日時":   posted_at,
            "テーマ":     theme,
            "カテゴリ":   category,
            "views":      views,
            "likes":      likes,
            "replies":    replies,
            "reposts":    reposts,
            "score":      resonance,
            "quality%":   quality,
            "hook_type":  hook_type,
            "cta_type":   cta_type,
            "fetched":    fetched,
            "post_id":    post_id,
        })

    return records


def write_meta(records):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# post-history-meta.md ── 投稿履歴（軽量メタ版）\n",
        "> post-history.md から自動生成。直接編集しない。\n",
        f"> 更新: {now}  全{len(records)}件\n\n",
        "| 番号 | 投稿日時 | テーマ | カテゴリ | views | likes | replies | reposts"
        " | score | quality% | hook_type | cta_type | fetched | post_id |\n",
        "|------|---------|--------|---------|-------|-------|---------|---------|"
        "-------|---------|-----------|---------|---------|--------|\n",
    ]
    for r in records:
        lines.append(
            f"| {r['投稿番号']} | {r['投稿日時']} | {r['テーマ']} | {r['カテゴリ']}"
            f" | {r['views']} | {r['likes']} | {r['replies']} | {r['reposts']}"
            f" | {r['score']} | {r['quality%']}"
            f" | {r['hook_type']} | {r['cta_type']} | {r['fetched']} | {r['post_id']} |\n"
        )
    META_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"[make_meta] post-history-meta.md 更新完了（{len(records)}件）")
    return records


def main(sync_sheet=False):
    print("===== make_meta.py 起動 =====")
    text = HISTORY_FILE.read_text(encoding="utf-8")
    records = parse_history(text)
    write_meta(records)

    if sync_sheet:
        # sync_to_sheet.py の --from-meta モードを呼ぶ
        import subprocess
        sheet_script = Path(__file__).resolve().parent.parent.parent / "threads_tool" / "sync_to_sheet.py"
        if sheet_script.exists():
            subprocess.run([sys.executable, str(sheet_script), "--from-meta", "--create-if-missing"], check=False)
        else:
            print(f"[make_meta] sync_to_sheet.py が見つかりません: {sheet_script}")

    print("===== make_meta.py 完了 =====")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", action="store_true", help="生成後にスプレッドシートへも同期する")
    args = parser.parse_args()
    main(sync_sheet=args.sheet)
