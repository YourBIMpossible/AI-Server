<#
.SYNOPSIS
  Open MyBuddy from Windows (plan step 5): start or reuse the SSH tunnel, then open the UI.
.DESCRIPTION
  Uses the `mybuddy` host from ~/.ssh/config (key login, no password, no address here).
  Forwards the three box UIs to 127.0.0.1:13000 / 13001 / 13080. If the ports already
  answer, the running tunnel is reused. On failure it shows one message box:
  "MyBuddy is offline or unavailable". Launched hidden by mybuddy-open.vbs.
.PARAMETER Ui
  Which UI to open: all (default, for the trial week), openwebui, anythingllm, librechat.
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'openwebui', 'anythingllm', 'librechat')]
    [string]$Ui = 'all',
    [string]$SshHost = 'mybuddy'
)
$ErrorActionPreference = 'Stop'

$Forwards = [ordered]@{
    openwebui   = @{ Local = 13000; Remote = 3000 }
    anythingllm = @{ Local = 13001; Remote = 3001 }
    librechat   = @{ Local = 13080; Remote = 3080 }
}

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync('127.0.0.1', $Port).Wait(300) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Show-Offline {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
        'MyBuddy is offline or unavailable.', 'MyBuddy', 'OK', 'Warning')
}

function Test-TunnelUp {
    foreach ($f in $Forwards.Values) { if (-not (Test-LocalPort $f.Local)) { return $false } }
    return $true
}

try {
    if (-not (Test-TunnelUp)) {
        $sshArgs = @('-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                  '-o', 'ConnectTimeout=6', '-o', 'ServerAliveInterval=30',
                  '-o', 'ServerAliveCountMax=3')
        foreach ($f in $Forwards.Values) {
            $sshArgs += @('-L', "127.0.0.1:$($f.Local):127.0.0.1:$($f.Remote)")
        }
        $sshArgs += $SshHost
        $ssh = Start-Process -FilePath 'ssh.exe' -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
        $deadline = (Get-Date).AddSeconds(12)
        while (-not (Test-TunnelUp)) {
            if ($ssh.HasExited -or (Get-Date) -gt $deadline) {
                if (-not $ssh.HasExited) { Stop-Process -Id $ssh.Id -Force }
                Show-Offline
                exit 1
            }
            Start-Sleep -Milliseconds 300
        }
    }
    $targets = if ($Ui -eq 'all') { $Forwards.Keys } else { @($Ui) }
    foreach ($t in $targets) { Start-Process "http://127.0.0.1:$($Forwards[$t].Local)/" }
    exit 0
} catch {
    Show-Offline
    exit 1
}
