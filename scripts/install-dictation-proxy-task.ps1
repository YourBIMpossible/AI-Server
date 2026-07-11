# Makes the OpenWhispr dictation-cleanup proxy permanent: registers a Scheduled Task
# that starts it at logon and restarts it if it crashes. Normal privilege (binds
# 127.0.0.1 only, no elevation needed). Re-run any time to update.
#
# See aiserver/dictation_proxy.py for what this does and why it exists.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

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

$state = (Get-ScheduledTask -TaskName "OpenWhispr Dictation Proxy").State
Write-Host ""
Write-Host "Done. Starts automatically at every logon: $state" -ForegroundColor Green
Write-Host "Listening at http://127.0.0.1:11435 -> forwards to Ollama at OLLAMA_HOST" -ForegroundColor Cyan
Write-Host ""
Write-Host "In OpenWhispr, set the Self-Hosted endpoint URL for Dictation Cleanup" -ForegroundColor Yellow
Write-Host "(and Note Formatting, if you use it) to:  http://localhost:11435/v1"
Write-Host "Do NOT point Voice Agent or Chat at this proxy -- its fallback would" -ForegroundColor Yellow
Write-Host "incorrectly discard legitimate agent answers."
Read-Host "`nPress Enter to close"
