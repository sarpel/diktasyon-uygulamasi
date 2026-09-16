$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,anthropic,openai,gemini]"
pytest -q
pyinstaller --noconfirm --clean packaging\dikte.spec
$version = (Select-String -Path packaging\installer.iss -Pattern '#define AppVersion "(.+)"').Matches[0].Groups[1].Value
$iscc = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 bulunamadı (winget install JRSoftware.InnoSetup). Taşınabilir derleme hazır: dist\Dikte"
    exit 0
}
& $iscc packaging\installer.iss
Write-Host "Kurulum paketi: dist\Dikte-Setup-$version.exe"
