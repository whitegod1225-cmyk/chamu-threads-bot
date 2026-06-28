"""
supervisor.py: 自動運用の健全性チェック
GitHub Actionsから週1回実行され、問題があればGitHub Issueを作成する
"""
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
KNOWLEDGE = BASE.parent / "knowledge"

warnings = []
report_lines = []

def load(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

# ── チェック1: post-queue.md の投稿残数 ──────────────────────
queue = load(BASE / "post-queue.md")
queue_posts = re.findall(r"^## 投稿\d+", queue, re.MULTILINE)
queue_count = len(queue_posts)
report_lines.append(f"📋 キュー残数: {queue_count}本")
if queue_count <= 3:
    warnings.append(f"⚠️ キューが残り{queue_count}本。投稿切れが近い（/writerで補充を）")
elif queue_count >= 15:
    warnings.append(f"⚠️ キューが{queue_count}本と過多。投稿ペースを上げるか確認を")

# ── チェック2: 型A チェック ─────────────────────────────────
type_a_count = len(re.findall(r"型A", queue))
report_lines.append(f"🅰️ キュー内の型A: {type_a_count}本")
if type_a_count == 0 and queue_count >= 5:
    warnings.append("⚠️ キューに型Aがない。/intro-writerで1本生成して挿入すること")

# ── チェック3: next-topics.md の残テーマ数 ──────────────────
topics = load(BASE / "next-topics.md")
topic_count = len(re.findall(r"^## テーマ\d+", topics, re.MULTILINE))
report_lines.append(f"💡 次回テーマ残数: {topic_count}個")
if topic_count <= 1:
    warnings.append(f"⚠️ next-topics.mdのテーマが残り{topic_count}個。/analystで補充を")

# ── チェック4: 最終投稿からの経過時間 ──────────────────────
history = load(BASE / "post-history.md")
dates = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", history)
if dates:
    last_date_str = dates[-1]
    last_date = datetime.strptime(last_date_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    hours_ago = (now - last_date.astimezone(jst)).total_seconds() / 3600
    report_lines.append(f"🕐 最終投稿: {last_date_str} ({int(hours_ago)}時間前)")
    if hours_ago > 48:
        warnings.append(f"⚠️ 最終投稿から{int(hours_ago)}時間経過。自動投稿が止まっている可能性あり")
else:
    report_lines.append("🕐 最終投稿: 履歴なし")

# ── レポート出力 ────────────────────────────────────────────
now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")
report = f"""# Supervisor Report
実行日時: {now_str}

## ステータス
""" + "\n".join(f"- {l}" for l in report_lines)

if warnings:
    report += "\n\n## ⚠️ 警告\n" + "\n".join(f"- {w}" for w in warnings)
    print("WARNINGS_FOUND")
else:
    report += "\n\n## ✅ 問題なし"
    print("ALL_CLEAR")

report_path = BASE / "supervisor-report.md"
report_path.write_text(report, encoding="utf-8")
print(report)

# 警告があれば exit 1 → GitHub Actionsがissueを作成する
if warnings:
    sys.exit(1)
