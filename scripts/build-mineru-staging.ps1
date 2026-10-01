# 构建 MinerU OCR 运行时与 pipeline 模型到 build-staging/mineru/
#
# 产物布局（electron-builder extraResources 打入安装包 resources/mineru/）：
#   build-staging/mineru/python/   可重定位 Python 3.12（python-build-standalone）
#                                  + mineru[pipeline]==3.4.5（PyPI 默认 CPU 版 torch）
#   build-staging/mineru/models/   PDF-Extract-Kit-1.0 快照内容（snapshot master 下的 models/ 树）
#
# sidecar 运行时：
#   BIDCRAFT_RESOURCES_PATH/mineru/python/python.exe 解释执行 mineru.cli.client；
#   dataRoot/mineru/mineru.json 指向 models/，MINERU_MODEL_SOURCE=local 离线使用。
#
# 本机复用已下载模型（避免重复拉取 1.2GB）：
#   .\scripts\build-mineru-staging.ps1 `
#     -LocalModelsSnapshot "$env:USERPROFILE\.cache\modelscope\models\OpenDataLab--PDF-Extract-Kit-1.0\snapshots\master"
param(
    [string]$StagingRoot = "$PSScriptRoot\..\build-staging",
    [string]$PythonVersion = "3.12",
    # 指定已存在的 PDF-Extract-Kit snapshot master 目录时直接复制，跳过联网下载
    [string]$LocalModelsSnapshot = "",
    # 联网下载时的 modelscope 缓存根（CI 用 actions/cache 缓存该目录）
    [string]$ModelCache = (Join-Path $env:USERPROFILE ".cache\modelscope")
)

$ErrorActionPreference = "Stop"
$mineruRoot = Join-Path $StagingRoot "mineru"
$pyHome = Join-Path $mineruRoot "python"
$pyExe = Join-Path $pyHome "python.exe"
$modelsDst = Join-Path $mineruRoot "models"
$installMarker = Join-Path $pyHome ".mineru-3.4.5.installed"
$snapshotRel = "models\OpenDataLab--PDF-Extract-Kit-1.0\snapshots\master"

# ---------- 1) 可重定位 Python 运行时 ----------
if (Test-Path $pyExe) {
    Write-Host "=== [1/3] 复用已有 Python 运行时：$pyHome ===" -ForegroundColor Cyan
}
else {
    Write-Host "=== [1/3] 准备 python-build-standalone $PythonVersion ===" -ForegroundColor Cyan
    uv python install $PythonVersion
    if ($LASTEXITCODE -ne 0) { throw "uv python install 失败" }

    # uv python dir：uv 托管 Python 的根。目录命名随 uv 版本有两种形态：
    #   新版 cpython-3.12.12-windows-x86_64-none
    #   旧版 cpython-3.12.x+ts-...-x86_64-pc-windows-msvc
    # 优先带补丁号的实际安装目录（名称排序 desc 时它排在无补丁号的共享前缀之前）
    $managedRoot = (uv python dir).Trim()
    $pattern = "cpython-$PythonVersion*-*x86_64-*"
    $srcHome = Get-ChildItem -Path $managedRoot -Directory -Filter $pattern |
        Where-Object { Test-Path (Join-Path $_.FullName "python.exe") } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $srcHome) {
        throw "未在 $managedRoot 找到 $pattern；可先执行 uv python install $PythonVersion 后重试"
    }
    Write-Host "  复制可重定位运行时：$($srcHome.FullName)" -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $pyHome | Out-Null
    Copy-Item (Join-Path $srcHome.FullName "*") $pyHome -Recurse -Force
    # 此副本用于随安装包分发的独立环境，删除 PEP 668 标记以允许 pip 直装
    $extManaged = Join-Path $pyHome "Lib\EXTERNALLY-MANAGED"
    if (Test-Path $extManaged) { Remove-Item $extManaged -Force }

    # 剔除运行时不需要的开发/测试文件（mineru 链路不使用 tk 与 C 开发文件）
    foreach ($devDir in @("include", "libs", "tcl", "Lib\tkinter", "Lib\test")) {
        $p = Join-Path $pyHome $devDir
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
}

# ---------- 2) 安装 mineru[pipeline]==3.4.5（CPU） ----------
if (Test-Path $installMarker) {
    Write-Host "=== [2/3] 复用已安装 mineru 3.4.5 ===" -ForegroundColor Cyan
}
else {
    Write-Host "=== [2/3] 安装 mineru[pipeline]==3.4.5（PyPI 默认 CPU torch，耗时较长）===" -ForegroundColor Cyan
    # 不能用 uv pip：uv 拒绝向其托管来源的 standalone 解释器装包（externally managed）；
    # python-build-standalone install_only 自带 pip 且无 EXTERNALLY-MANAGED，可直接安装
    & $pyExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip 自举失败" }
    & $pyExe -m pip install "mineru[pipeline]==3.4.5"
    if ($LASTEXITCODE -ne 0) { throw "mineru 安装失败" }
    # six 是 mineru 内置 pytorchocr（paddleocr 衍生代码 imaug/operators.py）的
    # 隐式依赖，未被 mineru 3.4.5 的元数据声明，干净环境下漏装会在 OCR 首跑时报
    # ModuleNotFoundError: No module named 'six'
    & $pyExe -m pip install "six==1.17.0"
    if ($LASTEXITCODE -ne 0) { throw "six 安装失败" }
    # 校验 CLI 可从该解释器以 -m 方式启动（分发不依赖 mineru.exe wrapper）
    & $pyExe -c "import mineru; print('mineru', __import__('importlib.metadata', fromlist=['version']).version('mineru'))"
    if ($LASTEXITCODE -ne 0) { throw "mineru 安装校验失败" }
    New-Item -ItemType File -Path $installMarker | Out-Null
}

# ---------- 3) pipeline 模型（PDF-Extract-Kit-1.0 快照） ----------
if (Test-Path (Join-Path $modelsDst "models")) {
    Write-Host "=== [3/3] 复用已有模型目录：$modelsDst ===" -ForegroundColor Cyan
}
elseif ($LocalModelsSnapshot -ne "") {
    if (-not (Test-Path (Join-Path $LocalModelsSnapshot "models"))) {
        throw "LocalModelsSnapshot 下未找到 models/ 子目录：$LocalModelsSnapshot"
    }
    Write-Host "=== [3/3] 从本机快照复制模型：$LocalModelsSnapshot ===" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $modelsDst | Out-Null
    Copy-Item (Join-Path $LocalModelsSnapshot "*") $modelsDst -Recurse -Force
}
else {
    Write-Host "=== [3/3] 从 ModelScope 下载 pipeline 模型（约 1.2GB）===" -ForegroundColor Cyan
    $env:MINERU_MODEL_SOURCE = "modelscope"
    $env:MODELSCOPE_CACHE = $ModelCache
    & $pyExe -m mineru.cli.models_download -s modelscope -m pipeline
    if ($LASTEXITCODE -ne 0) { throw "模型下载失败" }
    $snapshot = Join-Path $ModelCache $snapshotRel
    if (-not (Test-Path (Join-Path $snapshot "models"))) {
        throw "下载后未找到快照：$snapshot"
    }
    New-Item -ItemType Directory -Force -Path $modelsDst | Out-Null
    Copy-Item (Join-Path $snapshot "*") $modelsDst -Recurse -Force
}

# ---------- 汇总 ----------
function Get-DirSizeMB($path) {
    [math]::Round(((Get-ChildItem -Recurse -Force $path | Measure-Object Length -Sum).Sum / 1MB), 0)
}
Write-Host ""
Write-Host "✅ MinerU staging 就绪：$mineruRoot" -ForegroundColor Green
Write-Host ("  python : {0} MB" -f (Get-DirSizeMB $pyHome)) -ForegroundColor Green
Write-Host ("  models : {0} MB" -f (Get-DirSizeMB $modelsDst)) -ForegroundColor Green
