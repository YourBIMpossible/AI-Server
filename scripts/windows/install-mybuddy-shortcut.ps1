<#
.SYNOPSIS
  Install the MyBuddy launcher to %LOCALAPPDATA%\MyBuddy and put a "MyBuddy" shortcut on
  the desktop. Re-run after pulling changes to update the installed copy.
#>
[CmdletBinding()]
param([string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'MyBuddy'))
$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
foreach ($f in 'mybuddy-open.ps1', 'mybuddy-open.vbs') {
    Copy-Item -Force (Join-Path $PSScriptRoot $f) (Join-Path $InstallDir $f)
}
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MyBuddy.lnk'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$s.Arguments = '"' + (Join-Path $InstallDir 'mybuddy-open.vbs') + '"'
$s.WorkingDirectory = $InstallDir
$s.IconLocation = (Join-Path $env:WINDIR 'System32\shell32.dll') + ',13'
$s.Description = 'Open MyBuddy (SSH tunnel to the box, then the browser)'
$s.Save()
Write-Output "Installed to $InstallDir; shortcut: $lnk"
