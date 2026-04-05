import urllib.request
import json

ACCESS_TOKEN = "THAAX6Vv488utBUVJxVDBwU3drMEIFVXNfSHpyRUJ1VTIpSF9NcjA4OG9kQTh6by1tRWNFYy1jUkV0Vm81Wmp0YkpzVkEtX1JkanVVMnNBVnhhdFNKMnA4ck15cVVBNVVzt"

url = f"https://graph.threads.net/v1.0/me?fields=id,username&access_token={ACCESS_TOKEN}"

req = urllib.request.Request(url)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode())
    print("ユーザーID:", data['id'])
    print("username:", data.get("username", "N/A"))