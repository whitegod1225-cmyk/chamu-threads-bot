#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
図解画像をリポジトリに追加してキューエントリを生成するヘルパー。

使い方:
    python tools/add-image-post.py <画像ファイルパス> <キャプション> [投稿番号]

例:
    python tools/add-image-post.py ~/Downloads/drive_goods_1.jpg "帰省のロングドライブ、去年いちばん後悔したのはこれを知らなかったこと。" 435
"""

import sys
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

REPO_ROOT     = Path(__file__).resolve().parent.parent
IMAGES_DIR    = REPO_ROOT / "images"
QUEUE_FILE    = REPO_ROOT / "skills" / "queue" / "post-queue.md"
GITHUB_REPO   = "whitegod1225-cmyk/chamu-threads-bot"
GITHUB_BRANCH = "main"

# ── ユーティリティ ─────────────────────────────────────

def raw_url(filename: str) -> str:
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/images/{filename}"


def next_post_number() -> int:
    text = QUEUE_FILE.read_text(encoding="utf-8")
    nums = [int(n) for n in re.findall(r"## 投稿(\d+)", text)]
    # post-history からも最大値を取る
    history = REPO_ROOT / "skills" / "queue" / "post-history.md"
    if history.exists():
        nums += [int(n) for n in re.findall(r"## 投稿(\d+)", history.read_text(encoding="utf-8"))]
    return max(nums, default=400) + 1


def build_queue_entry(post_num: int, caption: str, image_url: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""## 投稿{post_num}
**テーマ**：「図解投稿（{today}）」
**カテゴリ**：専門知識（B）／図解投稿
**時期**：通年
**図解タイプ**：タイル型

**本文**
{caption}

**画像URL**
{image_url}

**コメント欄（セルフリプライ用）**
なし"""


def append_to_queue(entry: str):
    text = QUEUE_FILE.read_text(encoding="utf-8")
    # ファイル末尾に追記（末尾が \n で終わっていない場合も考慮）
    sep = "\n\n---\n\n" if text.rstrip().endswith("---") is False else "\n\n"
    new_text = text.rstrip() + "\n\n---\n\n" + entry + "\n"
    QUEUE_FILE.write_text(new_text, encoding="utf-8")


def git_commit_push(image_path: Path, post_num: int):
    cmds = [
        ["git", "add", f"images/{image_path.name}", "skills/queue/post-queue.md"],
        ["git", "commit", "-m", f"feat: 投稿{post_num}（図解画像）を追加"],
        ["git", "pull", "--rebase", "origin", "main"],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if result.returncode != 0 and cmd[1] != "pull":
            print(f"[WARN] {' '.join(cmd)} 失敗:\n{result.stderr}")
            return False
    return True


# ── メイン ───────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    src_path = Path(sys.argv[1]).expanduser().resolve()
    caption  = sys.argv[2]
    post_num = int(sys.argv[3]) if len(sys.argv) >= 4 else next_post_number()

    if not src_path.exists():
        print(f"[ERROR] ファイルが見つかりません: {src_path}")
        sys.exit(1)

    # 拡張子チェック
    if src_path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        print(f"[ERROR] 対応していない形式です: {src_path.suffix}")
        sys.exit(1)

    # images/ にコピー（ファイル名: post_NNN_元ファイル名）
    dest_name = f"post_{post_num}_{src_path.name}"
    dest_path = IMAGES_DIR / dest_name
    shutil.copy2(src_path, dest_path)
    print(f"[OK] 画像をコピー: {dest_path.name}")

    # GitHub raw URL 生成
    img_url = raw_url(dest_name)
    print(f"[OK] 画像URL: {img_url}")

    # キューエントリ生成・追記
    entry = build_queue_entry(post_num, caption, img_url)
    append_to_queue(entry)
    print(f"[OK] 投稿{post_num} をキューに追加")

    # git commit & push
    print("[...] git commit & push 中...")
    if git_commit_push(dest_path, post_num):
        print(f"[完了] 投稿{post_num} がキューに入りました。次のActionsで自動投稿されます。")
    else:
        print("[注意] pushに失敗しました。手動で git push してください。")

    print(f"\n--- キューエントリ ---\n{entry}\n")


if __name__ == "__main__":
    main()
