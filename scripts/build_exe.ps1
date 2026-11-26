# Build Standalone Windows Executable for eSim Tool Manager
# Using PyInstaller with embedded tools.yaml resource bundle

$ErrorActionPreference = "Stop"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host " Building esim-tool-manager Standalone Executable" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Ensure output directory
$DistDir = Join-Path $PSScriptRoot "..\dist"
$BuildDir = Join-Path $PSScriptRoot "..\build"

if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}

# 2. Invoke PyInstaller
Write-Host "`n[1/3] Compiling standalone binary with PyInstaller..." -ForegroundColor Yellow

$SpecArgs = @(
    "-m", "PyInstaller",
    "--onefile",
    "--name", "esim-tool-manager",
    "--add-data", "esim_tool_manager\tools.yaml;esim_tool_manager",
    "--clean",
    "esim_tool_manager\__main__.py"
)

python @SpecArgs

# 3. Verify Output
$ExePath = Join-Path $DistDir "esim-tool-manager.exe"
if (Test-Path $ExePath) {
    $ExeSize = (Get-Item $ExePath).Length / 1MB
    Write-Host "`n[2/3] Executable successfully created at: $ExePath ($([math]::Round($ExeSize, 2)) MB)" -ForegroundColor Green

    Write-Host "`n[3/3] Validating compiled binary..." -ForegroundColor Yellow
    & $ExePath version
    & $ExePath list
    Write-Host "`nBuild and verification completed successfully!" -ForegroundColor Green
} else {
    Write-Error "Build failed: $ExePath was not generated."
}
