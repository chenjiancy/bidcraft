# 构建 sidecar exe（PyInstaller）到 build-staging/sidecar/
# electron-builder 通过 extraResources 将其打入安装包 resources/sidecar/。
# 注意：目标必须在 builder 输出目录 release/ 之外（extraResources 源不能位于输出目录）。
param(
    [string]$StagingRoot = "$PSScriptRoot\..\build-staging"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$sidecarDir = Join-Path $repoRoot "sidecar"
$dst = Join-Path $StagingRoot "sidecar"

Write-Host "=== [1/3] 安装 pyinstaller（sidecar/.venv）===" -ForegroundColor Cyan
Push-Location $sidecarDir
try {
    uv pip install pyinstaller --python (Join-Path $sidecarDir ".venv\Scripts\python.exe")

    Write-Host "=== [2/3] PyInstaller 打包 ===" -ForegroundColor Cyan
    if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
    uv run pyinstaller bidcraft-sidecar.spec --noconfirm

    Write-Host "=== [3/3] 复制产物到 $dst ===" -ForegroundColor Cyan
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item (Join-Path $sidecarDir "dist\bidcraft-sidecar.exe") `
        (Join-Path $dst "bidcraft-sidecar.exe") -Force
    Remove-Item "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "dist" -Recurse -Force -ErrorAction SilentlyContinue
}
finally {
    Pop-Location
}

$exe = Join-Path $dst "bidcraft-sidecar.exe"
if (-not (Test-Path $exe)) {
    Write-Host "❌ sidecar 构建失败：$exe 不存在" -ForegroundColor Red
    exit 1
}
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "✅ sidecar 就绪：$exe ($size MB)" -ForegroundColor Green
