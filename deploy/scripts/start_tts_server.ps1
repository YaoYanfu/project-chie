param(
    [string]$SoVitsDir = "D:\GPT-soVITS\GPT-SoVITS-v2pro-20250604-nvidia50",
    [string]$PythonExe = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 9880,
    [int]$TimeoutSeconds = 60,
    [switch]$NoBrowser,
    [switch]$Background
)

$ErrorActionPreference = "Stop"

function Test-TtsReady {
    param([string]$Url, [int]$TimeoutSec = 2)
    try {
        $null = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec
        return $true
    }
    catch {
        return $false
    }
}

function Wait-TtsReady {
    param([string]$Url, [int]$TimeoutSeconds = 60)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TtsReady -Url $Url) {
            return $true
        }
        $elapsed = [math]::Round(($deadline - (Get-Date)).TotalSeconds)
        Write-Host "[TTS] Waiting for GPT-SoVITS... ($elapsed s remaining)" -NoNewline
        Start-Sleep -Seconds 2
        Write-Host "`r" -NoNewline
    }
    return $false
}

function Test-SoVitsApiPy {
    param([string]$Dir)
    $apiPy = Join-Path $Dir "api_v2.py"
    return Test-Path -LiteralPath $apiPy
}

function Test-PythonInDir {
    param([string]$Dir)
    $candidates = @(
        (Join-Path $Dir ".venv\Scripts\python.exe"),
        (Join-Path $Dir "runtime\python.exe"),
        (Join-Path $Dir "python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Get-PythonCommand {
    param([string]$SoVitsDir, [string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
        return $ExplicitPath
    }

    $found = Test-PythonInDir -Dir $SoVitsDir
    if ($found) {
        return $found
    }

    $globalPython = Get-Command python -ErrorAction SilentlyContinue
    if ($globalPython) {
        return $globalPython.Source
    }

    throw "Cannot find Python. Use -PythonExe to specify path, or install Python and add it to PATH."
}

function Test-PortInUse {
    param([string]$Host, [int]$Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new($Host, $Port)
        $listener.Start()
        $listener.Stop()
        return $false
    }
    catch {
        return $true
    }
}

# ---- main ----

Write-Host "=" * 60
Write-Host "Project Chie GPT-SoVITS TTS launcher"
Write-Host "=" * 60
Write-Host "SoVITS install dir: $SoVitsDir"
Write-Host "TTS API: http://$HostAddress`:$Port/tts"
Write-Host ""

if (-not (Test-Path -LiteralPath $SoVitsDir)) {
    throw "GPT-SoVITS directory not found: $SoVitsDir`nSet -SoVitsDir to your GPT-SoVITS installation path."
}

if (-not (Test-SoVitsApiPy -Dir $SoVitsDir)) {
    throw "api_v2.py not found under $SoVitsDir`nPlease confirm this is a GPT-SoVITS installation."
}

$checkUrl = "http://$HostAddress`:$Port/tts"

if (Test-TtsReady -Url $checkUrl) {
    Write-Host "[TTS] GPT-SoVITS is already running at $checkUrl"
    if (-not $NoBrowser) {
        Write-Host "[TTS] Done. Project Chie voice config: gpt_sovits_api_url = `"$checkUrl`""
    }
    exit 0
}

$pythonPath = Get-PythonCommand -SoVitsDir $SoVitsDir -ExplicitPath $PythonExe
Write-Host "[TTS] Python: $pythonPath"
Write-Host "[TTS] Starting GPT-SoVITS api_v2.py..."

$envArgs = @{}
if ($env:OLLAMA_MODELS) {
    $envArgs["OLLAMA_MODELS"] = $env:OLLAMA_MODELS
}

if ($Background) {
    $proc = Start-Process -FilePath $pythonPath `
        -ArgumentList @("api_v2.py", "--host", $HostAddress, "--port", $Port) `
        -WorkingDirectory $SoVitsDir `
        -WindowStyle Hidden `
        -PassThru

    Write-Host "[TTS] GPT-SoVITS started in background (PID $($proc.Id))"

    if (Wait-TtsReady -Url $checkUrl -TimeoutSeconds $TimeoutSeconds) {
        Write-Host "`n[TTS] GPT-SoVITS is ready at $checkUrl"
        Write-Host "[TTS] Project Chie voice config: gpt_sovits_api_url = `"$checkUrl`""
        Write-Host "[TTS] Background process PID: $($proc.Id) (close with: Stop-Process -Id $($proc.Id))"
    }
    else {
        Write-Host "`n[TTS] WARNING: GPT-SoVITS did not become ready within $TimeoutSeconds s"
        Write-Host "[TTS] The process may still be loading. Check manually: curl $checkUrl"
    }
}
else {
    Write-Host "[TTS] Starting in foreground (Ctrl+C to stop)..."
    Write-Host "[TTS] Project Chie voice config: gpt_sovits_api_url = `"$checkUrl`""
    Write-Host ""

    & $pythonPath "api_v2.py" --host $HostAddress --port $Port
}
