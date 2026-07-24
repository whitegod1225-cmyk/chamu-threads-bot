"""
fetcher.py — Threads投稿のエンゲージメントを取得してpost-history.mdに記録する
対象: metrics_fetchedがFalseで、投稿から24時間以上経過しているもの
"""
import urllib.request
import urllib.parse
import urllib.error
import json
import re
import sys
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists() and not os.environ.get("CI"):
    for _enc in ("utf-8", "cp932", "utf-8-sig"):
        try:
            load_dotenv(dotenv_path=_env_path, encoding=_enc)
            break
        except UnicodeDecodeError:
            continue

ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
HISTORY_FILE = Path(__file__).parent / "post-history.md"
ANALYSIS_FILE = Path(__file__).parent / "analysis-latest.md"
JST = timezone(timedelta(hours=9))


def fetch_insights(post_id):
    metrics = "views,likes,replies,reposts,quotes"
    params = urllib.parse.urlencode({"metric": metrics, "access_token": ACCESS_TOKEN})
    url = f"https://graph.threads.net/v1.0/{post_id}/insights?{params}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode("utf-8"))
        result = {}
        for item in data.get("data", []):
            result[item["name"]] = item["values"][0]["value"] if item.get("values") else item.get("total_value", {}).get("value", 0)
        return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  APIエラー {post_id}: HTTP {e.code} | {body}")
        return None


def parse_posted_at(text):
    """<!-- 処理日時: 2026-04-12 07:48 | 投稿ID: xxx --> から日時を取得"""
    m = re.search(r'処理日時: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', text)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    m = re.search(r'投稿済み: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', text)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    return None


def parse_post_id(text):
    m = re.search(r'投稿ID: (\d+)', text)
    return m.group(1) if m else None


def main():
    print("===== fetcher.py 起動 =====")
    history = HISTORY_FILE.read_text(encoding="utf-8")
    now = datetime.now(JST)

    # ブロック単位で分割（<!-- ... -->コメントを含むセクション）
    blocks = re.split(r'(?=<!-- )', history)

    results = []
    updated = False

    for i, block in enumerate(blocks):
        post_id = parse_post_id(block)
        posted_at = parse_posted_at(block)

        if not post_id:
            continue
        if not posted_at:
            continue

        elapsed = now - posted_at
        if elapsed.total_seconds() < 86400:
            print(f"  スキップ（24h未満）: {post_id}")
            continue

        if "metrics_fetched: true" in block:
            print(f"  スキップ（取得済み）: {post_id}")
            continue

        print(f"  取得中: {post_id} (投稿から{int(elapsed.total_seconds()//3600)}時間)")
        metrics = fetch_insights(post_id)
        if metrics is None:
            continue

        likes   = metrics.get("likes", 0)
        replies = metrics.get("replies", 0)
        reposts = metrics.get("reposts", 0)
        views   = metrics.get("views", 0)
        quotes  = metrics.get("quotes", 0)

        print(f"  結果: views={views}, likes={likes}, replies={replies}, reposts={reposts}")

        # テーマ抽出
        theme_m = re.search(r'\*\*テーマ\*\*：(.+)', block)
        theme = theme_m.group(1).strip() if theme_m else "不明"
        category_m = re.search(r'\*\*カテゴリ\*\*：(.+)', block)
        category = category_m.group(1).strip() if category_m else "不明"

        # ── スコアカード算出 ──
        resonance_score = likes * 3 + replies * 5 + reposts * 2
        quality_score = round(resonance_score / views * 100, 1) if views > 0 else 0.0

        # hook_type: カテゴリ文字列から「型N：XXX型」を抽出
        hook_m = re.search(r'型\w+[：:][^\s/]+型', category)
        hook_type = hook_m.group(0) if hook_m else "不明"

        # cta_type: コメント欄の内容から推定
        reply_section_m = re.search(r'\*\*コメント欄.*?\*\*\n(.+)', block, re.DOTALL)
        reply_text = reply_section_m.group(1) if reply_section_m else ""
        if any(kw in reply_text for kw in ["保存して", "スクショ", "手元に"]):
            cta_type = "保存誘導"
        elif any(kw in reply_text for kw in ["フォロー", "流れてきます", "毎日して"]):
            cta_type = "フォロー誘導"
        elif any(kw in reply_text for kw in ["コメント", "教えて", "あった？", "いる？"]):
            cta_type = "コメント誘導"
        elif any(kw in reply_text for kw in ["おつかれ", "大丈夫", "十分", "ぼちぼち"]):
            cta_type = "救い締め"
        else:
            cta_type = "その他"

        # failure_flag: views<50 かつ likes=0
        failure_flag = views < 50 and likes == 0

        # post-historyブロックにメトリクス追記
        metrics_line = (
            f"\n**メトリクス（{now.strftime('%Y-%m-%d')}取得）**\n"
            f"views={views} / likes={likes} / replies={replies} / reposts={reposts} / quotes={quotes}\n"
            f"resonance_score={resonance_score} / quality_score={quality_score}%\n"
            f"hook_type={hook_type} / cta_type={cta_type}"
            + (f" / failure_flag=true ⚠️" if failure_flag else "") + "\n"
            f"metrics_fetched: true\n"
        )
        # --- の前に挿入
        blocks[i] = block.rstrip().rstrip("---").rstrip() + metrics_line + "\n\n---\n"
        updated = True

        results.append({
            "post_id": post_id,
            "theme": theme,
            "category": category,
            "posted_at": posted_at.strftime("%Y-%m-%d"),
            "views": views,
            "likes": likes,
            "replies": replies,
            "reposts": reposts,
            "resonance_score": resonance_score,
            "quality_score": quality_score,
            "hook_type": hook_type,
            "cta_type": cta_type,
            "failure_flag": failure_flag,
        })

    if updated:
        HISTORY_FILE.write_text("".join(blocks), encoding="utf-8")
        print("post-history.md を更新しました")
        # メタファイルを再生成
        try:
            import importlib.util, sys as _sys
            _spec = importlib.util.spec_from_file_location(
                "make_meta", Path(__file__).parent / "make_meta.py"
            )
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.main()
        except Exception as e:
            print(f"[fetcher] make_meta 呼び出し失敗（無視）: {e}")
    else:
        print("更新対象なし（取得済みまたは24h未満）")

    # analysis-latest.mdに分析レポートを保存
    if results:
        lines = [f"# analysis-latest.md ── エンゲージメント分析\n"]
        lines.append(f"更新日時: {now.strftime('%Y-%m-%d %H:%M')}\n\n")
        lines.append("## 投稿別パフォーマンス\n\n")
        lines.append("| テーマ | カテゴリ | 投稿日 | views | likes | replies | reposts | score |\n")
        lines.append("|--------|---------|--------|-------|-------|---------|---------|-------|\n")
        sorted_results = sorted(results, key=lambda x: x["resonance_score"], reverse=True)
        for r in sorted_results:
            flag = " ⚠️" if r.get("failure_flag") else ""
            lines.append(
                f"| {r['theme']} | {r['category']} | {r['posted_at']} "
                f"| {r['views']} | {r['likes']} | {r['replies']} | {r['reposts']} "
                f"| {r['resonance_score']}{flag} |\n"
            )

        lines.append("\n## ハイライト\n\n")
        if sorted_results:
            best = sorted_results[0]
            lines.append(
                f"**最高スコア**: 「{best['theme']}」"
                f"（score={best['resonance_score']} / quality={best['quality_score']}% / hook={best['hook_type']}）\n\n"
            )
            worst = sorted_results[-1]
            if len(sorted_results) > 1:
                lines.append(
                    f"**最低スコア**: 「{worst['theme']}」"
                    f"（score={worst['resonance_score']} / views={worst['views']}）\n\n"
                )
            failures = [r for r in results if r.get("failure_flag")]
            if failures:
                lines.append(f"**⚠️ failure_flag（views<50 かつ likes=0）**: {len(failures)}件\n")
                for f in failures:
                    lines.append(f"  - 「{f['theme']}」（{f['posted_at']}）\n")
                lines.append("\n")

        # hook_type別集計
        from collections import Counter
        hook_counts = Counter(r["hook_type"] for r in results if r["hook_type"] != "不明")
        if hook_counts:
            lines.append("## hook_type別平均スコア\n\n")
            lines.append("| hook_type | 件数 | 平均score |\n")
            lines.append("|-----------|------|----------|\n")
            hook_scores = {}
            for r in results:
                ht = r["hook_type"]
                hook_scores.setdefault(ht, []).append(r["resonance_score"])
            for ht, scores in sorted(hook_scores.items(), key=lambda x: -sum(x[1])/len(x[1])):
                avg = round(sum(scores) / len(scores), 1)
                lines.append(f"| {ht} | {len(scores)} | {avg} |\n")
            lines.append("\n")

        ANALYSIS_FILE.write_text("".join(lines), encoding="utf-8")
        print(f"analysis-latest.md に {len(results)}件の分析を保存しました")

    print("===== fetcher.py 完了 =====")


if __name__ == "__main__":
    main()
