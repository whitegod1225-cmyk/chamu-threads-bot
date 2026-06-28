# chamu-push: content-toolの変更をGitHubに反映するワンコマンド
# 使い方: cd content-tool && .\push.ps1

$files = @(
    "skills/queue/post-queue.md",
    "skills/queue/post-history.md",
    "skills/queue/next-topics.md",
    "skills/queue/affiliate-topics.md",
    "skills/knowledge"
)

git add $files

$diff = git diff --cached --stat
if (-not $diff) {
    Write-Host "変更なし。pushをスキップします。" -ForegroundColor Yellow
    exit 0
}

Write-Host $diff -ForegroundColor Cyan

$date = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "chore: update content $date"

git pull --rebase origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ pull --rebase 失敗。conflict を確認してください。" -ForegroundColor Red
    exit 1
}

git push origin main
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ push完了" -ForegroundColor Green
} else {
    Write-Host "❌ push失敗" -ForegroundColor Red
    exit 1
}
