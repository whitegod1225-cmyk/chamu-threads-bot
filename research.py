import os
import sys
import pyperclip
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

load_dotenv(dotenv_path=".env", encoding="utf-8")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
MAX_VIDEOS = 10
TRANSCRIPT_PREVIEW_CHARS = 500
OUTPUT_FILE = "result.txt"
PROMPT_FILE = "prompt.txt"


def search_videos(keyword: str) -> list[str]:
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    try:
        response = youtube.search().list(
            q=keyword,
            part="id",
            type="video",
            maxResults=MAX_VIDEOS,
            order="viewCount",
            relevanceLanguage="ja",
        ).execute()
    except HttpError as e:
        print(f"[エラー] YouTube Search API: {e}")
        sys.exit(1)

    return [item["id"]["videoId"] for item in response.get("items", [])]


def get_video_details(video_ids: list[str]) -> list[dict]:
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    try:
        response = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids),
        ).execute()
    except HttpError as e:
        print(f"[エラー] YouTube Videos API: {e}")
        sys.exit(1)

    videos = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        videos.append({
            "id": item["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "url": f"https://youtu.be/{item['id']}",
        })

    videos.sort(key=lambda x: x["view_count"], reverse=True)
    return videos


def get_transcript(video_id: str) -> str | None:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(["ja"])
        except Exception:
            try:
                transcript = transcript_list.find_transcript(["en"])
            except Exception:
                transcript = transcript_list.find_generated_transcript(["ja", "en"])

        segments = transcript.fetch()
        text = " ".join(seg["text"] for seg in segments)
        return text[:TRANSCRIPT_PREVIEW_CHARS]

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    except Exception:
        return None


def format_number(n: int) -> str:
    return f"{n:,}"


def main():
    if not YOUTUBE_API_KEY:
        print("[エラー] .env に YOUTUBE_API_KEY が設定されていません。")
        sys.exit(1)

    keyword = input("検索キーワードを入力してください（例: 育児 保育士）: ").strip()
    if not keyword:
        print("[エラー] キーワードが空です。")
        sys.exit(1)

    print(f"\n🔍 「{keyword}」で YouTube を検索中...")
    video_ids = search_videos(keyword)

    if not video_ids:
        print("[エラー] 動画が見つかりませんでした。")
        sys.exit(1)

    print(f"   {len(video_ids)} 件取得。詳細情報を取得中...")
    videos = get_video_details(video_ids)

    print("\n📝 字幕を取得中...")
    for v in videos:
        transcript = get_transcript(v["id"])
        if transcript:
            v["transcript"] = transcript
            print(f"   ✅ 字幕あり: {v['title'][:45]}...")
        else:
            v["transcript"] = None
            print(f"   ⏭️  字幕なし: {v['title'][:45]}...")

    # result.txt に保存
    lines = [
        f"検索キーワード：{keyword}",
        f"取得動画数：{len(videos)} 件",
        "=" * 50,
        "",
    ]

    for i, v in enumerate(videos, 1):
        transcript_text = v["transcript"] if v["transcript"] else "（字幕なし）"
        lines += [
            f"=== 動画{i} ===",
            f"タイトル：{v['title']}",
            f"URL：{v['url']}",
            f"再生数：{format_number(v['view_count'])}",
            f"いいね数：{format_number(v['like_count'])}",
            f"字幕（最初の{TRANSCRIPT_PREVIEW_CHARS}文字）：",
            transcript_text,
            "",
        ]

    output = "\n".join(lines)

    with open(OUTPUT_FILE, "w", encoding="utf-8", errors="replace") as f:
        f.write(output)

    print(f"\n✅ {len(videos)} 件の結果を {OUTPUT_FILE} に保存しました。")

    # prompt.txt を生成
    prompt_content = f"""以下のYouTubeデータを分析して、
元保育士・児童指導員の30代・3人の母が運営する
育児系Threadsアカウント用の投稿文を10本作って。

【ペルソナ】
- 元保育士・児童指導員、30代、3人の母
- 明るく前向き、フランクな口調（敬語NG）
- ターゲット：20〜30代の育児中のママ

【投稿の種類を混ぜて】
- 共感・拡散系 3本
- 専門知識・保存系 3本
- アフィリエイト導線 2本
- note誘導 2本

【フックを強く】
- 1行目で「私のことだ！」と思わせる
- 数字・逆説・本音告白を使う

【YouTubeデータ】
{output}
"""

    with open(PROMPT_FILE, "w", encoding="utf-8", errors="replace") as f:
        f.write(prompt_content)

    # クリップボードにコピー
    try:
        pyperclip.copy(prompt_content)
        clipboard_ok = True
    except Exception:
        clipboard_ok = False

    print(f"📄 {PROMPT_FILE} を生成しました。")
    if clipboard_ok:
        print("📋 クリップボードにコピーしました。")
    else:
        print("⚠️  クリップボードへのコピーに失敗しました。prompt.txt を手動でコピーしてください。")
    print("\nClaude に貼り付けてください。")


if __name__ == "__main__":
    main()
