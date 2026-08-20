"""
analyst.py — post-history.md のメトリクスを分析して next-topics.md / performance-patterns.md を更新する
fetcherがメトリクスを取得した後に実行する
"""
import re
import sys
import io
from pathlib import Path
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HISTORY_FILE  = Path(__file__).parent / "post-history.md"
ANALYSIS_FILE = Path(__file__).parent / "analysis-latest.md"
TOPICS_FILE   = Path(__file__).parent / "next-topics.md"
PATTERNS_FILE = Path(__file__).parent / "performance-patterns.md"
JST = timezone(timedelta(hours=9))

CATEGORY_LABELS = {
    "A": "感情・共感系",
    "AC": "ワンオペ・保育園共感系",
    "B": "専門知識系",
    "DE": "グッズ・節約系",
    "note": "note誘導",
}

# 型の表示名
POST_TYPE_LABELS = {
    "①言い換え型":    "①言い換え型",
    "②概念再定義型":  "②概念再定義型",
    "③告白・報告型":  "③告白・報告型",
    "④あるある型":    "④あるある型",
    "B→A変換型":      "B→A変換型",
    "アフィリ型":      "アフィリ型",
    "不明":           "不明",
}

# フック種別の表示名
HOOK_LABELS = {
    "数字先出し": "数字先出し（16年・3回・1000人 etc.）",
    "場面描写":   "場面描写（〇時・〇日目・〇年前 etc.）",
    "権威崩し":   "権威崩し（保育士なのに〜できなかった）",
    "逆説型":     "逆説型（〇〇じゃなかった・と思ってたけど）",
    "告白型":     "告白型（〇〇だった・わからなかった・やめた）",
    "感情直球":   "感情直球（つらい・しんどい・悲しい etc.）",
    "その他":     "その他",
}


def classify_bucket(category: str) -> str:
    if "note誘導" in category:
        return "note"
    if any(k in category for k in ["専門知識", "グッズ・専門知識"]):
        return "B"
    if any(k in category for k in ["グッズ", "節約", "アフィリ", "楽天"]):
        return "DE"
    if any(k in category for k in ["ワーママ", "入園準備", "入園後", "入園", "ワンオペ"]):
        return "AC"
    if any(k in category for k in ["共感", "体験談", "問いかけ", "生活系"]):
        return "A"
    return "A"


def classify_post_type(category: str, theme: str) -> str:
    """カテゴリ欄と投稿テーマから①〜④型を判定する"""
    text = category + " " + theme

    if "型13" in text or "アフィリ" in text or "楽天" in text:
        return "アフィリ型"
    if "①" in text or "言い換え" in text:
        return "①言い換え型"
    if "②" in text or "概念再定義" in text or "再定義" in text:
        return "②概念再定義型"
    if "③" in text or "告白" in text or "報告" in text:
        return "③告白・報告型"
    if "④" in text or "あるある" in text or "カオス" in text:
        return "④あるある型"
    if "B→A" in text or "B×A" in text or "知識系" in text:
        return "B→A変換型"

    # フォールバック：テーマの文言から推測
    if any(w in theme for w in ["言い換え", "代わりに言う", "言う言葉"]):
        return "①言い換え型"
    if any(w in theme for w in ["じゃない", "ではない", "ではなかった", "じゃなかった"]):
        return "②概念再定義型"
    if any(w in theme for w in ["なのに", "わからなかった", "できなかった", "やめた"]):
        return "③告白・報告型"

    return "不明"


def classify_hook(first_line: str) -> str:
    """投稿の1行目からフック種別を判定する"""
    if not first_line:
        return "その他"

    # 権威崩し：「保育士〇〇年なのに」「〇〇のはずなのに」
    if re.search(r'(保育士|元保育士|16年|1000人).{0,10}(なのに|のに)', first_line):
        return "権威崩し"

    # 数字先出し：1行目に数字が含まれる（年数・回数・人数等）
    if re.search(r'\d+(年|回|人|本|日|時|歳|ヶ月|個|円|分)', first_line):
        return "数字先出し"

    # 場面描写：具体的な時刻・日付・状況
    if re.search(r'(午前|午後|\d+時|\d+日目|\d+年前|夏休み|土曜|朝|夜中|夜11時|夜10時)', first_line):
        return "場面描写"

    # 逆説型：「〇〇じゃなかった」「〇〇ではなかった」
    if re.search(r'(じゃなかった|ではなかった|と思ってたけど|だと思ってた)', first_line):
        return "逆説型"

    # 告白型：「〇〇だった」「わからなかった」「やめた」
    if re.search(r'(なのに|だった|わからなかった|できなかった|やめた|出た|あった)', first_line):
        return "告白型"

    # 感情直球：感情ワード直出し
    if re.search(r'(つらい|しんどい|悲しい|嬉しい|怖い|苦しい|限界)', first_line):
        return "感情直球"

    return "その他"


def parse_metrics(history: str) -> list:
    """post-history.md からメトリクス付き投稿を抽出"""
    posts = []
    blocks = re.split(r'\n## 投稿', history)

    for block in blocks:
        if not re.match(r'\d+', block):
            continue

        m_metrics = re.search(
            r'views=(\d+) / likes=(\d+) / replies=(\d+) / reposts=(\d+)',
            block
        )
        if not m_metrics:
            continue

        views   = int(m_metrics.group(1))
        likes   = int(m_metrics.group(2))
        replies = int(m_metrics.group(3))
        reposts = int(m_metrics.group(4))

        m_theme = re.search(r'\*\*テーマ\*\*：(.+)', block)
        m_cat   = re.search(r'\*\*カテゴリ\*\*：(.+)', block)
        m_date  = re.search(r'(?:処理日時|投稿済み): (\d{4}-\d{2}-\d{2})', block)
        m_type  = re.search(r'\*\*型\*\*：(.+)', block)
        m_hook  = re.search(r'\*\*フック種別\*\*：(.+)', block)

        theme    = m_theme.group(1).strip() if m_theme else "不明"
        category = m_cat.group(1).strip() if m_cat else "不明"
        date_str = m_date.group(1) if m_date else "不明"

        # 型フィールドが明示されていればそれを使う、なければ推定
        post_type = m_type.group(1).strip() if m_type else classify_post_type(category, theme)

        # フック種別フィールドが明示されていればそれを使う、なければ本文1行目から推定
        if m_hook:
            hook = m_hook.group(1).strip()
        else:
            # 本文の1行目を取得
            body_match = re.search(r'\*\*本文\*\*\n(.+)', block)
            first_line = body_match.group(1).strip() if body_match else theme
            hook = classify_hook(first_line)

        score = likes * 3 + replies * 5 + reposts * 4
        like_rate    = round(likes / views * 100, 3) if views > 0 else 0
        comment_rate = round(replies / views * 100, 3) if views > 0 else 0
        quality      = round(score / views * 100, 3) if views > 0 else 0

        posts.append({
            "theme":        theme,
            "category":     category,
            "bucket":       classify_bucket(category),
            "post_type":    post_type,
            "hook":         hook,
            "date":         date_str,
            "views":        views,
            "likes":        likes,
            "replies":      replies,
            "reposts":      reposts,
            "score":        score,
            "like_rate":    like_rate,
            "comment_rate": comment_rate,
            "quality":      quality,
        })

    return posts


def analyze(posts: list) -> dict:
    if not posts:
        return {}

    sorted_by_score = sorted(posts, key=lambda x: x["score"], reverse=True)

    bucket_scores = {}
    for p in posts:
        b = p["bucket"]
        bucket_scores.setdefault(b, []).append(p["score"])

    bucket_avg = {
        b: round(sum(scores) / len(scores), 1)
        for b, scores in bucket_scores.items()
    }

    return {
        "total":      len(posts),
        "best":       sorted_by_score[:3],
        "worst":      sorted_by_score[-3:],
        "bucket_avg": bucket_avg,
    }


def group_stats(posts: list, key: str) -> dict:
    """指定キーでグループ化してパフォーマンス統計を返す"""
    groups = {}
    for p in posts:
        val = p.get(key, "不明")
        groups.setdefault(val, []).append(p)

    result = {}
    for val, group in groups.items():
        n = len(group)
        avg_views    = round(sum(p["views"] for p in group) / n)
        avg_score    = round(sum(p["score"] for p in group) / n, 1)
        avg_like     = round(sum(p["like_rate"] for p in group) / n, 3)
        avg_comment  = round(sum(p["comment_rate"] for p in group) / n, 3)
        avg_quality  = round(sum(p["quality"] for p in group) / n, 3)
        result[val] = {
            "count":       n,
            "avg_views":   avg_views,
            "avg_score":   avg_score,
            "avg_like":    avg_like,
            "avg_comment": avg_comment,
            "avg_quality": avg_quality,
        }
    return result


def recommend_label(stats: dict, baseline_like: float = 0.0, baseline_quality: float = 0.0) -> str:
    """パフォーマンス統計から推奨度ラベルを返す（全体平均との相対比較）"""
    if stats["count"] <= 1:
        return "— データ不足"
    # 全体平均の120%以上 → 積極使用
    if baseline_like > 0 and baseline_quality > 0:
        if stats["avg_like"] >= baseline_like * 1.2 and stats["avg_quality"] >= baseline_quality * 1.2:
            return "✅ 積極使用"
        if stats["avg_like"] >= baseline_like * 0.7 or stats["avg_quality"] >= baseline_quality * 0.7:
            return "⚠️ 様子見"
        return "❌ 見直し"
    # ベースラインなし時のフォールバック（絶対値）
    if stats["avg_like"] >= 0.3 and stats["avg_quality"] >= 0.5:
        return "✅ 積極使用"
    if stats["avg_like"] >= 0.1 or stats["avg_quality"] >= 0.2:
        return "⚠️ 様子見"
    return "❌ 見直し"


def generate_performance_patterns(posts: list, now: datetime):
    """performance-patterns.md を生成・更新する"""
    if not posts:
        return

    # 直近30投稿を対象
    recent = sorted(posts, key=lambda x: x["date"], reverse=True)[:30]

    type_stats = group_stats(recent, "post_type")
    hook_stats = group_stats(recent, "hook")

    # 全体ベースライン（直近30投稿の平均）
    baseline_like    = round(sum(p["like_rate"] for p in recent) / len(recent), 3) if recent else 0.0
    baseline_quality = round(sum(p["quality"] for p in recent) / len(recent), 3) if recent else 0.0

    # 推奨型・非推奨型を抽出（相対比較）
    recommended_types = [t for t, s in type_stats.items() if "✅" in recommend_label(s, baseline_like, baseline_quality)]
    avoid_types       = [t for t, s in type_stats.items() if "❌" in recommend_label(s, baseline_like, baseline_quality)]
    recommended_hooks = [h for h, s in hook_stats.items() if "✅" in recommend_label(s, baseline_like, baseline_quality)]
    avoid_hooks       = [h for h, s in hook_stats.items() if "❌" in recommend_label(s, baseline_like, baseline_quality)]

    # 既存ファイルの週次ログ部分を保持
    weekly_log = ""
    if PATTERNS_FILE.exists():
        existing = PATTERNS_FILE.read_text(encoding="utf-8")
        m = re.search(r'(## 週次ログ.*)', existing, re.DOTALL)
        if m:
            weekly_log = m.group(1)

    lines = []
    lines.append("# performance-patterns.md ── 型別・フック別学習ログ\n")
    lines.append(f"更新: {now.strftime('%Y-%m-%d %H:%M')}（直近{len(recent)}投稿を対象）\n\n")
    lines.append("> このファイルは analyst.py が自動更新します。手動編集不要。\n")
    lines.append("> /writer はこのファイルの推奨設定を参照して型とフックを選ぶこと。\n\n")

    # 型別パフォーマンス表
    lines.append("## 型別パフォーマンス\n\n")
    lines.append("| 型 | 使用数 | 平均views | 平均いいね率 | 平均コメント率 | 平均qualityスコア | 推奨度 |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for t, s in sorted(type_stats.items(), key=lambda x: x[1]["avg_quality"], reverse=True):
        label = recommend_label(s, baseline_like, baseline_quality)
        lines.append(
            f"| {t} | {s['count']}本 | {s['avg_views']:,} | {s['avg_like']:.2f}% "
            f"| {s['avg_comment']:.2f}% | {s['avg_quality']:.2f}% | {label} |\n"
        )

    lines.append("\n")

    # フック種別パフォーマンス表
    lines.append("## フック種別パフォーマンス\n\n")
    lines.append("| フック種別 | 使用数 | 平均views | 平均いいね率 | 平均コメント率 | 推奨度 |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for h, s in sorted(hook_stats.items(), key=lambda x: x[1]["avg_like"], reverse=True):
        label = recommend_label(s, baseline_like, baseline_quality)
        lines.append(
            f"| {h} | {s['count']}本 | {s['avg_views']:,} "
            f"| {s['avg_like']:.2f}% | {s['avg_comment']:.2f}% | {label} |\n"
        )

    lines.append("\n")

    # note誘導型の集計
    note_posts = [p for p in recent if p.get("bucket") == "note"]
    if note_posts:
        lines.append("## note誘導型パフォーマンス\n\n")
        n = len(note_posts)
        avg_views   = round(sum(p["views"] for p in note_posts) / n)
        avg_like    = round(sum(p["like_rate"] for p in note_posts) / n, 3)
        avg_comment = round(sum(p["comment_rate"] for p in note_posts) / n, 3)
        avg_quality = round(sum(p["quality"] for p in note_posts) / n, 3)
        lines.append(f"- 対象投稿数: {n}本\n")
        lines.append(f"- 平均views: {avg_views:,}\n")
        lines.append(f"- 平均いいね率: {avg_like:.2f}%\n")
        lines.append(f"- 平均コメント率: {avg_comment:.2f}%\n")
        lines.append(f"- 平均qualityスコア: {avg_quality:.2f}%\n\n")
        lines.append("| テーマ（先頭30文字） | フック | views | いいね率 | コメント率 |\n")
        lines.append("|---|---|---|---|---|\n")
        for p in sorted(note_posts, key=lambda x: x["quality"], reverse=True):
            theme_short = p["theme"][:30].rstrip("「」")
            lines.append(
                f"| {theme_short} | {p['hook']} "
                f"| {p['views']:,} | {p['like_rate']:.2f}% | {p['comment_rate']:.2f}% |\n"
            )
        # 全体平均との比較
        all_avg_like = round(sum(p["like_rate"] for p in recent) / len(recent), 3) if recent else 0
        diff = round(avg_like - all_avg_like, 3)
        diff_sign = "+" if diff >= 0 else ""
        lines.append(f"\n全体平均いいね率: {all_avg_like:.2f}% → note誘導型との差: {diff_sign}{diff:.2f}%\n")
        lines.append("> note誘導投稿のいいね率が全体平均を上回る場合は積極的にCTAを入れる。\n\n")
    else:
        lines.append("## note誘導型パフォーマンス\n\n")
        lines.append("> 直近30投稿にnote誘導型なし。カテゴリに「note誘導」を入れて記録が蓄積されると自動集計されます。\n\n")

    # 推奨設定サマリー（/writerが参照する）
    lines.append("## 推奨設定（/writer が参照する設定）\n\n")
    lines.append(f"- **優先する型**: {', '.join(recommended_types) if recommended_types else '様子見中'}\n")
    lines.append(f"- **避ける型**: {', '.join(avoid_types) if avoid_types else 'なし'}\n")
    lines.append(f"- **優先するフック**: {', '.join(recommended_hooks) if recommended_hooks else '様子見中'}\n")
    lines.append(f"- **避けるフック**: {', '.join(avoid_hooks) if avoid_hooks else 'なし'}\n\n")

    # トップ投稿（型・フック確認用）
    lines.append("## 直近トップ投稿（型・フック確認用）\n\n")
    lines.append("| テーマ（先頭30文字） | 型 | フック | views | いいね率 | コメント率 |\n")
    lines.append("|---|---|---|---|---|---|\n")
    top = sorted(recent, key=lambda x: x["quality"], reverse=True)[:10]
    for p in top:
        theme_short = p["theme"][:30].rstrip("「」")
        lines.append(
            f"| {theme_short} | {p['post_type']} | {p['hook']} "
            f"| {p['views']:,} | {p['like_rate']:.2f}% | {p['comment_rate']:.2f}% |\n"
        )

    lines.append("\n")

    # 週次ログ：既存を保持しつつ今週分を先頭に追加
    today_log = f"### {now.strftime('%Y-%m-%d')}\n"
    today_log += f"- 分析対象: {len(recent)}投稿\n"
    today_log += f"- 最強型: {sorted(type_stats.items(), key=lambda x: x[1]['avg_quality'], reverse=True)[0][0] if type_stats else '不明'}\n"
    today_log += f"- 最強フック: {sorted(hook_stats.items(), key=lambda x: x[1]['avg_like'], reverse=True)[0][0] if hook_stats else '不明'}\n"
    if avoid_types:
        today_log += f"- 要見直し型: {', '.join(avoid_types)}\n"
    today_log += "\n"

    if weekly_log:
        # 既存ログに今日分を追記（重複日はスキップ）
        if now.strftime('%Y-%m-%d') not in weekly_log:
            updated_log = weekly_log.replace("## 週次ログ\n", f"## 週次ログ\n{today_log}")
        else:
            updated_log = weekly_log
        lines.append(updated_log)
    else:
        lines.append("## 週次ログ\n\n")
        lines.append(today_log)

    PATTERNS_FILE.write_text("".join(lines), encoding="utf-8")
    print("performance-patterns.md を更新しました")


def generate_topics(analysis: dict) -> list:
    """分析結果から次のテーマを3つ提案"""
    if not analysis:
        return []

    topics = []
    bucket_avg = analysis.get("bucket_avg", {})
    sorted_buckets = sorted(bucket_avg.items(), key=lambda x: x[1], reverse=True)

    bucket_suggestions = {
        "A": [
            ("子どもに怒りすぎた後の立て直し方", "怒った後の具体的な関係修復ステップを体験談で", "「怒ってごめんね、で終わらない方法を見つけた」"),
            ("保育士として見てきた『いいお母さん』の定義", "完璧じゃなくていい、の具体的な根拠を専門知識で補強", "「16年で気づいた、子どもが求めてるお母さん像」"),
        ],
        "AC": [
            ("保育園の呼び出し、仕事を何回休んだか正直に言う", "実数を先出しして共感を取る型", "「入園3ヶ月で14回休んだ、でも今は月0回」"),
            ("毎朝の泣き別れを乗り越えた3つのこと", "共感→体験談→専門知識の流れ", "「毎朝泣かれてた時期、これだけで変わった」"),
            ("保育園に預けて『よかった』と思える日が来た", "時間軸を使った体験談", "「あの罪悪感は、今のわたしには想像できないくらい薄れた」"),
        ],
        "B": [
            ("イヤイヤ期がひどい子に共通する3つのこと", "専門知識×保育士視点で権威性を出す", "「1000人以上のイヤイヤを見てきて気づいたパターン」"),
            ("言葉が遅い子どもの親にまず伝えたいこと", "発達の個人差×保育士知識", "「『うちの子まだ喋らない』で焦ってる人に届けたい」"),
        ],
        "DE": [
            ("入園準備、本当に必要なものだけ正直に言う", "グッズ系は具体性と金額感が大事", "「全部買ったら3万超えた、本当に必要なのはこれだけ」"),
        ],
    }

    used = set()
    for bucket, _ in sorted_buckets:
        if bucket in bucket_suggestions:
            for suggestion in bucket_suggestions[bucket]:
                key = suggestion[0]
                if key not in used:
                    topics.append({
                        "bucket":     bucket,
                        "theme":      suggestion[0],
                        "angle":      suggestion[1],
                        "first_line": suggestion[2],
                    })
                    used.add(key)
                if len(topics) >= 3:
                    break
        if len(topics) >= 3:
            break

    defaults = [
        {"bucket": "AC", "theme": "保育園ある日の朝をラクにした3つの工夫", "angle": "生活改善×共感", "first_line": "「朝のバタバタ、これだけで10分短くなった」"},
        {"bucket": "B",  "theme": "癇癪がひどい時期の保育士的対処法",       "angle": "専門知識×体験談", "first_line": "「癇癪、止めようとするから長引く」"},
        {"bucket": "A",  "theme": "ワンオペで限界だった日の翌朝",            "angle": "感情の変化を描く", "first_line": "「昨夜泣いたくせに、朝になったらまた動けてる」"},
    ]
    for d in defaults:
        if len(topics) >= 3:
            break
        if d["theme"] not in used:
            topics.append(d)

    return topics[:3]


def main():
    print("===== analyst.py 起動 =====")
    now = datetime.now(JST)

    history = HISTORY_FILE.read_text(encoding="utf-8")
    posts = parse_metrics(history)

    print(f"メトリクス取得済み投稿: {len(posts)}件")

    if not posts:
        print("分析対象なし。fetcherでメトリクスを取得してから実行してください。")
        print("===== analyst.py 完了 =====")
        return

    analysis = analyze(posts)

    # analysis-latest.md を更新
    lines = ["# analysis-latest.md ── エンゲージメント分析\n"]
    lines.append(f"更新日時: {now.strftime('%Y-%m-%d %H:%M')}\n\n")

    lines.append("## 投稿別パフォーマンス\n\n")
    lines.append("| テーマ | 型 | フック | 投稿日 | views | likes | replies | score | いいね率 | quality |\n")
    lines.append("|--------|---|---|--------|-------|-------|---------|-------|---------|--------|\n")
    for p in sorted(posts, key=lambda x: x["score"], reverse=True):
        lines.append(
            f"| {p['theme'][:28]} | {p['post_type']} | {p['hook']} | {p['date']} "
            f"| {p['views']} | {p['likes']} | {p['replies']} | {p['score']} "
            f"| {p['like_rate']:.2f}% | {p['quality']:.2f}% |\n"
        )

    lines.append("\n## カテゴリ別平均スコア\n\n")
    for b, avg in sorted(analysis["bucket_avg"].items(), key=lambda x: x[1], reverse=True):
        label = CATEGORY_LABELS.get(b, b)
        lines.append(f"- **{label}**（{b}）: 平均スコア {avg}\n")

    if analysis.get("best"):
        lines.append("\n## ハイライト\n\n")
        best = analysis['best'][0]
        lines.append(
            f"**最高スコア**: 「{best['theme']}」"
            f"（score={best['score']}, 型={best['post_type']}, フック={best['hook']}, views={best['views']}）\n\n"
        )

    ANALYSIS_FILE.write_text("".join(lines), encoding="utf-8")
    print("analysis-latest.md を更新しました")

    # performance-patterns.md を生成・更新
    generate_performance_patterns(posts, now)

    # next-topics.md を追記モードで更新（既存テーマを消さない）
    topics = generate_topics(analysis)

    existing = ""
    if TOPICS_FILE.exists():
        existing = TOPICS_FILE.read_text(encoding="utf-8")

    existing_themes = set(re.findall(r'^## テーマ\d+：(.+)', existing, re.MULTILINE))
    existing_nums   = [int(n) for n in re.findall(r'^## テーマ(\d+)', existing, re.MULTILINE)]
    next_num        = max(existing_nums) + 1 if existing_nums else 1
    new_topics      = [t for t in topics if t["theme"] not in existing_themes]

    if not new_topics:
        print("追加するテーマなし（すべて既存に含まれています）")
    else:
        if not existing.strip():
            header = (
                f"# next-topics.md ── 次回投稿テーマ提案\n"
                f"更新日時: {now.strftime('%Y-%m-%d %H:%M')}\n"
                f"※ /writerはここからテーマを選んで投稿を生成する\n\n"
            )
            TOPICS_FILE.write_text(header, encoding="utf-8")
        else:
            updated = re.sub(r'更新日時: .+', f'更新日時: {now.strftime("%Y-%m-%d %H:%M")}', existing, count=1)
            TOPICS_FILE.write_text(updated, encoding="utf-8")

        with TOPICS_FILE.open("a", encoding="utf-8") as f:
            for t in new_topics:
                label = CATEGORY_LABELS.get(t["bucket"], t["bucket"])
                f.write(f"## テーマ{next_num}：{t['theme']}\n")
                f.write(f"**カテゴリ**: {label}（{t['bucket']}）\n")
                f.write(f"**切り口**: {t['angle']}\n")
                f.write(f"**1行目案**: {t['first_line']}\n\n")
                f.write("---\n\n")
                next_num += 1

        print(f"next-topics.md に{len(new_topics)}件のテーマを追記しました")

    print("\n【提案テーマ】")
    for t in topics:
        print(f"  [{t['bucket']}] {t['theme']}")

    print("===== analyst.py 完了 =====")


if __name__ == "__main__":
    main()
