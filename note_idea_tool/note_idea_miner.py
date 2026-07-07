"""
note_idea_miner.py
consultation_log.json に溜まった相談要約（人が要約済みのもの）と
反応の良かったThreads投稿データをもとに、
noteアイデア記事のネタ候補をAIにクラスタリングして提案するツール。

出力はレポート(Markdown)のみ。自動でnoteに投稿しない。
consultation_log.jsonの「使用済み」フラグを立てるのもしない。
実際に記事化すると決めたら:
  python tag_consultation.py mark-used --id C-xxxx --note-id N-xxxx
で明示的にマーク（人の最終判断を必ず挟む設計）。

使い方:
  python note_idea_miner.py --top-posts 5
"""

import os
import sys
import json
import argparse
import time
import urllib.request

TOKEN_ENV = "ANTHROPIC_API_KEY"
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

HERE = os.path.dirname(__file__)
LOG_PATH = os.path.join(HERE, "consultation_log.json")
POST_META_PATH = os.path.join(HERE, "..", "threads_tool", "post_meta.json")
METRICS_CACHE_PATH = os.path.join(HERE, "..", "threads_tool", "threads_metrics_cache.json")
REPORT_DIR = os.path.join(HERE, "note_idea_reports")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_api_key():
    key = os.environ.get(TOKEN_ENV)
    if not key:
        sys.exit(f"エラー: 環境変数 {TOKEN_ENV} を設定してください。")
    return key


def call_claude(system_prompt, user_prompt, max_tokens=2000):
    key = get_api_key()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def get_unused_consultations():
    log = load_json(LOG_PATH, [])
    return [r for r in log if not r.get("used_in_note")]


def get_top_posts(limit=5):
    """post_meta.json + threads_metrics_cache.json からエンゲージメントの高い投稿を抽出。
    どちらかが無い/空でもエラーにせずスキップ（相談要約だけでもネタ出しは可能）。"""
    meta = load_json(POST_META_PATH, [])
    cache = load_json(METRICS_CACHE_PATH, {})
    permalink_metrics = {v.get("permalink"): v for v in cache.values() if v.get("permalink")}

    scored = []
    for m in meta:
        if "投稿ID" not in m or "_comment" in m:
            continue
        metrics = permalink_metrics.get(m.get("permalink"))
        if not metrics:
            continue
        views = metrics.get("views") or 0
        likes = metrics.get("likes") or 0
        replies = metrics.get("replies") or 0
        reposts = metrics.get("reposts") or 0
        quotes = metrics.get("quotes") or 0
        # スコア式: likes×3 + replies×5 + reposts×2（Threadsアルゴリズム推定重み）
        score = likes * 3 + replies * 5 + reposts * 2
        quality_score = score / views if views else 0
        scored.append((quality_score, m, metrics))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def build_prompt(consultations, top_posts):
    consult_lines = []
    for r in consultations:
        consult_lines.append(
            f"- ID:{r['id']} 分類:{r.get('大分類')}/{r.get('中分類')} "
            f"年齢帯:{r.get('対象年齢帯')} 状態:{r.get('親の状態タグ')} "
            f"要約:{r['summary']}"
        )

    post_lines = []
    for quality_score, m, metrics in top_posts:
        views = metrics.get("views") or 0
        likes = metrics.get("likes") or 0
        replies = metrics.get("replies") or 0
        post_lines.append(
            f"- 投稿ID:{m.get('投稿ID')} テーマ:{m.get('テーマ')} "
            f"型:{m.get('型番号')} views:{views} likes:{likes} replies:{replies} "
            f"質スコア:{quality_score:.2%}"
        )

    return (
        "【蓄積された相談要約】\n" + ("\n".join(consult_lines) if consult_lines else "(なし)") +
        "\n\n【反応が良かった過去投稿】\n" + ("\n".join(post_lines) if post_lines else "(データなし)")
    )


def mine_ideas(consultations, top_posts):
    system_prompt = """あなたはnote執筆記事の企画者です。
複数の相談要約と過去に反応の良かった投稿データから、
展開できるパターンを見つけて、note執筆記事のネタ候補を最大5本企画してください。

読者は「子育てに失敗している気がする」疲れた・孤独な母親たち。企画の起点は情報の需要ではなく、感情の着地点です。各ネタは必ず次の3つの着地感情のどれか1つに向けて設計すること：
1. 代わりに言ってくれた感（罪悪感→赦し）
2. 気づかせてくれた感（謎→認知的快感）
3. 仲間がいる感（孤独→連帯）

ルール:
- 1本のネタには、根拠となる相談IDを最低1つ以上ひも付けること(裏付けのない企画は作らない)。
- 相談の生テキストをそのまま引用しない。パターンとして抽象化すること。
- サムネイル用の画像生成プロンプトは、実在の人物・キャラクター・ブランドを含まない。
  抽象的で温かみのあるイラスト調の指示にすること。
- priorityの判定基準：「高」＝相談データと反応の良かった投稿の両方がテーマを裏付ける。「中」＝どちらか一方のみ。「低」＝どちらの裏付けも弱いが、感情の論理が強い。
- 出力は必ずJSON配列のみ。前置き・後書き・Markdown記法は禁止。

各要素のフィールド:
  title: note記事タイトル案
  target: 想定読者
  hook: 冒頭フックの方向性(矛盾/驚き/否定のどれを使うか、具体的に)
  outline: 記事構成のメモ(3〜4行、体験→気づき→締めの流れ)
  landing_emotion: 3つの着地感情のどれか＋「なぜこの相談クラスタが自然にその感情に向かうのか」を1文で。ルールの引用ではなく、この相談群の感情の力学についての洞察を書くこと。
  resonance_reason: この記事がようやく名前を与える「声に出せなかったもの」は何か。母親たちが口に出せずにいる傷、あるいは飢えを、洞察として2〜3文で書く。記事の内容説明・チェックリストは禁止。読者の内側にあるものだけを書く。
  recommended_type: "型2"（プロが同じ敵に負ける敗北報告、教訓で終わらない）/ "B型"（知識＋「ママのせいじゃない」免責＋末尾に個人体験の接ぎ木）/ "hybrid" のいずれか＋その型を選ぶことで記事の組み立てがどう変わるかを1文で。
  threads_hook_hint: この記事へ読者を連れてくるThreads投稿のフックの示唆。Threadsでは感情を「開いたまま」にし、noteが同じ傷をさらに深く掘る続きになるように設計する（noteで感情を仕切り直させない）。その開き方を具体的に書く。
  supporting_ids: 根拠となる相談ID・投稿IDの配列
  thumbnail_prompt: サムネイル画像生成用プロンプト(日本語、100字程度)
  priority: "高" "中" "低" のいずれか(上記の判定基準に従う)
"""
    user_prompt = build_prompt(consultations, top_posts)
    raw = call_claude(system_prompt, user_prompt)
    cleaned = raw.strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def render_report(ideas, consultations, top_posts):
    date_str = time.strftime("%Y-%m-%d")
    lines = [f"# noteネタ企画案 ({date_str})", ""]
    lines.append(f"入力データ: 相談要約 {len(consultations)}件 / 好反応投稿 {len(top_posts)}件")
    lines.append("")
    for i, idea in enumerate(ideas, 1):
        lines.append(f"## {i}. {idea.get('title')}  [優先度: {idea.get('priority')}]")
        lines.append(f"- 想定読者: {idea.get('target')}")
        lines.append(f"- フックの方向性: {idea.get('hook')}")
        lines.append(f"- 着地感情: {idea.get('landing_emotion')}")
        lines.append(f"- 共鳴の理由: {idea.get('resonance_reason')}")
        lines.append(f"- 推奨型: {idea.get('recommended_type')}")
        lines.append(f"- Threadsフックのヒント: {idea.get('threads_hook_hint')}")
        lines.append(f"- 構成メモ: {idea.get('outline')}")
        lines.append(f"- 根拠ID: {', '.join(idea.get('supporting_ids', []))}")
        lines.append(f"- サムネプロンプト: {idea.get('thumbnail_prompt')}")
        lines.append("")
    lines.append("---")
    lines.append("採用する場合は、対応する相談IDに対して以下を実行してください:")
    lines.append("`python tag_consultation.py mark-used --id <ID> --note-id <note記事ID>`")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="相談要約と好反応投稿からnoteネタを提案")
    parser.add_argument("--top-posts", type=int, default=5)
    parser.add_argument("--min-consultations", type=int, default=2,
                         help="この件数未満なら実行を止める（ネタの裏付け不足を防ぐ）")
    args = parser.parse_args()

    consultations = get_unused_consultations()
    if len(consultations) < args.min_consultations:
        sys.exit(
            f"未使用の相談要約が{len(consultations)}件しかありません"
            f"（最低{args.min_consultations}件推奨）。"
            "tag_consultation.py add でもう少し蓄積してから実行してください。"
        )

    top_posts = get_top_posts(limit=args.top_posts)

    print("AIにネタ出し中...")
    ideas = mine_ideas(consultations, top_posts)

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, f"note_ideas_{time.strftime('%Y%m%d_%H%M%S')}.md")
    report = render_report(ideas, consultations, top_posts)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"{len(ideas)}件のネタ案を {report_path} に保存しました。")


if __name__ == "__main__":
    main()
