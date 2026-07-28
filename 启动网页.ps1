$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot "Local_model\gpt-sovits-demo-env\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "没有找到项目 Python 环境：$python"
}

Set-Location -LiteralPath $projectRoot
Write-Host ""
Write-Host "峰言峰语工作台正在启动……" -ForegroundColor Yellow
Write-Host "浏览器地址：http://127.0.0.1:7860" -ForegroundColor Cyan
Write-Host "关闭本窗口即可停止服务。" -ForegroundColor DarkGray
Write-Host ""

& $python ".\feng_web.py"
