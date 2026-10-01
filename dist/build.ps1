# Builds PerAxSetup.exe (the self-contained installer) from source.
#
#   powershell -ExecutionPolicy Bypass -File dist\build.ps1 [-Python <python.exe>]
#
# Needs (on the BUILD machine only - not the user's): Python with PyInstaller
# (`pip install pyinstaller`), and AutoHotkey v2 + Ahk2Exe. Output: build\PerAxSetup.exe
param(
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$repo  = Split-Path $PSScriptRoot -Parent
$build = Join-Path $repo "build"
$stage = Join-Path $build "stage"
$ico   = Join-Path $repo "assets\perax.ico"

$ahk = "$env:LOCALAPPDATA\Programs\AutoHotkey\v2\AutoHotkey64.exe"
if (-not (Test-Path $ahk)) { $ahk = "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" }
$ahk2exe = "C:\Program Files\AutoHotkey\Compiler\Ahk2Exe.exe"
foreach ($p in @($ahk, $ahk2exe, $ico)) {
    if (-not (Test-Path $p)) { throw "missing required file: $p" }
}

function Invoke-Ahk2Exe($inFile, $outFile) {
    # Ahk2Exe is a GUI app, so '&' returns before it finishes - Start-Process -Wait blocks properly.
    Remove-Item $outFile -Force -ErrorAction SilentlyContinue
    $a = @("/in", "`"$inFile`"", "/out", "`"$outFile`"", "/base", "`"$ahk`"", "/icon", "`"$ico`"")
    $p = Start-Process -FilePath $ahk2exe -ArgumentList $a -Wait -PassThru -WindowStyle Hidden
    if (-not (Test-Path $outFile)) { throw "Ahk2Exe produced nothing for $inFile (exit $($p.ExitCode))" }
}

Write-Host "==> clean" -ForegroundColor Cyan
Remove-Item -Recurse -Force $build -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null

Write-Host "==> freeze Python app (PyInstaller)" -ForegroundColor Cyan
$hidden = @("smiteoverlay","smitewidget","smitedead","smiteload","smitequeue","smitesettings","smiteprofile","phasecheck","smiteupdate","smitekeycheck","selftest",
            "loldead","lolload","loltags","lolqueue","lolmute","lolreentry","lolbleed","lolclose","lolgold","lolward","lolout","lolfix","lolpool","lolfit","lolrunes",
            "smitecard","smiteconfig","smitepaths","lolbuild","lolgame","lolscout","lolmatchup","lolitems","lolrecommend",
            "lollive","lolvision","lolprofile","lolaccounts","claudecli",
            "lolugg","lollocal",   # scout fallback (u.gg) + your history off the client (LCU)
            # These five were reachable only through top-level imports of other modules, i.e. by
            # luck. selftest now asserts every core/ and ui/ module is listed here, because a
            # module PyInstaller misses ships an exe that crashes on import — a release missing
            # the very feature it is named for.
            "loldraft","lolimport","loltempo","smiteskin","smitenotes",
            "winsound","wave","PIL._tkinter_finder")
$pyiArgs = @("--noconfirm","--onedir","--windowed","--name","PerAxApp","--icon",$ico,
             "--paths",(Join-Path $repo "core"),"--paths",(Join-Path $repo "ui"),"--paths",(Join-Path $repo "tools"),
             "--distpath",(Join-Path $build "pyi"),"--workpath",(Join-Path $build "pyiwork"),"--specpath",$build)
foreach ($h in $hidden) { $pyiArgs += @("--hidden-import",$h) }
$pyiArgs += (Join-Path $repo "perax_main.py")
& $Python -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "==> compile tray -> PerAx.exe" -ForegroundColor Cyan
Invoke-Ahk2Exe (Join-Path $repo "dist\tray.ahk") (Join-Path $stage "PerAx.exe")

Write-Host "==> assemble install tree" -ForegroundColor Cyan
Copy-Item (Join-Path $build "pyi\PerAxApp") (Join-Path $stage "app") -Recurse
New-Item -ItemType Directory -Force (Join-Path $stage "assets") | Out-Null
Copy-Item $ico (Join-Path $stage "assets\perax.ico")
Copy-Item (Join-Path $repo "VERSION") (Join-Path $stage "VERSION")
Copy-Item (Join-Path $repo "CHANGELOG.md") (Join-Path $stage "CHANGELOG.md")   # Patch notes window reads this

Write-Host "==> zip payload" -ForegroundColor Cyan
$payload = Join-Path $repo "dist\payload.zip"   # next to installer.ahk for FileInstall
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $payload -Force

Write-Host "==> compile installer -> PerAxSetup.exe" -ForegroundColor Cyan
Invoke-Ahk2Exe (Join-Path $repo "dist\installer.ahk") (Join-Path $build "PerAxSetup.exe")
Remove-Item $payload -Force -ErrorAction SilentlyContinue

$size = "{0:N1}" -f ((Get-Item (Join-Path $build "PerAxSetup.exe")).Length / 1MB)
Write-Host "`nDONE -> $build\PerAxSetup.exe ($size MB)" -ForegroundColor Green
