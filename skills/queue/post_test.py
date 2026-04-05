import urllib.request
import urllib.parse
import json

ACCESS_TOKEN = "THAAX6Vv488utBUVJxVDBwU3drMElFVXNfSHpyRUJ1VTlpSF9NcjA4OG9kQTh6by1tRWNFYy1jUkV0Vm81Wmp0YkpzVkEtX1JkanVVMnNBVnhhdFNKMnA4ck15cVVBNVVzNFg1NzVuQWxTX3lRXzVya0otd01mZAU9lWlJSWlhzOEgtZAXBjanc2MVdfM3ZALVEkZD"
USER_ID = "34618526867762918"

TEXT = "テスト投稿です🌸"

base = "https://graph.threads.net/v1.0"

params1 = urllib.parse.urlencode({
    "media_type": "TEXT",
    "text": TEXT,
    "access_token": ACCESS_TOKEN
}).encode()
req1 = urllib.request.Request(f"{base}/{USER_ID}/threads", data=params1, method="POST")
with urllib.request.urlopen(req1) as res:
    container_id = json.loads(res.read())["id"]
print("コンテナ作成:", container_id)

params2 = urllib.parse.urlencode({
    "creation_id": container_id,
    "access_token": ACCESS_TOKEN
}).encode()
req2 = urllib.request.Request(f"{base}/{USER_ID}/threads_publish", data=params2, method="POST")
with urllib.request.urlopen(req2) as res:
    post_id = json.loads(res.read())["id"]
print("投稿完了:", post_id)