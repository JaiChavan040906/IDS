# Used by start_portal_public.bat: waits for the local portal, opens a Cloudflare quick tunnel,
# and shows the public https://....trycloudflare.com link. Exit code 1 if something fails.
param([int]$Port = 8001, [string]$Log = "data\tunnel.log")

$ProgressPreference = "SilentlyContinue"

# 1) wait for the portal (up to ~2 minutes: the AI model takes a moment to load)
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 | Out-Null
        $ok = $true; break
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) { Write-Host "The portal did not start. Look at the 'Sentinel portal' window for the error."; exit 1 }

# 2) start the tunnel (keeps running in the background until stopped)
if (Test-Path $Log) { Remove-Item $Log -Force }
Start-Process -FilePath "tools\cloudflared.exe" -WindowStyle Hidden `
    -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port", "--logfile", $Log)

# 3) wait for the public link to appear in the tunnel log
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $Log) {
        $m = Select-String -Path $Log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}
if (-not $url) { Write-Host "Could not get a public link. Check the internet connection and try again."; exit 1 }

try { Set-Clipboard -Value $url } catch {}
Write-Host ""
Write-Host "============================================================"
Write-Host ("  PUBLIC LINK:  " + $url) -ForegroundColor Green
Write-Host "  (copied to the clipboard - paste it anywhere to share)"
Write-Host "============================================================"
Write-Host "  Sign in as admin or analyst with the passwords you just chose."
Write-Host "  The link can take up to a minute to start working."
Start-Process $url
exit 0
