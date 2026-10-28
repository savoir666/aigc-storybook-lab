$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$tempPath = Join-Path $projectRoot 'work\tmp'
New-Item -ItemType Directory -Force -Path $tempPath | Out-Null
$env:TEMP = $tempPath
$env:TMP = $tempPath
$env:PIP_CACHE_DIR = Join-Path $projectRoot 'work\cache\pip'
$env:HF_HOME = Join-Path $projectRoot 'work\cache\huggingface'
$env:XDG_CACHE_HOME = Join-Path $projectRoot 'work\cache'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonPath = $null
if (Test-Path -LiteralPath $venvPython) { $pythonPath = $venvPython }
if (-not $pythonPath) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Source -notmatch 'WindowsApps') { $pythonPath = $candidate.Source }
    elseif (Test-Path -LiteralPath $bundledPython) { $pythonPath = $bundledPython }
}
if (-not $pythonPath) { throw '请先安装 Python 3.12，并勾选 Add Python to PATH。' }
$developmentDeps = [IO.Path]::GetFullPath((Join-Path $projectRoot '..\..\work\python_deps'))
if ((Test-Path -LiteralPath (Join-Path $developmentDeps 'fastapi')) -and (Test-Path -LiteralPath $bundledPython)) {
    $pythonPath = $bundledPython
    $env:PYTHONPATH = "$developmentDeps;$(Join-Path $projectRoot 'src')"
} else {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $pythonPath -m venv '.venv'
        if ($LASTEXITCODE -ne 0) { throw '创建Python环境失败。' }
    }
    $pythonPath = $venvPython
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    & $pythonPath -c 'import fastapi,uvicorn,edge_tts,onnxruntime,langchain_core,reportlab,PIL,sklearn'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '首次启动：安装开源依赖，不会购买模型服务。'
        & $pythonPath -m pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重试。' }
    }
}
if (-not (Test-Path -LiteralPath 'data\library\manifest.json')) {
    & $pythonPath scripts/seed_assets.py
    if ($LASTEXITCODE -ne 0) { throw '创建示例素材失败。' }
}
$env:STORYBOOK_PORT = '8766'
$check = Test-NetConnection -ComputerName 127.0.0.1 -Port 8766 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($check) {
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/status' -TimeoutSec 3
        if ($status.name -eq '星芽故事屋') { Start-Process 'http://127.0.0.1:8766'; exit 0 }
    } catch { }
    throw '8766端口已被其他程序占用，请关闭该程序后重试。'
}
Write-Host '星芽故事屋即将启动：http://127.0.0.1:8766'
Write-Host '服务窗口需保持打开；按 Ctrl+C 关闭服务。'
Start-Process -FilePath $pythonPath -ArgumentList @('-c', '"import time,webbrowser;time.sleep(3);webbrowser.open(''http://127.0.0.1:8766'')"') -WindowStyle Hidden
& $pythonPath -m uvicorn storybook.server:app --host 127.0.0.1 --port 8766
