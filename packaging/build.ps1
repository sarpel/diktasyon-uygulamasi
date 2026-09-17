$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,cuda,anthropic,openai,gemini]"
pytest -q
pyinstaller --noconfirm --clean packaging\dikte.spec
$version = (Select-String -Path packaging\installer.iss -Pattern '#define AppVersion "(.+)"').Matches[0].Groups[1].Value
# Inno Setup makine geneline, kullanıcıya özel veya winget dizinine kurulmuş olabilir;
# önce kayıt defterindeki kurulum yolu, sonra bilinen dizinler, sonra PATH denenir.
function Find-Iscc {
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )
    foreach ($key in $keys) {
        $loc = (Get-ItemProperty -Path $key -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
        if ($loc) {
            $candidate = Join-Path $loc "ISCC.exe"
            if (Test-Path $candidate) { return $candidate }
        }
    }
    $dirs = @(
        ${env:ProgramFiles(x86)},
        $env:ProgramFiles,
        (Join-Path $env:LOCALAPPDATA "Programs")
    ) | Where-Object { $_ }
    foreach ($dir in $dirs) {
        $candidate = Join-Path $dir "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    return (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
}

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Warning "Inno Setup 6 bulunamadı (winget install JRSoftware.InnoSetup). Taşınabilir derleme hazır: dist\Dikte"
    exit 0
}
& $iscc packaging\installer.iss
Write-Host "Kurulum paketi: dist\Dikte-Setup-$version.exe"
