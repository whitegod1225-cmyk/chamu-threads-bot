"""
analyst.py — post-history.md のメトリクスを分析して next-topics.md を更新する
fetcherがメトリクスを取得した後に実行する
"""
import re
import sys
import io
from pathlib import Path
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HISTORY_FILE = Path(__file__).parent / "post-history.md"
ANALYSIS_FILE = Path(__file__).parent / "analysis-latest.md"
TOPICS_FILE = Path(__file__).parent / "next-topics.md"
JST = timezone(timedelta(hours=9))

# カテゴリ分類（fetcher/reorder_queueと同じロジック）
CATEGORY_LABELS = {
    "A": "感情・共感系",
    "AC": "ワンオペ・保育園共感系",
    "B": "専門知識系",
    "DE": "グッズ・節約系",
    "note": "note誘導",
}

def classify(category: str) -> str:
    if "note誘導" in category:
        return "note"
    if any(k in category for k in ["専門知識", "グッズ・専門知識"]):
        return "B"
    if any(k in category for k in ["グッズ", "節約"]):
        return "DE"
    if any(k in category for k in ["ワーママ", "入園準備", "入園後", "入園", "ワンオペ"]):
        return "AC"
    if any(k in category for k in ["共感", "体験談", "問いかけ", "生活系"]):
        return "A"
    return "A"


def parse_metrics(history: str) -> list:
    """post-history.md からメトリクス付き投稿を抽出"""
    posts = []
    blocks = re.split(r'\n## 投稿', history)

    for block in blocks:
        if not re.match(r'\d+', block):
            continue

        # メトリクスがある投稿のみ
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

        theme    = m_theme.group(1).strip() if m_theme else "不明"
        category = m_cat.group(1).strip() if m_cat else "不明"
        date_str = m_date.group(1) if m_date else "不明"

        # エンゲージメントスコア（いいね×3 + コメント×5 + リポスト×4）
        score = likes * 3 + replies * 5 + reposts * 4

        posts.append({
            "theme": theme,
            "category": category,
            "bucket": classify(category),
            "date": date_str,
            "views": views,
            "likes": likes,
            "replies": replies,
            "reposts": reposts,
            "score": score,
        })

    return posts


def analyze(posts: list) -> dict:
    if not posts:
        return {}

    sorted_by_score = sorted(posts, key=lambda x: x["score"], reverse=True)

    # カテゴリ別平均スコア
    bucket_scores = {}
    for p in posts:
        b = p["bucket"]
        if b not in bucket_scores:
            bucket_scores[b] = []
        bucket_scores[b].append(p["score"])

    bucket_avg = {
        b: round(sum(scores) / len(scores), 1)
        for b, scores in bucket_scores.items()
    }

    return {
        "total": len(posts),
        "best": sorted_by_score[:3],
        "worst": sorted_by_score[-3:],
        "bucket_avg": bucket_avg,
    }


def generate_topics(analysis: dict) -> list:
    """分析結果から次のテーマを3つ提案"""
    if not analysis:
        return []

    topics = []
    bucket_avg = analysis.get("bucket_avg", {})

    # 最も伸びているカテゴリを優先
    sorted_buckets = sorted(bucket_avg.items(), key=lambda x: x[1], reverse=True)
    best_bucket = sorted_buckets[0][0] if sorted_buckets else "AC"

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
                        "bucket": bucket,
                        "theme": suggestion[0],
                        "angle": suggestion[1],
                        "first_line": suggestion[2],
                    })
                    used.add(key)
                if len(topics) >= 3:
                    break
        if len(topics) >= 3:
            break

    # 足りなければデフォルト補充
    defaults = [
        {"bucket": "AC", "theme": "保育園ある日の朝をラクにした3つの工夫", "angle": "生活改善×共感", "first_line": "「朝のバタバタ、これだけで10分短くなった」"},
        {"bucket": "B", "theme": "癇癪がひどい時期の保育士的対処法", "angle": "専門知識×体験談", "first_line": "「癇癪、止めようとするから長引く」"},
        {"bucket": "A", "theme": "ワンオペで限界だった日の翌朝", "angle": "感情の変化を描く", "first_line": "「昨夜泣いたくせに、朝になったらまた動けてる」"},
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
    lines = [f"# analysis-latest.md ── エンゲージメント分析\n"]
    lines.append(f"更新日時: {now.strftime('%Y-%m-%d %H:%M')}\n\n")

    lines.append("## 投稿別パフォーマンス\n\n")
    lines.append("| テーマ | カテゴリ | 投稿日 | views | likes | replies | reposts | score |\n")
    lines.append("|--------|---------|--------|-------|-------|---------|---------|-------|\n")
    for p in sorted(posts, key=lambda x: x["score"], reverse=True):
        lines.append(f"| {p['theme']} | {p['category']} | {p['date']} | {p['views']} | {p['likes']} | {p['replies']} | {p['reposts']} | {p['score']} |\n")

    lines.append("\n## カテゴリ別平均スコア\n\n")
    for b, avg in sorted(analysis["bucket_avg"].items(), key=lambda x: x[1], reverse=True):
        label = CATEGORY_LABELS.get(b, b)
        lines.append(f"- **{label}**（{b}）: 平均スコア {avg}\n")

    if analysis.get("best"):
        lines.append("\n## ハイライト\n\n")
        lines.append(f"**最高スコア**: 「{analysis['best'][0]['theme']}」（score={analysis['best'][0]['score']}, likes={analysis['best'][0]['likes']}, views={analysis['best'][0]['views']}）\n\n")
        if len(analysis["best"]) > 1:
            lines.append(f"**伸びたカテゴリ**: {analysis['best'][0]['category']}\n\n")

    ANALYSIS_FILE.write_text("".join(lines), encoding="utf-8")
    print("analysis-latest.md を更新しました")

    # next-topics.md を生成
    topics = generate_topics(analysis)

    topic_lines = [f"# next-topics.md ── 次回投稿テーマ提案\n"]
    topic_lines.append(f"更新日時: {now.strftime('%Y-%m-%d %H:%M')}\n")
    topic_lines.append("※ /writerはここからテーマを選んで投稿を生成する\n\n")

    for i, t in enumerate(topics, 1):
        label = CATEGORY_LABELS.get(t["bucket"], t["bucket"])
        topic_lines.append(f"## テーマ{i}：{t['theme']}\n")
        topic_lines.append(f"**カテゴリ**: {label}（{t['bucket']}）\n")
        topic_lines.append(f"**切り口**: {t['angle']}\n")
        topic_lines.append(f"**1行目案**: {t['first_line']}\n\n")
        topic_lines.append("---\n\n")

    TOPICS_FILE.write_text("".join(topic_lines), encoding="utf-8")
    print(f"next-topics.md に{len(topics)}件のテーマを保存しました")

    print("\n【提案テーマ】")
    for t in topics:
        print(f"  [{t['bucket']}] {t['theme']}")

    print("===== analyst.py 完了 =====")


if __name__ == "__main__":
    main()
