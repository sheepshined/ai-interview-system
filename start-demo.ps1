# ============================================================
# AI 模拟面试系统 · 一键演示启动
# 用法: 在仓库根目录执行  .\start-demo.ps1
# 作用: 检查环境 -> 启动后端(8000) -> 等健康检查 -> 启动前端(3001) -> 打开浏览器
# 关闭: 直接关闭弹出的两个窗口即可
# ============================================================

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend-v2"

function Test-PortInUse([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-HttpOk([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 800 }
    }
    return $false
}

Write-Host "== AI 模拟面试系统 一键启动 ==" -ForegroundColor White

# 1) 环境检查
$venvPython = Join-Path $BACKEND ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[X] 未找到后端虚拟环境 $venvPython" -ForegroundColor Red
    Write-Host "    请先按 README.md 完成首次准备 (python -m venv .venv + pip install)"
    exit 1
}
if (-not (Test-Path (Join-Path $FRONTEND "node_modules"))) {
    Write-Host "[X] 未找到前端依赖 frontend-v2\node_modules" -ForegroundColor Red
    Write-Host "    请先执行: cd frontend-v2; npm install"
    exit 1
}
if (-not (Test-Path (Join-Path $BACKEND ".env"))) {
    Write-Host "[!] 未找到 backend\.env, LLM 功能将不可用; 请按 README 配置 LLM_API_KEY" -ForegroundColor Yellow
}

# 2) 端口检查
if (Test-PortInUse 8000) {
    Write-Host "[!] 端口 8000 已被占用: 若已有后端在跑, 将直接复用它" -ForegroundColor Yellow
} else {
    Write-Host "[1/3] 启动后端 (uvicorn, 端口 8000)..."
    Start-Process -WorkingDirectory $BACKEND -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"
}

if (Wait-HttpOk "http://127.0.0.1:8000/healthz" 90) {
    Write-Host "      后端健康检查通过 /healthz = 200" -ForegroundColor Green
} else {
    Write-Host "[X] 后端 90 秒内未通过 /healthz, 请查看后端窗口的报错" -ForegroundColor Red
    exit 1
}

if (Test-PortInUse 3001) {
    Write-Host "[!] 端口 3001 已被占用: 若已有前端在跑, 将直接复用它" -ForegroundColor Yellow
} else {
    Write-Host "[2/3] 启动前端 (Vite, 端口 3001)..."
    Start-Process -WorkingDirectory $FRONTEND -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev -- --host 127.0.0.1"
}

if (Wait-HttpOk "http://127.0.0.1:3001" 90) {
    Write-Host "      前端已就绪" -ForegroundColor Green
} else {
    Write-Host "[!] 前端 90 秒内未就绪, 可手动打开 http://127.0.0.1:3001" -ForegroundColor Yellow
}

# 3) 打开浏览器
Write-Host "[3/3] 打开浏览器 http://127.0.0.1:3001 (演示账号 admin / 123123)" -ForegroundColor White
Start-Process "http://127.0.0.1:3001"
Write-Host "完成。关闭演示: 关闭后端与前端两个窗口即可。" -ForegroundColor Gray
