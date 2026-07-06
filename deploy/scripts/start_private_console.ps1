param(
    [string]$Token = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 7860,
    [string]$OllamaModelsDir = "D:\JZDSLx\llm_models",
    [string]$Model = "jaahas/qwen3.5-uncensored:35b",
    [int]$NumCtx = 1024,
    [int]$MaxTokens = 384,
    [int]$MaxHistory = 8,
    [switch]$Remote,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Test-OllamaReady {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Wait-OllamaReady {
    param([int]$TimeoutSeconds = 30)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaReady) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-OllamaModelAvailable {
    param([string]$ModelName)

    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        foreach ($item in $tags.models) {
            if ($item.name -eq $ModelName) {
                return $true
            }
        }
    }
    catch {
        return $false
    }
    return $false
}

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-PythonCommand {
    param([string]$ProjectRoot)

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    return "python"
}

function Get-DisplayHost {
    param([string]$BindHost)

    if ($BindHost -eq "0.0.0.0") {
        return "127.0.0.1"
    }
    return $BindHost
}

$projectRoot = Get-ProjectRoot
Set-Location $projectRoot

if ($Remote) {
    $HostAddress = "0.0.0.0"
    $env:MAIBOT_LOCAL_CONSOLE_ALLOW_REMOTE = "1"
}

if (-not $Token) {
    if ($env:MAIBOT_LOCAL_CONSOLE_TOKEN) {
        $Token = $env:MAIBOT_LOCAL_CONSOLE_TOKEN
    }
    else {
        $Token = [Guid]::NewGuid().ToString("N")
    }
}

$env:OLLAMA_MODELS = $OllamaModelsDir
$env:MAIBOT_LOCAL_MODEL_BASE_URL = "http://127.0.0.1:11434"
$env:MAIBOT_LOCAL_MODEL_NAME = $Model
$env:MAIBOT_LOCAL_MODEL_NUM_CTX = [string]$NumCtx
$env:MAIBOT_LOCAL_MODEL_MAX_TOKENS = [string]$MaxTokens
$env:MAIBOT_LOCAL_CONSOLE_MAX_HISTORY = [string]$MaxHistory
$env:MAIBOT_LOCAL_MODEL_DISABLE_THINKING = "1"
$env:MAIBOT_LOCAL_MODEL_ENABLED = "1"

Write-Host "MaiBot private console launcher"
Write-Host "Project root: $projectRoot"
Write-Host "Ollama models dir: $OllamaModelsDir"
Write-Host "Model: $Model"
Write-Host "num_ctx=$NumCtx, max_tokens=$MaxTokens, max_history=$MaxHistory"

if (-not (Test-Path -LiteralPath $OllamaModelsDir)) {
    throw "Ollama models directory does not exist: $OllamaModelsDir"
}

if (-not (Test-OllamaReady)) {
    Write-Host "Ollama is not running. Starting ollama serve in background..."
    Start-Process -FilePath "ollama" -ArgumentList @("serve") -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
    if (-not (Wait-OllamaReady -TimeoutSeconds 30)) {
        throw "Ollama did not become ready within 30 seconds. Run manually: `$env:OLLAMA_MODELS=`"$OllamaModelsDir`"; ollama serve"
    }
}
else {
    Write-Host "Ollama is already running."
}

if (-not (Test-OllamaModelAvailable -ModelName $Model)) {
    Write-Warning "Ollama model list does not include: $Model"
    Write-Warning "If you later see 'model not found', close the running Ollama process and run this script again."
}

$python = Get-PythonCommand -ProjectRoot $projectRoot
$displayHost = Get-DisplayHost -BindHost $HostAddress
$url = "http://$displayHost`:$Port/?token=$Token"

Write-Host "Private console URL: $url"
if ($Remote) {
    Write-Host "For phone access, replace 127.0.0.1 with your PC LAN IP or Tailscale IP."
}

if (-not $NoBrowser) {
    Start-Process $url | Out-Null
}

& $python -m src.local_console `
    --host $HostAddress `
    --port $Port `
    --token $Token `
    --model $Model `
    --base-url "http://127.0.0.1:11434" `
    --num-ctx $NumCtx `
    --disable-thinking `
    --enable-model
