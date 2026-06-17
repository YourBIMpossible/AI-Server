#requires -Version 5.1
<#
  AI-Server setup for the current Windows rig (RTX 5080).
  Installs Ollama, pulls the models in config/models.txt, runs a smoke test.
  Re-runnable: skips install if Ollama is already present.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Write-Host "AI-Server root: $root"

# --- 1. Ensure Ollama is installed ---
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Ollama not found. Attempting install via winget..."
    try {
        winget install --id Ollama.Ollama -e --source winget `
            --accept-source-agreements --accept-package-agreements
    } catch {
        Write-Warning "winget install failed. Download and run the installer manually:"
        Write-Warning "  https://ollama.com/download"
        Read-Host "Press Enter once Ollama is installed to continue"
    }
    # refresh PATH for this session
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path','User')
} else {
    Write-Host "Ollama already installed: $($ollama.Source)"
}

# --- 2. Make sure the Ollama service is up ---
Write-Host "Waiting for Ollama service..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 2 | Out-Null
        $ok = $true; break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) {
    Write-Host "Starting 'ollama serve' in the background..."
    Start-Process -WindowStyle Hidden -FilePath "ollama" -ArgumentList "serve"
    Start-Sleep -Seconds 3
}

# --- 3. Pull models from config/models.txt ---
$modelsFile = Join-Path $root 'config\models.txt'
$models = Get-Content $modelsFile |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith('#') }
foreach ($m in $models) {
    Write-Host "Pulling $m ..."
    ollama pull $m
}

# --- 4. Smoke test ---
Write-Host "Running smoke test..."
python (Join-Path $root 'scripts\smoke-test.py')
Write-Host "Done. Endpoint live at http://localhost:11434/v1"
