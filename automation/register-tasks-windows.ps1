#requires -Version 5.1
<#
  Registers the AI-Server automation jobs as Windows Scheduled Tasks (supersedes the
  old single-task registration script). Re-runnable (-Force re-registers).

    daily-digest     every day      07:00
    weekly-rollup    Mondays        07:15
    decision-drift   Saturdays      07:30   (needs the RAG index; see note below)

  Each task runs `python -m automation <job>` from the repo root, so it picks up the
  aiserver/rag/automation packages without an install. Outputs go to <root>\out\.

  NOTE: decision-drift reads the RAG index. Schedule `python -m rag.ingest` (e.g. a task a
  few minutes before 07:30 Sat) or run it manually so the index is fresh before drift runs.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# Prefer pythonw (no console window); fall back to python.
$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python not found on PATH. Install Python 3 and retry." }

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

function Register-Job {
    param(
        [string]$Job,
        [string]$TaskName,
        [string]$Description,
        $Trigger
    )
    $action = New-ScheduledTaskAction -Execute $py -Argument "-m automation $Job" -WorkingDirectory $root
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $Trigger `
        -Settings $settings -Force -Description $Description | Out-Null
    Write-Host "Registered: '$TaskName'  ($Job)"
}

Register-Job -Job 'daily-digest'   -TaskName 'AI-Server Daily Digest' `
    -Description 'Summarizes recent BuildLog + decision-log activity via the local LLM.' `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 7:00AM)

Register-Job -Job 'weekly-rollup'  -TaskName 'AI-Server Weekly Rollup' `
    -Description 'Monday status note over the week''s BuildLog + decision-log.' `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7:15AM)

Register-Job -Job 'decision-drift' -TaskName 'AI-Server Decision Drift' `
    -Description 'Flags decisions with no strong match in the canonical docs (RAG).' `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 7:30AM)

Write-Host ""
Write-Host "All three jobs registered. Test one now, e.g.:"
Write-Host "  Start-ScheduledTask -TaskName 'AI-Server Daily Digest'"
Write-Host "Outputs go to:  $root\out\"
