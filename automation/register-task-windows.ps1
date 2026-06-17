#requires -Version 5.1
<#
  Registers a daily Windows Scheduled Task that runs the local digest automation.
  Default: every day at 7:00 AM. Re-runnable (re-registers with -Force).
#>
$ErrorActionPreference = 'Stop'
$root     = Split-Path -Parent $PSScriptRoot
$script   = Join-Path $root 'automation\daily_digest.py'
$taskName = 'AI-Server Daily Digest'

# Resolve python (prefer pythonw for no console window).
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found on PATH. Install Python 3 and retry." }

$action   = New-ScheduledTaskAction -Execute $py -Argument "`"$script`"" -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description 'Summarizes recent BuildLog + decision-log activity via the local LLM.'

Write-Host "Registered scheduled task: '$taskName' (daily 7:00 AM)."
Write-Host "Test it now:  Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Output goes to:  $root\out\"
