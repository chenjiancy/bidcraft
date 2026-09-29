# 构建侧车 exe，输出到 release/ 目录
param(
    [string]$OutputDir = "$PSScriptRoot\..\release",
    [string]$Platform = "x64"
)

$ErrorActionPreference = "Stop"

Write-Host "=== BidCraft Sidecar 构建 ===" -ForegroundColor Cyan

# 安装 pyinstaller（在 sidecar venv 里）
Write-Host "[1/4] 安装 pyinstaller..." -ForegroundColor Yellow
cd "$PSScriptRoot\..\sidecar"
uv pip install pyinstaller --python 3.12

# 清理旧产物（仅保留 dist 目录供检查）
if (Test-Path "$OutputDir\sidecar") { Remove-Item "$OutputDir\sidecar" -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$OutputDir\sidecar" | Out-Null

# 运行 pyinstaller（不传 --clean，避免破坏缓存导致二次构建过慢）
Write-Host "[2/4] 执行 pyinstaller..." -ForegroundColor Yellow
cd "$PSScriptRoot\..\sidecar"
uv run pyinstaller bidcraft-sidecar.spec --noconfirm

# 复制 exe 到 release/sidecar/
Write-Host "[3/4] 复制产物..." -ForegroundColor Yellow
Copy-Item "dist\bidcraft-sidecar.exe" "$OutputDir\sidecar\bidcraft-sidecar.exe" -Force
Remove-Item "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "dist" -Recurse -Force -ErrorAction SilentlyContinue

# 验证
Write-Host "[4/4] 验证产物..." -ForegroundColor Yellow
$exe = "$OutputDir\sidecar\bidcraft-sidecar.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "  ✅ $exe ($size MB)" -ForegroundColor Green
} else {
    Write-Host "  ❌ 构建失败" -ForegroundColor Red
    exit 1
}

Write-Host "完成。侧车位于: $exe" -ForegroundColor Green
