#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infographic_idea_miner.py
==========================
ちゃむ。用「保存したくなる育児図解ネタ」生成システム

既存の consultation-db.md の悩みデータ + Fable 5 で
保存したくなる育児図解ネタを機械的に生成・蓄積する。

【仕組み】
  属性軸 × 型（構成パターン） × 保存トリガー を組み合わせて
  Claude Fable 5 に渡し、タイトル・構成・キャッチコピーを生成。
  生成済みネタは skills/queue/infographic-ideas-db.md に蓄積し重複防止。

【使い方】
  cd content-tool
  export ANTHROPIC_API_KEY="sk-ant-..."

  python3 tools/infographic_idea_miner.py --count 10
  python3 tools/infographic_idea_miner.py --count 5 --axis 離乳食
  python3 tools/infographic_idea_miner.py --count 5 --format threads
  python3 tools/infographic_idea_miner.py --list-axes
  python3 tools/infographic_idea_miner.py --dry-run --count 5
"""

import os
import re
import json
import random
import argparse
from datetime import datetime
from pathlib import Path

import anthropic

# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------

MODEL = "claude-fable-5"
MAX_TOKENS = 2000

BASE_DIR = Path(__file__).resolve().parent.parent  # content-tool/ ルート
IDEAS_DB_PATH = BASE_DIR / "skills" / "queue" / "infographic-ideas-db.md"
CONSULTATION_DB_PATH = BASE_DIR / "skills" / "queue" / "consultation-db.md"

# ----------------------------------------------------------------------
# 軸の定義
# ----------------------------------------------------------------------

ATTRIBUTE_AXES = {
    "月齢_年齢": [
        "新生児(0-1ヶ月)", "生後2-3ヶ月", "生後4-6ヶ月", "生後7-8ヶ月",
        "生後9-11ヶ月", "1歳前半", "1歳後半", "2歳", "3歳", "4-5歳", "小学校入学前",
    ],
    "季節_行事": [
        "春(入園・進級)", "梅雨", "夏(熱中症・水遊び)", "秋(運動会・衣替え)",
        "冬(感染症シーズン)", "年末年始", "GW", "夏休み", "お盆帰省", "クリスマス",
    ],
    "性別関連": [
        "男の子あるある", "女の子あるある", "性別による発達差の誤解",
    ],
    "所属_環境": [
        "未就学児(在宅)", "保育園(0-2歳クラス)", "保育園(3-5歳クラス)",
        "幼稚園", "こども園", "一時保育", "保活",
    ],
    "発達_行動": [
        "イヤイヤ期(1歳後半-2歳)", "イヤイヤ期(3歳)", "赤ちゃん返り",
        "夜泣き", "後追い", "トイトレ", "指しゃぶり", "かみつき", "自我の芽生え",
    ],
    "健康_病気": [
        "発熱時の対応", "感染症(RSウイルス等)", "アレルギー", "便秘",
        "皮膚トラブル", "予防接種スケジュール", "歯の生え方",
    ],
    "衣服": [
        "季節の服装の目安", "サイズアウトのサイン", "保育園の着替え準備",
        "着脱しやすい服の選び方",
    ],
    "食事_離乳食": [
        "離乳食初期", "離乳食中期", "離乳食後期", "完了期",
        "幼児食への移行", "偏食対応", "アレルギー食材の進め方", "外食デビュー",
    ],
    "乗り物_移動": [
        "ベビーカー選び", "チャイルドシート", "抱っこ紐", "電車移動",
        "車での長距離移動",
    ],
    "便利グッズ": [
        "月齢別あってよかったグッズ", "買ったけど使わなかったグッズ",
        "時短家電", "外出時の持ち物",
    ],
}

STRUCTURE_TYPES = {
    "チェックリスト型": "〇〇かどうか当てはまる項目をチェックする形式。自己診断できる安心感が保存動機。",
    "比較表型": "A案とB案、または月齢前後での違いを並べて比較。判断材料として保存される。",
    "タイムライン型": "月齢や時系列での変化を一覧化。将来の自分が見返す前提で保存される。",
    "NG_OK型": "やりがちなNG対応と、代わりのOK対応を対で示す。失敗を避けたい心理で保存される。",
    "早見表型": "数値・目安・基準を一覧化。都度検索する手間を省くために保存される。",
    "フローチャート型": "〇〇の場合は→こうする、を分岐で示す。緊急時や判断に迷う場面で保存される。",
}

SAVE_TRIGGERS = [
    "今は使わないが将来必ず使う情報だから",
    "人と比べて安心・不安を解消したいから",
    "緊急時にすぐ見返したいから",
    "知らなかった・目から鱗だったから",
    "誰かに教えたい(シェアしたい)から",
]

# ----------------------------------------------------------------------
# ユーティリティ
# ----------------------------------------------------------------------

def list_axes():
    print("【属性軸カテゴリ一覧】")
    for cat, items in ATTRIBUTE_AXES.items():
        print(f"\n■ {cat}")
        for i in items:
            print(f"   - {i}")
    print("\n【構成パターン(型)】")
    for k, v in STRUCTURE_TYPES.items():
        print(f"   - {k}: {v}")


def load_existing_titles() -> set:
    if not IDEAS_DB_PATH.exists():
        return set()
    text = IDEAS_DB_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"^### (.+)$", text, flags=re.MULTILINE))


def load_consultation_context(max_chars: int = 3000) -> str:
    if not CONSULTATION_DB_PATH.exists():
        return ""
    text = CONSULTATION_DB_PATH.read_text(encoding="utf-8")
    return text[:max_chars]


# ----------------------------------------------------------------------
# 組み合わせ生成
# ----------------------------------------------------------------------

def pick_combinations(count: int, axis_filter: str | None) -> list[dict]:
    combos = []
    categories = list(ATTRIBUTE_AXES.keys())
    for _ in range(count):
        if axis_filter:
            matched = [
                (cat, item)
                for cat in categories
                for item in ATTRIBUTE_AXES[cat]
                if axis_filter in cat or axis_filter in item
            ]
            if not matched:
                raise ValueError(f"'{axis_filter}' に一致する軸が見つかりません。--list-axes で確認してください。")
            cat, attr = random.choice(matched)
        else:
            cat = random.choice(categories)
            attr = random.choice(ATTRIBUTE_AXES[cat])

        structure = random.choice(list(STRUCTURE_TYPES.keys()))
        trigger = random.choice(SAVE_TRIGGERS)
        combos.append({
            "category": cat,
            "attribute": attr,
            "structure": structure,
            "structure_desc": STRUCTURE_TYPES[structure],
            "trigger": trigger,
        })
    return combos


# ----------------------------------------------------------------------
# Fable呼び出し
# ----------------------------------------------------------------------

SYSTEM_PROMPT = """あなたは「ちゃむ。」という育児コンテンツ発信者のブレーンです。

■ちゃむ。のペルソナ
元保育士・児童指導員(合計16年経験)、30代・3人の母、保育した子ども1000人以上。
育児に自信をなくした・疲れ果てた・孤独を感じているママがターゲット。
子どもは全員現在小学生。育児体験は過去形で語る。

■あなたの役割
与えられた「属性軸」「構成パターン(型)」「保存トリガー」の組み合わせを元に、
ちゃむ。が実際の保育士経験から語れる、具体的で保存したくなる育児図解ネタを1つ作ってください。

■絶対条件
- AIっぽい一般論・当たり障りのない内容は禁止。保育士としての具体的な経験・数字・エピソードの匂いを必ず入れる
- タイトルは「逆張り」「驚き」「知らないと損」のどれかを含める
- 図解の構成項目は3〜6個。Instagram/Threadsの1枚絵やnoteの図解として使える粒度にする
- キャッチコピーは20字以内
- 出力は必ず以下のJSON形式のみ。前置き・Markdown記法は一切つけない

{
  "title": "図解のタイトル(保存したくなるフック)",
  "catchphrase": "20字以内のキャッチコピー",
  "structure_items": ["項目1", "項目2", "項目3"],
  "episode_hook": "保育士経験に基づく具体的なひとことエピソード(50字程度)",
  "why_saved": "なぜこれが保存されるのか(具体的理由)",
  "format_suggestion": "threads単体 or note連載 のどちらが向いているか、理由付きで",
  "hashtags": ["#タグ1", "#タグ2", "#タグ3"]
}
"""


def generate_idea(client: anthropic.Anthropic, combo: dict, consultation_context: str, fmt_hint: str | None) -> dict:
    user_prompt = f"""【今回の組み合わせ】
属性軸カテゴリ: {combo['category']}
具体的な属性: {combo['attribute']}
構成パターン(型): {combo['structure']}（{combo['structure_desc']}）
保存トリガー: {combo['trigger']}
"""
    if fmt_hint:
        user_prompt += f"\n【フォーマット指定】{fmt_hint} 向けに最適化してください。\n"
    if consultation_context:
        user_prompt += f"\n【参考: 実際のママからの相談データ(抜粋)】\n{consultation_context}\n"
    user_prompt += "\n上記条件でJSON形式の図解ネタを1つ生成してください。"

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = "".join(b.text for b in response.content if b.type == "text").strip()
    raw_text = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip())

    try:
        idea = json.loads(raw_text)
    except json.JSONDecodeError:
        idea = {"title": "[パース失敗]", "raw": raw_text}

    idea["_combo"] = combo
    return idea


# ----------------------------------------------------------------------
# 保存
# ----------------------------------------------------------------------

def save_ideas(ideas: list[dict]):
    lines = []
    if not IDEAS_DB_PATH.exists():
        IDEAS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines.append("# infographic-ideas-db.md ── 育児図解ネタ銀行\n")
        lines.append("> Fableが生成した図解ネタを蓄積。/zu-writerで使うときはここから選ぶ。\n")
        lines.append("> 転用ステータス: 未着手 / zu-writer済み / 投稿済み\n")

    for idea in ideas:
        if "raw" in idea:
            continue
        combo = idea.get("_combo", {})
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines += [
            "\n---\n",
            f"### {idea.get('title', '無題')}\n",
            f"- 生成日: {ts}",
            f"- 軸: {combo.get('category')} / {combo.get('attribute')}",
            f"- 型: {combo.get('structure')}",
            f"- 保存トリガー: {combo.get('trigger')}",
            f"- キャッチコピー: {idea.get('catchphrase', '')}",
            "- 構成項目:",
        ]
        for item in idea.get("structure_items", []):
            lines.append(f"  - {item}")
        lines += [
            f"- エピソードフック: {idea.get('episode_hook', '')}",
            f"- 保存される理由: {idea.get('why_saved', '')}",
            f"- フォーマット推奨: {idea.get('format_suggestion', '')}",
            f"- ハッシュタグ: {' '.join(idea.get('hashtags', []))}",
            "- 転用ステータス: 未着手",
        ]

    with open(IDEAS_DB_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ----------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ちゃむ。育児図解ネタ生成（Fable使用）")
    parser.add_argument("--count", type=int, default=5, help="生成するネタ数（デフォルト5）")
    parser.add_argument("--axis", type=str, default=None, help="軸を絞り込む文字列（例: 離乳食, イヤイヤ期）")
    parser.add_argument("--format", type=str, default=None, choices=["threads", "note"], help="出力フォーマットのヒント")
    parser.add_argument("--list-axes", action="store_true", help="利用可能な軸一覧を表示して終了")
    parser.add_argument("--dry-run", action="store_true", help="API呼び出しせず組み合わせのみ表示")
    args = parser.parse_args()

    if args.list_axes:
        list_axes()
        return

    combos = pick_combinations(args.count, args.axis)
    existing_titles = load_existing_titles()

    if args.dry_run:
        print(json.dumps(combos, ensure_ascii=False, indent=2))
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("環境変数 ANTHROPIC_API_KEY が設定されていません。")

    client = anthropic.Anthropic(api_key=api_key)
    consultation_context = load_consultation_context()

    generated = []
    for i, combo in enumerate(combos, 1):
        print(f"[{i}/{len(combos)}] 生成中: {combo['category']} / {combo['attribute']} / {combo['structure']}")
        idea = generate_idea(client, combo, consultation_context, args.format)
        title = idea.get("title", "")
        if title in existing_titles:
            print(f"  → 重複タイトルのためスキップ: {title}")
            continue
        generated.append(idea)
        existing_titles.add(title)
        print(f"  → {title or '[パース失敗]'}")

    save_ideas(generated)
    print(f"\n完了: {len(generated)}件を {IDEAS_DB_PATH} に保存しました。")
    print(f"次のステップ: /zu-writer でDBから図解ネタを選んでプロンプト生成してください。")


if __name__ == "__main__":
    main()
