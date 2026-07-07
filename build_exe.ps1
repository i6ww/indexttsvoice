$ErrorActionPreference = "Stop"

$pyInstallerArgs = @(
  "--noconfirm",
  "--windowed",
  "--name", "秒图语音工厂",
  "--icon", "assets\icons\app.ico",
  "--hidden-import", "PySide6.QtMultimedia",
  "--add-data", "文案.txt;.",
  "--add-data", "assets;assets",
  "main.py"
)

python -m PyInstaller @pyInstallerArgs

Write-Host "Build complete: dist\秒图语音工厂\秒图语音工厂.exe"
