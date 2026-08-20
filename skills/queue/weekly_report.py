"""
weekly_report.py — 直近7日間の投稿成績をGitHub Issueに自動投稿する
毎週月曜8時JSTに weekly_report.yml から呼び出される
"""
import re
import os
import sys
import io
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HISTORY_FILE  = Path(__file__).parent / "post-history.md"
TOPICS_FILE   = Path(__file__).parent / "next-topics.md"
JST = timezone(timedelta(hours=9))
SCORE_FORMULA = "likes×3 + replies×5 + reposts×2"


def parse_posts(history: str) -> list:
    posts = []
    blocks = re.split(r'\n## 投稿', history)

    for block in blocks:
        if not re.match(r'\d+', block):
            continue

        m_metrics = re.search(
            r'views=(\d+) / likes=(\d+) / replies=(\d+) / reposts=(\d+)',
            block
        )
        m_theme = re.search(r'\*\*テーマ\*\*：(.+)', block)
        m_cat   = re.search(r'\*\*カテゴリ\*\*：(.+)', block)
        m_date  = re.search(r'(?:処理日時|投稿済み): (\d{4}-\d{2}-\d{2})', block)
        m_type  = re.search(r'\*\*型\*\*：(.+)', block)
        m_hook  = re.search(r'\*\*フック種別\*\*：(.+)', block)

        theme    = m_theme.group(1).strip() if m_theme else "不明"
        category = m_cat.group(1).strip() if m_cat else "不明"
        date_str = m_date.group(1) if m_date else None
        post_type = m_type.group(1).strip() if m_type else "不明"
        hook     = m_hook.group(1).strip() if m_hook else "その他"

        if not date_str:
            continue

        if m_metrics:
            views   = int(m_metrics.group(1))
            likes   = int(m_metrics.group(2))
            replies = int(m_metrics.group(3))
            reposts = int(m_metrics.group(4))
            score   = likes * 3 + replies * 5 + reposts * 2
            has_metrics = True
        else:
            views = likes = replies = reposts = score = 0
            has_metrics = False

        posts.append({
            "theme":       theme,
            "category":    category,
            "post_type":   post_type,
            "hook":        hook,
            "date":        date_str,
            "views":       views,
            "likes":       likes,
            "replies":     replies,
            "reposts":     reposts,
            "score":       score,
            "has_metrics": has_metrics,
        })

    return posts


def filter_last_n_days(posts: list, days: int, today: datetime) -> list:
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    return [p for p in posts if p["date"] >= cutoff]


def build_issue_body(posts_7d: list, all_posts: list, today: datetime, topics_text: str) -> str:
    period_start = (today - timedelta(days=7)).strftime("%m/%d")
    period_end   = today.strftime("%m/%d")

    posts_with_metrics = [p for p in posts_7d if p["has_metrics"]]
    posts_no_metrics   = [p for p in posts_7d if not p["has_metrics"]]

    lines = []
    lines.append(f"## 直近7日間（{period_start}〜{period_end}）投稿レポート\n")
    lines.append(f"> スコア式：{SCORE_FORMULA}\n\n")

    # ── 投稿数サマリー ──
    lines.append(f"### 投稿数\n")
    lines.append(f"- 今週の投稿: **{len(posts_7d)}本**（メトリクスあり: {len(posts_with_metrics)}本 / 取得待ち: {len(posts_no_metrics)}本）\n\n")

    # ── 空白期間チェック ──
    if posts_7d:
        dates = sorted(set(p["date"] for p in posts_7d))
        gaps = []
        prev = datetime.strptime(dates[0], "%Y-%m-%d")
        for d in dates[1:]:
            curr = datetime.strptime(d, "%Y-%m-%d")
            diff = (curr - prev).days
            if diff >= 2:
                gaps.append(f"{prev.strftime('%m/%d')}〜{curr.strftime('%m/%d')}（{diff}日空白）")
            prev = curr
        if gaps:
            lines.append(f"⚠️ **投稿空白あり**: {', '.join(gaps)}\n\n")

    # ── スコアランキング ──
    if posts_with_metrics:
        ranked = sorted(posts_with_metrics, key=lambda x: x["score"], reverse=True)
        lines.append("### スコアランキング\n\n")
        lines.append("| 順位 | テーマ（先頭25文字） | 型 | フック | views | score |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for i, p in enumerate(ranked[:10], 1):
            emoji = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else str(i)))
            theme_short = p["theme"][:25]
            lines.append(f"| {emoji} | {theme_short} | {p['post_type']} | {p['hook']} | {p['views']:,} | {p['score']} |\n")
        lines.append("\n")

        # ── ベスト投稿の詳細 ──
        best = ranked[0]
        lines.append("### 今週のベスト投稿\n")
        lines.append(f"**「{best['theme'][:40]}」**\n")
        lines.append(f"- 型: {best['post_type']} / フック: {best['hook']}\n")
        lines.append(f"- views: {best['views']:,} / likes: {best['likes']} / replies: {best['replies']} / score: {best['score']}\n\n")

        # ── 沈んだ投稿（score=8以下）の連続チェック ──
        low_score = [p for p in posts_with_metrics if p["score"] <= 8]
        if len(low_score) >= 3:
            lines.append(f"⚠️ **低スコア投稿が{len(low_score)}本連続** — テーマ・型・フックの見直しを検討\n\n")

        # ── 型別パフォーマンス（7日間）──
        type_groups: dict = {}
        for p in posts_with_metrics:
            t = p["post_type"]
            type_groups.setdefault(t, []).append(p)

        lines.append("### 型別パフォーマンス（今週）\n\n")
        lines.append("| 型 | 本数 | 平均views | 平均score |\n")
        lines.append("|---|---|---|---|\n")
        for t, group in sorted(type_groups.items(), key=lambda x: sum(p["score"] for p in x[1]) / len(x[1]), reverse=True):
            avg_v = round(sum(p["views"] for p in group) / len(group))
            avg_s = round(sum(p["score"] for p in group) / len(group), 1)
            lines.append(f"| {t} | {len(group)}本 | {avg_v:,} | {avg_s} |\n")
        lines.append("\n")

    else:
        lines.append("今週の投稿はまだメトリクス取得待ちです。\n\n")

    # ── メトリクス取得待ち投稿 ──
    if posts_no_metrics:
        lines.append("### メトリクス取得待ち\n")
        for p in posts_no_metrics:
            lines.append(f"- {p['date']} 「{p['theme'][:30]}」\n")
        lines.append("\n")

    # ── 全期間トップとの比較 ──
    all_with_metrics = [p for p in all_posts if p["has_metrics"] and p["score"] > 0]
    if all_with_metrics and posts_with_metrics:
        overall_avg = round(sum(p["views"] for p in all_with_metrics) / len(all_with_metrics))
        week_avg    = round(sum(p["views"] for p in posts_with_metrics) / len(posts_with_metrics))
        diff_pct    = round((week_avg - overall_avg) / overall_avg * 100) if overall_avg > 0 else 0
        sign        = "+" if diff_pct >= 0 else ""
        lines.append(f"### 全期間平均との比較\n")
        lines.append(f"- 今週の平均views: **{week_avg:,}** / 全期間平均: {overall_avg:,}（{sign}{diff_pct}%）\n\n")

    # ── 推奨テーマ（next-topics.mdから） ──
    if topics_text:
        topic_blocks = re.findall(r'## テーマ\d+：(.+)\n\*\*カテゴリ\*\*：(.+)\n\*\*切り口\*\*：(.+)\n\*\*1行目案\*\*：(.+)', topics_text)
        if topic_blocks:
            lines.append("### 来週の推奨テーマ（next-topics.mdより）\n\n")
            for theme, cat, angle, first_line in topic_blocks[:3]:
                lines.append(f"**「{theme}」**\n")
                lines.append(f"- カテゴリ: {cat} / 切り口: {angle}\n")
                lines.append(f"- 1行目案: {first_line}\n\n")

    lines.append("---\n")
    lines.append("*このIssueは weekly_report.yml により自動生成されました*\n")

    return "".join(lines)


def create_github_issue(title: str, body: str) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GITHUB_TOKEN / GITHUB_REPOSITORY が未設定。Issueを作成できません。")
        print("=== レポート内容（ローカル確認用） ===")
        print(f"# {title}\n")
        print(body)
        return False

    url     = f"https://api.github.com/repos/{repo}/issues"
    payload = json.dumps({
        "title": title,
        "body":  body,
        "labels": ["weekly-report"],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept":        "application/vnd.github+json",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"Issue作成成功: {result.get('html_url')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Issue作成失敗: {e.code} {e.reason}")
        print(e.read().decode())
        return False


def main():
    print("===== weekly_report.py 起動 =====")
    now = datetime.now(JST)

    history = HISTORY_FILE.read_text(encoding="utf-8")
    all_posts = parse_posts(history)
    print(f"全投稿数（メトリクスあり）: {len([p for p in all_posts if p['has_metrics']])}件")

    posts_7d = filter_last_n_days(all_posts, 7, now)
    print(f"直近7日間の投稿: {len(posts_7d)}件")

    topics_text = TOPICS_FILE.read_text(encoding="utf-8") if TOPICS_FILE.exists() else ""

    body  = build_issue_body(posts_7d, all_posts, now, topics_text)
    title = f"[週次レポート] {(now - timedelta(days=7)).strftime('%m/%d')}〜{now.strftime('%m/%d')} 投稿成績"

    create_github_issue(title, body)
    print("===== weekly_report.py 完了 =====")


if __name__ == "__main__":
    main()
