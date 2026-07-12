# Makes the OpenWhispr dictation-cleanup proxy permanent: registers a Scheduled Task
# that starts it at logon and restarts it if it crashes. Normal privilege (binds
# 127.0.0.1 only, no elevation needed). Re-run any time to update.
#
# See aiserver/dictation_proxy.py for what this does and why it exists.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

# Must match aiserver/config.py's DICTATION_PROXY_HOST/PORT defaults. If your .env
# overrides them, update these two lines to match (this script doesn't parse .env).
$proxyHost = "127.0.0.1"
$proxyPort = 11435

# --- locate pythonw (no console window) ---
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "python not found on PATH." }
$pyw = $py -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }

Write-Host "Python : $pyw"
Write-Host "Folder : $repoRoot"

$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)

$action = New-ScheduledTaskAction -Execute $pyw -Argument "-m aiserver.dictation_proxy" -WorkingDirectory $repoRoot
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "OpenWhispr Dictation Proxy" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Reliability proxy between OpenWhispr's Self-Hosted LLM config and Ollama: forces temperature=0 and falls back to raw text if the model answers instead of cleaning up." `
    -Force | Out-Null

Start-ScheduledTask -TaskName "OpenWhispr Dictation Proxy"
Start-Sleep -Seconds 2

# Task state only proves the process launched, not that it bound the port -- a
# missing dependency or import error under pythonw fails silently with no console.
# Probe the port itself so a bad install is never reported as a success.
function Test-ProxyPortOpen {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($proxyHost, $proxyPort, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(3000, $false) -and $client.Connected
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

$state = (Get-ScheduledTask -TaskName "OpenWhispr Dictation Proxy").State
$listening = Test-ProxyPortOpen
Write-Host ""
if ($listening) {
    Write-Host "Done. Starts automatically at every logon: $state" -ForegroundColor Green
    Write-Host "Listening at http://${proxyHost}:${proxyPort} -> forwards to Ollama at OLLAMA_HOST" -ForegroundColor Cyan
    Write-Host "(override the listen address via DICTATION_PROXY_HOST / DICTATION_PROXY_PORT in .env)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "In OpenWhispr, set the Self-Hosted endpoint URL for Dictation Cleanup" -ForegroundColor Yellow
    Write-Host "(and Note Formatting, if you use it) to:  http://${proxyHost}:${proxyPort}/v1"
    Write-Host "Do NOT point Voice Agent or Chat at this proxy -- its fallback would" -ForegroundColor Yellow
    Write-Host "incorrectly discard legitimate agent answers."
} else {
    Write-Host "WARNING: task state is '$state' but nothing is listening on ${proxyHost}:${proxyPort}." -ForegroundColor Red
    Write-Host "It may still be starting, or it failed silently under pythonw. Check:" -ForegroundColor Red
    Write-Host "  Get-ScheduledTaskInfo -TaskName 'OpenWhispr Dictation Proxy'" -ForegroundColor Red
    Write-Host "  python -m aiserver.dictation_proxy   (run directly, in a console, to see the error)" -ForegroundColor Red
}
Read-Host "`nPress Enter to close"
