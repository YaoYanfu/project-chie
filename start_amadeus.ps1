# Amadeus 一键启动脚本
#
# 这个脚本按以下顺序完成整个启动流程：
# 1. 检查本机配置和必要命令。
# 2. 建立 SSH 隧道，把本机 18001 端口安全转发到云端 MaiBot 的 8001 端口。
# 3. 启动本机 Amadeus 后端，并等待 127.0.0.1:8765 可以访问。
# 4. 通过 Amadeus 后端确认云端千惠在线、人物身份映射正常。
# 5. 启动 Electron 前端。
#
# 关闭 Electron 或按 Ctrl+C 后，脚本只会结束“本次由它启动”的后台进程；
# 启动脚本之前就已运行的 SSH 隧道或 Amadeus 后端不会被误关。

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$DashboardRoot = Join-Path $ProjectRoot 'dashboard'
$ConfigPath = Join-Path $ProjectRoot 'data\amadeus\config.json'
$LogDirectory = Join-Path $ProjectRoot 'data\amadeus\logs'

$CloudHost = 'ubuntu@82.156.88.63'
$TunnelPort = 18001
$AmadeusPort = 8765

$TunnelProcess = $null
$AmadeusProcess = $null

function Write-Step {
    param([string]$Message)

    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMilliseconds = 800
    )

    # 使用一次短 TCP 连接检查端口，避免 Test-NetConnection 每次等待太久。
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $ConnectTask = $Client.ConnectAsync($HostName, $Port)
        return $ConnectTask.Wait($TimeoutMilliseconds) -and $Client.Connected
    }
    catch {
        return $false
    }
    finally {
        $Client.Dispose()
    }
}

function Wait-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $Deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-AmadeusHealth {
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$AmadeusPort/health" -TimeoutSec 2
        return $Health.status -eq 'healthy'
    }
    catch {
        return $false
    }
}

try {
    Write-Step '检查项目、配置和运行环境'

    if (-not (Test-Path -LiteralPath $DashboardRoot)) {
        throw "找不到前端目录：$DashboardRoot"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "找不到 Amadeus 配置：$ConfigPath。请先完成云端地址、Token 和人物身份配置。"
    }

    # 这里只确认敏感配置存在，不会把 Token 输出到终端。
    $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$Config.remote_token)) {
        throw 'Amadeus 独立 Token 尚未配置。'
    }
    if ([string]::IsNullOrWhiteSpace([string]$Config.owner_person_id)) {
        throw 'Amadeus 人物身份 owner_person_id 尚未配置。'
    }
    if ([string]$Config.remote_base_url -ne "http://127.0.0.1:$TunnelPort") {
        throw "remote_base_url 当前不是 http://127.0.0.1:$TunnelPort，请先检查 data\amadeus\config.json。"
    }

    $SshCommand = Get-Command 'ssh.exe' -ErrorAction SilentlyContinue
    $NpmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
    if ($null -eq $SshCommand) {
        throw '找不到 ssh.exe，请先安装或启用 Windows OpenSSH 客户端。'
    }
    if ($null -eq $NpmCommand) {
        throw '找不到 npm.cmd，请先安装 Node.js。'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $DashboardRoot 'node_modules'))) {
        throw "前端依赖尚未安装。请先进入 $DashboardRoot 执行 npm install。"
    }

    Write-Host '环境检查完成。' -ForegroundColor Green

    Write-Step '建立本机到云端 MaiBot 的 SSH 安全隧道'

    if (Test-TcpPort -HostName '127.0.0.1' -Port $TunnelPort) {
        # 端口已经可用，说明隧道可能由你或另一个 Amadeus 实例启动，直接复用。
        Write-Host "127.0.0.1:$TunnelPort 已在监听，复用现有隧道。" -ForegroundColor Yellow
    }
    else {
        # -N 表示只做端口转发，不在服务器执行远程命令。
        # -L 把本机 18001 映射到云端机器自身的 8001，云端端口无需暴露给公网。
        # ServerAlive 选项用于及时发现断线，避免留下看似存在、实际失效的隧道。
        $SshArguments = @(
            '-N',
            '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=30',
            '-o', 'ServerAliveCountMax=3',
            '-L', "127.0.0.1:${TunnelPort}:127.0.0.1:8001",
            $CloudHost
        )
        $TunnelProcess = Start-Process `
            -FilePath $SshCommand.Source `
            -ArgumentList $SshArguments `
            -WindowStyle Hidden `
            -PassThru

        if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $TunnelPort -TimeoutSeconds 10)) {
            throw 'SSH 隧道启动失败。请先在终端手动执行一次 ssh ubuntu@82.156.88.63，确认密钥和主机指纹可用。'
        }
        Write-Host "SSH 隧道已建立（PID $($TunnelProcess.Id)）。" -ForegroundColor Green
    }

    Write-Step '启动本机 Amadeus 后端'

    if (Test-AmadeusHealth) {
        # 已运行的后端可能来自之前的终端或 Electron，直接复用。
        Write-Host "127.0.0.1:$AmadeusPort 上的 Amadeus 已在线，复用现有后端。" -ForegroundColor Yellow
    }
    else {
        # 优先使用项目虚拟环境，确保 Python 依赖版本与 MaiBot 项目一致。
        $VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $VenvPython) {
            $PythonExecutable = $VenvPython
        }
        else {
            $PythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
            if ($null -eq $PythonCommand) {
                throw '找不到 Python。请创建项目 .venv，或把 python.exe 加入 PATH。'
            }
            $PythonExecutable = $PythonCommand.Source
        }

        # 后端日志写入 data/amadeus/logs，启动失败时可以直接查看原因。
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        $StandardOutputLog = Join-Path $LogDirectory 'backend.stdout.log'
        $StandardErrorLog = Join-Path $LogDirectory 'backend.stderr.log'
        $AmadeusProcess = Start-Process `
            -FilePath $PythonExecutable `
            -ArgumentList @('-m', 'src.amadeus') `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $StandardOutputLog `
            -RedirectStandardError $StandardErrorLog `
            -PassThru

        if (-not (Wait-TcpPort -HostName '127.0.0.1' -Port $AmadeusPort -TimeoutSeconds 15)) {
            throw "Amadeus 后端启动失败，请查看日志：$StandardErrorLog"
        }
        Write-Host "Amadeus 后端已启动（PID $($AmadeusProcess.Id)）。" -ForegroundColor Green
    }

    Write-Step '验证 Amadeus 与云端千惠的连接'

    # /api/status 会同时检查云端 MaiBot 状态和本机人物身份映射。
    $Status = Invoke-RestMethod -Uri "http://127.0.0.1:$AmadeusPort/api/status" -TimeoutSec 10
    if (-not $Status.remote.online) {
        throw "云端 MaiBot 未连接：$($Status.remote.reason)"
    }
    if (-not $Status.identity.online -or -not $Status.identity.mapped) {
        throw "人物身份映射无效：$($Status.identity.reason)"
    }

    Write-Host "云端千惠在线；当前映射身份：$($Status.identity.display_name)" -ForegroundColor Green

    Write-Step '启动 Amadeus Electron 前端'
    Write-Host 'Electron 运行期间请保留此窗口。关闭前端或按 Ctrl+C 即可结束本次会话。' -ForegroundColor Yellow

    # Electron 在前台运行，所以其日志会显示在当前窗口，出错时便于直接查看。
    Push-Location $DashboardRoot
    try {
        & $NpmCommand.Source run electron:dev
        if ($LASTEXITCODE -ne 0) {
            throw "Electron 前端异常退出，退出码：$LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Host "`n启动失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '修复上述问题后重新运行本脚本即可。' -ForegroundColor Yellow
    exit 1
}
finally {
    Write-Step '清理本次启动的后台进程'

    # 只清理由本脚本创建并记录了 PID 的进程，复用的已有服务不会受到影响。
    if ($null -ne $AmadeusProcess -and -not $AmadeusProcess.HasExited) {
        Stop-Process -Id $AmadeusProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host '已停止本次启动的 Amadeus 后端。'
    }
    if ($null -ne $TunnelProcess -and -not $TunnelProcess.HasExited) {
        Stop-Process -Id $TunnelProcess.Id -Force -ErrorAction SilentlyContinue
        Write-Host '已关闭本次建立的 SSH 隧道。'
    }
}
