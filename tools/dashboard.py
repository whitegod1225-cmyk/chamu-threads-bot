#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ちゃむ。コンテンツダッシュボード
Usage:
    cd content-tool
    python tools/dashboard.py
    python tools/dashboard.py --port 5001 --no-browser
"""

import os
import re
import json
import argparse
import threading
import webbrowser
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
except ImportError:
    raise SystemExit("pip install flask flask-cors  を実行してください")

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent
QUEUE_FILE   = BASE_DIR / "skills" / "queue" / "post-queue.md"
HISTORY_FILE = BASE_DIR / "skills" / "queue" / "post-history.md"
HTML_FILE    = Path(__file__).resolve().parent / "dashboard.html"

app = Flask(__name__)
CORS(app)

# ── Parser ────────────────────────────────────────────────────

def parse_queue(filepath=QUEUE_FILE):
    if not filepath.exists():
        return []
    content = filepath.read_text(encoding="utf-8")
    posts = []
    parts = re.split(r'\n(?=## 投稿\d+\n)', "\n" + content)
    for part in parts:
        m = re.match(r'\n?## 投稿(\d+)\n', part)
        if not m:
            continue
        pid = int(m.group(1))

        def g(pat, default=""):
            r = re.search(pat, part)
            return r.group(1).strip() if r else default

        theme    = g(r'\*\*テーマ\*\*：「(.+?)」')
        cat_full = g(r'\*\*カテゴリ\*\*：(.+)')
        season   = g(r'\*\*時期\*\*：(.+)')
        product  = g(r'\*\*商品\*\*：(.+)')

        body_m    = re.search(r'\*\*本文\*\*\n([\s\S]*?)(?=\n\*\*コメント欄|\n---|\Z)', part)
        comment_m = re.search(r'\*\*コメント欄（セルフリプライ用）\*\*\n([\s\S]*?)(?=\n---|\Z)', part)

        body    = body_m.group(1).strip()    if body_m    else ""
        comment = comment_m.group(1).strip() if comment_m else ""
        cm = re.match(r'([A-Z])', cat_full)
        cat_letter = cm.group(1) if cm else "B"

        posts.append({
            "id":           pid,
            "theme":        theme,
            "category":     cat_letter,
            "category_full": cat_full,
            "season":       season,
            "product":      product,
            "body":         body,
            "comment":      comment,
        })
    return posts

# ── Writer ────────────────────────────────────────────────────

QUEUE_HEADER = """\
# post-queue.md ── 投稿待ちキュー
ライターが作成した投稿をここに追加する。
ポスターは一番上の投稿を取り出してThreadsに投稿する。
投稿済みのものはここから削除してpost-history.mdに移す。

> ⚠️ **【必須】このファイルを更新したら必ず `git push` すること**
> GitHub Actionsはこのファイルの**GitHub上のバージョン**を読む。
> pushしないと新しい投稿は一切自動投稿されない。

---

"""

def write_queue(posts, filepath=QUEUE_FILE):
    blocks = []
    for p in posts:
        lines = [f"## 投稿{p['id']}"]
        lines.append(f"**テーマ**：「{p['theme']}」")
        lines.append(f"**カテゴリ**：{p['category_full']}")
        if p.get("product"):
            lines.append(f"**商品**：{p['product']}")
        lines.append(f"**時期**：{p['season']}")
        lines.append("")
        lines.append("**本文**")
        lines.append(p["body"])
        lines.append("")
        lines.append("**コメント欄（セルフリプライ用）**")
        lines.append(p["comment"])
        blocks.append("\n".join(lines))
    content = QUEUE_HEADER + "\n\n---\n\n".join(blocks) + "\n"
    filepath.write_text(content, encoding="utf-8")

# ── Smart Insertion ───────────────────────────────────────────

THEME_MAP = {
    "肌着":      ["肌着", "ヨレ", "汗疹", "プチバトー"],
    "シャンプー": ["シャンプー", "アラウ", "アトピー"],
    "ベビーカー": ["ベビーカー", "ファン付き", "シート"],
    "ひとりっ子": ["ひとりっ子", "一人っ子"],
    "空気清浄機": ["空気清浄機", "KLOUDIC"],
    "ミニカー":   ["ミニカー"],
}

def theme_tag(text):
    for tag, kws in THEME_MAP.items():
        if any(k in text for k in kws):
            return tag
    return None

def find_insert_pos(posts, new_cat, new_theme):
    n = len(posts)
    for i in range(n, -1, -1):
        prev2 = posts[max(0, i-2):i]
        next2 = posts[i:i+2]
        if new_cat == "E" and any(p["category"] == "E" for p in prev2 + next2):
            continue
        if new_theme:
            nb = posts[max(0, i-1):i] + posts[i:i+1]
            if new_theme in [theme_tag(p["theme"] + p.get("body", "")) for p in nb]:
                continue
        return i
    return n

# ── History stats ─────────────────────────────────────────────

def history_stats():
    if not HISTORY_FILE.exists():
        return 0, {}
    content = HISTORY_FILE.read_text(encoding="utf-8")
    ids = re.findall(r'^## 投稿(\d+)', content, re.M)
    return len(ids), {}

# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_FILE.read_text(encoding="utf-8")

@app.route("/api/queue")
def api_queue():
    return jsonify(parse_queue())

@app.route("/api/stats")
def api_stats():
    posts = parse_queue()
    cats  = {}
    for p in posts:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    hist_total, _ = history_stats()
    affiliate_ratio = round(cats.get("E", 0) / len(posts) * 100) if posts else 0
    return jsonify({
        "queue_total":      len(posts),
        "history_total":    hist_total,
        "categories":       cats,
        "affiliate_ratio":  affiliate_ratio,
        "next_post":        posts[0] if posts else None,
    })

@app.route("/api/queue/reorder", methods=["POST"])
def api_reorder():
    ids = request.json.get("order", [])
    posts = parse_queue()
    pm = {p["id"]: p for p in posts}
    reordered = [pm[i] for i in ids if i in pm]
    write_queue(reordered)
    return jsonify({"ok": True})

@app.route("/api/queue/<int:pid>", methods=["DELETE"])
def api_delete(pid):
    posts = parse_queue()
    posts = [p for p in posts if p["id"] != pid]
    write_queue(posts)
    return jsonify({"ok": True})

@app.route("/api/queue/move", methods=["POST"])
def api_move():
    data  = request.json
    pid   = data["id"]
    direction = data["direction"]  # "up" | "down"
    posts = parse_queue()
    idx = next((i for i, p in enumerate(posts) if p["id"] == pid), None)
    if idx is None:
        return jsonify({"ok": False, "error": "not found"}), 404
    if direction == "up" and idx > 0:
        posts[idx], posts[idx-1] = posts[idx-1], posts[idx]
    elif direction == "down" and idx < len(posts) - 1:
        posts[idx], posts[idx+1] = posts[idx+1], posts[idx]
    write_queue(posts)
    return jsonify({"ok": True})

@app.route("/api/queue/add", methods=["POST"])
def api_add():
    data  = request.json
    posts = parse_queue()
    max_id = max((p["id"] for p in posts), default=400)
    new_id = max_id + 1

    new_post = {
        "id":           new_id,
        "theme":        data.get("theme", ""),
        "category":     data.get("category", "B"),
        "category_full": data.get("category_full", "B（育児知識・共感系）"),
        "season":       data.get("season", "通年"),
        "product":      data.get("product", ""),
        "body":         data.get("body", ""),
        "comment":      data.get("comment", ""),
    }

    tt  = theme_tag(new_post["theme"] + new_post["body"])
    idx = find_insert_pos(posts, new_post["category"], tt)
    posts.insert(idx, new_post)
    write_queue(posts)

    # Build neighbor context for display
    prev_id = posts[idx-1]["id"] if idx > 0               else None
    next_id = posts[idx+1]["id"] if idx < len(posts)-1     else None

    return jsonify({
        "ok": True, "id": new_id,
        "position": idx + 1, "total": len(posts),
        "prev_id": prev_id, "next_id": next_id,
    })

# ── Generate ──────────────────────────────────────────────────

CHAMU_PROFILE = (
    "元保育士・児童指導員（合計16年経験）、30代・3人の母、保育した子ども1000人以上。\n"
    "育児に自信をなくした・疲れ果てた・孤独を感じているママがターゲット。\n"
    "子どもは全員現在小学生。育児体験は過去形で語る。\n"
    "「16年やってきたのに自分の子には通じなかった」が最大の武器。"
)

SYSTEM_TEMPLATES = {
    "normal": """\
あなたは「ちゃむ。」としてThreads投稿文を書く専門ライターです。

■ ちゃむ。のペルソナ
{profile}

■ 文体ルール（絶対守る）
- 友人への語りかけ口調・タメ口
- 文末「。」を使わない
- 200〜350文字（本文）
- 体験・場面描写から入る（説明型・箇条書き型NG）
- AIっぽい定型文禁止。具体的な数字・エピソードを必ず入れる
- 本文の最後は話が途中で切れる形で終わらせる（コメント欄を読まないと完結しない）
- コメント欄：本文の続き + 末尾にCTAを1つ（フォロー誘導/保存誘導/コメント誘導のどれか）

■ タスク：通常投稿を3本生成する
投稿①：概念再定義型（「それは〇〇じゃない」で罪悪感を溶かす）
投稿②：知識/有益情報型（保育士視点の具体的な知識。「ママのせいじゃない」免責を入れる）
投稿③：告白・報告型（「16年保育士なのに〜」の権威崩し）

■ 出力形式（JSONのみ・前置き/後書き/コードフェンス一切禁止）
{{"posts": [
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言", "category": "B", "category_full": "B（育児知識・共感系）／概念再定義型", "season": "通年"}},
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言", "category": "B", "category_full": "B（育児知識・共感系）／有益情報型", "season": "通年"}},
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言", "category": "F", "category_full": "F（保育士の本音系）／告白型", "season": "通年"}}
]}}""",

    "consultation": """\
あなたは「ちゃむ。」としてThreads投稿文を書く専門ライターです。

■ ちゃむ。のペルソナ
{profile}

■ 絶対守るルール（最重要）
相談文を直接引用・言及しない。「相談を受けた」「こんな相談が来た」は禁止。
「保育士のころ、同じことで悩んでいるお母さんと話したことがある」「園で何度も見てきた場面だった」のように、自分の経験として語る。

■ 文体ルール
- 友人への語りかけ口調・タメ口・文末「。」禁止
- 200〜350文字（本文）・体験・場面描写から入る
- 本文の最後は話が途中で切れる形で終わらせる

■ タスク：相談文から投稿3本を生成する
投稿①：共感型（その気持ちを「これ、私も言われた」「保育士のころ〜」形式で代弁する）
投稿②：知識型（保育士として「ママのせいじゃない」免責＋具体的な知識）
投稿③：note誘導型（感情的な悩みなのでnoteへ誘導。URLは「ちゃむ。のnoteへ」のみ許可。URL直貼り禁止）

■ 出力形式（JSONのみ・前置き/後書き禁止）
{{"posts": [
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言", "category": "B", "category_full": "B（育児知識・共感系）／共感型", "season": "通年"}},
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言", "category": "B", "category_full": "B（育児知識・共感系）／有益情報型", "season": "通年"}},
  {{"body": "本文", "comment": "コメント欄", "theme": "テーマ一言（note誘導）", "category": "B", "category_full": "B（育児知識・共感系）／note誘導型", "season": "通年"}}
]}}""",

    "affiliate": """\
あなたは「ちゃむ。」としてThreadsアフィリエイト投稿文を書く専門ライターです。

■ ちゃむ。のペルソナ
{profile}

■ 大原則：売り込み感を出さない
1行目は商品ではなく場面描写・地味な不快から入る。「これ買えばいい」ではなく「昨日の夜〜してたとき」の入り。

■ 文体ルール
- 本文3行以内
- 場面描写・共感・フックのみ（商品名・価格・スペックは本文に絶対書かない）
- 最終行は必ず中途半端に終わらせる（「だって」「それが」「その方法が」等）
- コメント欄：1行目で本文の続きをつなぐ→具体的なベネフィット2〜4行→「（PR）」→楽天URL（[楽天アフィリエイトURL]とプレースホルダーで出す）

■ 出力形式（JSONのみ・前置き/後書き禁止）
{{"posts": [
  {{"body": "本文（3行以内）", "comment": "コメント欄（ベネフィット＋（PR）＋[楽天アフィリエイトURL]）", "theme": "テーマ一言", "category": "E", "category_full": "E（節約・グッズ・生活系）／型13：楽天アフィリエイト体験談型", "season": "通年（または夏などの季節）", "product": "商品カテゴリ名"}}
]}}""",
}

def build_system(mode):
    tpl = SYSTEM_TEMPLATES.get(mode, SYSTEM_TEMPLATES["normal"])
    return tpl.format(profile=CHAMU_PROFILE)

def build_user(mode, content):
    prefixes = {
        "normal":       "テーマ：",
        "consultation": "相談文：\n",
        "affiliate":    "商品・テーマ：",
    }
    prefix = prefixes.get(mode, "テーマ：")
    return f"{prefix}{content}\n\n上記の条件でJSON形式で生成してください。"

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data    = request.json
    mode    = data.get("mode", "normal")
    content = data.get("content", "").strip()
    api_key = data.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return jsonify({"error": "APIキーが設定されていません（.envにANTHROPIC_API_KEYを設定してください）"}), 400
    if not content:
        return jsonify({"error": "テーマまたは相談文を入力してください"}), 400

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=build_system(mode),
            messages=[{"role": "user", "content": build_user(mode, content)}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"posts": [{"body": raw, "comment": "", "theme": "生成結果", "category": "B",
                                  "category_full": "B（育児知識・共感系）", "season": "通年", "product": ""}]}
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ちゃむ。コンテンツダッシュボード")
    parser.add_argument("--port",       type=int, default=5050)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    print(f"\n  ちゃむ。ダッシュボード起動中 → {url}\n")

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
