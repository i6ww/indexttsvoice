$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$appName = -join ([char[]](0x79D2, 0x56FE, 0x8BED, 0x97F3, 0x5DE5, 0x5382))

$pyInstallerArgs = @(
  "--noconfirm",
  "--windowed",
  "--name", $appName,
  "--icon", "assets\icons\app.ico",
  "--hidden-import", "PySide6.QtMultimedia",
  "--hidden-import", "_cffi_backend",
  "--collect-binaries", "cffi",
  "--add-data", "assets;assets",
  "main.py"
)

& $python -m PyInstaller @pyInstallerArgs

Write-Host "Build complete: dist\$appName\$appName.exe"
