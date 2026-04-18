"""
reorder_queue.py — post-queue.md のカテゴリを分散して並び替える
設計比率: A(感情・共感)30% / C(保育園・両立)25% / B(専門知識)25% / D/E(グッズ・節約)20%
note誘導は4〜5投稿に1回の割合で挟む
"""
import re
import sys
import io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

QUEUE_FILE = Path(__file__).parent / "post-queue.md"


def classify(category: str) -> str:
    c = category.lower()
    if "note誘導" in category:
        return "note"
    if any(k in category for k in ["専門知識", "グッズ・専門知識"]):
        return "B"
    if any(k in category for k in ["グッズ", "節約"]):
        return "DE"
    if any(k in category for k in ["ワーママ", "入園準備", "入園後", "入園", "ワンオペ"]):
        return "AC"  # A/C混合扱い（共感系だが保育園に絡む）
    if any(k in category for k in ["共感", "体験談", "問いかけ", "生活系"]):
        return "A"
    return "A"


def parse_posts(text: str):
    """## 投稿NNN ブロックをリストで返す"""
    header = []
    blocks = []
    lines = text.splitlines(keepends=True)
    current = []
    in_block = False

    for line in lines:
        if re.match(r'^## 投稿\d+', line):
            if current and in_block:
                blocks.append("".join(current))
            current = [line]
            in_block = True
        elif not in_block:
            header.append(line)
        else:
            current.append(line)
    if current and in_block:
        blocks.append("".join(current))

    return "".join(header), blocks


def get_category(block: str) -> str:
    m = re.search(r'\*\*カテゴリ\*\*：(.+)', block)
    return m.group(1).strip() if m else "不明"


def interleave(buckets: dict) -> list:
    """
    1日5投稿パターン (繰り返し):
    A → AC → B → DE → A → note → AC → B → DE → AC → ...
    """
    # note以外のバケツを使ったパターン
    # 1サイクル10投稿: A×3, AC×3, B×2, DE×1, note×1
    pattern = ["A", "AC", "B", "A", "DE", "AC", "B", "note", "A", "AC"]
    result = []
    idx = {k: 0 for k in buckets}
    total = sum(len(v) for v in buckets.values())

    cycle_pos = 0
    while sum(len(buckets[k]) - idx[k] for k in buckets) > 0:
        # 未消化の実数
        remaining = {k: len(buckets[k]) - idx[k] for k in buckets}
        if all(v == 0 for v in remaining.values()):
            break

        bucket_key = pattern[cycle_pos % len(pattern)]
        cycle_pos += 1

        # そのバケツが空なら別のバケツを探す
        order = [bucket_key] + [k for k in ["A", "AC", "B", "DE", "note"] if k != bucket_key]
        placed = False
        for key in order:
            if remaining[key] > 0:
                result.append(buckets[key][idx[key]])
                idx[key] += 1
                placed = True
                break
        if not placed:
            break

    return result


def main():
    text = QUEUE_FILE.read_text(encoding="utf-8")
    header, blocks = parse_posts(text)

    # カテゴリ分類
    buckets = {"A": [], "AC": [], "B": [], "DE": [], "note": []}
    for block in blocks:
        cat = get_category(block)
        bucket = classify(cat)
        buckets[bucket].append(block)

    print("【分類結果】")
    for k, v in buckets.items():
        print(f"  {k}: {len(v)}件")

    reordered = interleave(buckets)
    print(f"\n並び替え後: {len(reordered)}件")

    # 書き直し
    new_content = header.rstrip() + "\n\n---\n\n"
    for block in reordered:
        b = block.strip()
        if not b.endswith("---"):
            b += "\n\n---"
        new_content += b + "\n\n"

    QUEUE_FILE.write_text(new_content, encoding="utf-8")
    print("post-queue.md を更新しました")

    # 並び順の確認
    print("\n【並び替え後の先頭20件】")
    for i, block in enumerate(reordered[:20]):
        cat = get_category(block)
        m = re.search(r'^## (投稿\d+)', block)
        num = m.group(1) if m else f"投稿{i+1}"
        theme_m = re.search(r'\*\*テーマ\*\*：(.+)', block)
        theme = theme_m.group(1)[:20] if theme_m else ""
        print(f"  {i+1:2d}. {num} [{classify(cat):4s}] {cat} — {theme}")


if __name__ == "__main__":
    main()
