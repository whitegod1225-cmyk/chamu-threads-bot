import os
import sys
import anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

load_dotenv()

# ── 設定 ────────────────────────────────────────────────────────────────────
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MAX_VIDEOS = 10
MAX_TRANSCRIPT_CHARS = 1500  # 1動画あたりの字幕上限（トークン節約）
OUTPUT_FILE = "result.txt"


# ── YouTube 検索 ─────────────────────────────────────────────────────────────
def search_videos(keyword: str, max_results: int = MAX_VIDEOS) -> list[dict]:
    """キーワードで動画を検索して動画IDリストを返す"""
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    try:
        response = youtube.search().list(
            q=keyword,
            part="id,snippet",
            type="video",
            maxResults=max_results,
            order="viewCount",
            relevanceLanguage="ja",
        ).execute()
    except HttpError as e:
        print(f"[エラー] YouTube Search API: {e}")
        sys.exit(1)

    video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
    return video_ids


def get_video_details(video_ids: list[str]) -> list[dict]:
    """動画IDリストからタイトル・説明文・再生数・いいね数を取得"""
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
            "description": snippet.get("description", "")[:300],  # 先頭300文字
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        })

    # 再生数降順にソート
    videos.sort(key=lambda x: x["view_count"], reverse=True)
    return videos


# ── 字幕取得 ─────────────────────────────────────────────────────────────────
def get_transcript(video_id: str) -> str | None:
    """字幕テキストを取得。取得できない場合は None を返す"""
    try:
        # 日本語→英語の順で試みる
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
        return text[:MAX_TRANSCRIPT_CHARS]

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
    except Exception:
        return None


# ── Claude 分析 ──────────────────────────────────────────────────────────────
def analyze_with_claude(keyword: str, videos: list[dict]) -> str:
    """動画情報をまとめて Claude に渡し、分析結果を返す"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # プロンプト用データ整形
    video_summaries = []
    for i, v in enumerate(videos, 1):
        transcript_text = v.get("transcript") or "（字幕なし）"
        summary = (
            f"【動画{i}】\n"
            f"タイトル: {v['title']}\n"
            f"再生数: {v['view_count']:,} / いいね数: {v['like_count']:,}\n"
            f"説明文: {v['description']}\n"
            f"字幕抜粋: {transcript_text}\n"
        )
        video_summaries.append(summary)

    videos_text = "\n---\n".join(video_summaries)

    prompt = f"""あなたはSNSコンテンツ戦略の専門家です。
以下は「{keyword}」で検索した育児系YouTubeの人気動画データです。

{videos_text}

上記のデータをもとに、以下の3点を日本語で分析・提案してください。

## 1. 人気コンテンツの共通パターン（箇条書き5点）
視聴者に響いているテーマ・切り口・表現のパターンを分析してください。

## 2. Threadsに転用できる投稿ネタ10案
各ネタは以下の形式で出力：
- ネタタイトル（20字以内）
- 投稿内容案（140字以内・絵文字あり・親しみやすいトーン）

## 3. フック文アイデア3個
Threadsで「続きを読む」をタップさせるための冒頭フレーズ。
ターゲット：育児中の保護者（0〜6歳の子どもを持つ親）
"""

    print("\nClaude に分析を依頼中...")
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        result = stream.get_final_message()

    return result.content[0].text


# ── メイン ───────────────────────────────────────────────────────────────────
def main():
    # API キー確認
    if not YOUTUBE_API_KEY:
        print("[エラー] .env に YOUTUBE_API_KEY が設定されていません。")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("[エラー] .env に ANTHROPIC_API_KEY が設定されていません。")
        sys.exit(1)

    # キーワード入力
    if len(sys.argv) > 1:
        keyword = " ".join(sys.argv[1:])
    else:
        keyword = input("検索キーワードを入力してください（例: 育児 保育士）: ").strip()
        if not keyword:
            print("[エラー] キーワードが空です。")
            sys.exit(1)

    print(f"\n🔍 「{keyword}」で YouTube を検索中...")

    # 動画検索
    video_ids = search_videos(keyword)
    if not video_ids:
        print("[エラー] 動画が見つかりませんでした。")
        sys.exit(1)

    print(f"   {len(video_ids)} 件の動画を取得しました。詳細情報を取得中...")

    # 動画詳細取得
    videos = get_video_details(video_ids)

    # 字幕取得
    print("\n📝 字幕を取得中...")
    for v in videos:
        transcript = get_transcript(v["id"])
        if transcript:
            v["transcript"] = transcript
            print(f"   ✅ 字幕あり: {v['title'][:40]}...")
        else:
            v["transcript"] = None
            print(f"   ⏭️  字幕なし（スキップ）: {v['title'][:40]}...")

    # 字幕ありの動画が0件でも分析は続行
    transcript_count = sum(1 for v in videos if v["transcript"])
    print(f"\n   字幕取得成功: {transcript_count}/{len(videos)} 件")

    # Claude 分析
    analysis = analyze_with_claude(keyword, videos)

    # 出力
    output = (
        f"# YouTube → Threads ネタ分析レポート\n"
        f"検索キーワード: {keyword}\n"
        f"対象動画数: {len(videos)} 件（字幕あり: {transcript_count} 件）\n"
        f"{'=' * 60}\n\n"
        f"{analysis}\n\n"
        f"{'=' * 60}\n"
        f"## 取得した動画一覧\n"
    )
    for i, v in enumerate(videos, 1):
        output += (
            f"{i}. {v['title']}\n"
            f"   再生数: {v['view_count']:,} / いいね数: {v['like_count']:,}\n"
            f"   https://youtu.be/{v['id']}\n"
        )

    print("\n" + "=" * 60)
    print(analysis)
    print("=" * 60)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n✅ 結果を {OUTPUT_FILE} に保存しました。")


if __name__ == "__main__":
    main()
