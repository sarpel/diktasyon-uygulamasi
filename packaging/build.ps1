$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,anthropic,openai,gemini]"
pytest -q
pyinstaller --noconfirm --clean packaging\dikte.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
Write-Host "Kurulum paketi: dist\Dikte-Setup-0.1.0.exe"
