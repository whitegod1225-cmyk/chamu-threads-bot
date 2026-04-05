import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

def main():
    # Read research.txt
    try:
        with open("research.txt", "r", encoding="utf-8") as f:
            research = f.read().strip()
    except FileNotFoundError:
        print("エラー: research.txt が見つかりません。")
        return

    if not research:
        print("エラー: research.txt が空です。内容を追加してから再実行してください。")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: .env ファイルに ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""以下のリサーチ内容をもとに、Threadsの投稿文を5案作成してください。

条件:
- 各投稿文は140文字以内（日本語・英語どちらでも可）
- 絵文字を適切に使用する
- 親しみやすく、読みやすいトーン
- 各案は番号付きで出力（例: 1. 〜）
- 投稿文のみを出力し、説明や注釈は不要

リサーチ内容:
{research}"""

    print("Threads 投稿文を生成中...")

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    result_text = response.content[0].text.strip()

    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(result_text)

    print("✅ 生成完了！output.txt に保存しました。\n")
    print(result_text)

if __name__ == "__main__":
    main()
