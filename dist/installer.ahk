#Requires AutoHotkey v2.0
#SingleInstance Force

; ============================================================
; PerAxSetup.exe - self-contained installer (compiled from this script with the whole
; app embedded as payload.zip). Needs nothing pre-installed: Python, Pillow and AutoHotkey
; are all inside the payload.
;
;   PerAxSetup.exe              show the install window (normal use)
;   PerAxSetup.exe /upgrade     silent reinstall over the existing copy (used by the updater)
;   PerAxSetup.exe /uninstall   remove Per-Ax
;
; Installs to %LOCALAPPDATA%\Per-Ax and makes Desktop + Start Menu shortcuts. "Start with
; Windows" is a checkbox (the HKCU Run value Settings -> Startup also toggles); a silent
; /upgrade leaves that choice exactly as it was.
; ============================================================

APPNAME := "Per-Ax"
PUBLISHER := "JustHosh"
TARGET := EnvGet("LOCALAPPDATA") "\" APPNAME
REGKEY := "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\" APPNAME
RUNKEY := "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"   ; = smiteconfig._RUN_KEY

mode := "gui"
for a in A_Args {
    if (a = "/upgrade" || a = "/S" || a = "/silent")
        mode := "silent"
    else if (a = "/uninstall")
        mode := "uninstall"
}

if (mode = "uninstall") {
    Uninstall()
    ExitApp()
} else if (mode = "silent") {
    DoInstall(true, true)            ; upgrade path: relaunch the tray after replacing files
    ExitApp()
}

; ---------- normal GUI install ----------
g := Gui("+AlwaysOnTop -MaximizeBox -MinimizeBox", APPNAME " Setup")
g.BackColor := "0x11131A"
g.SetFont("s10 cWhite", "Segoe UI")
g.MarginX := 22, g.MarginY := 18
g.SetFont("s15 bold c0xC8AA6E")
g.Add("Text", , "Per-Ax")
g.SetFont("s10 cWhite")
g.Add("Text", "y+8 w430", "A League of Legends champ-select and in-game overlay.")
g.Add("Text", "y+12 w430 c0x9B988E",
    "This installs everything it needs (nothing else to download) into your account folder "
    . "and adds a desktop shortcut. Run League in Borderless mode.")
startWin := g.Add("Checkbox", "y+10 w430 Checked", "Start with Windows (needed for it to open by itself at champ select)")
g.SetFont("s9 c0x9B988E")
g.Add("Text", "y+12 w430", "Installs to:  " TARGET)
btn := g.Add("Button", "y+18 w120 h34 Default", "Install")
btn.SetFont("s10 bold")
cancel := g.Add("Button", "x+10 yp w90 h34", "Cancel")
status := g.Add("Text", "xm y+14 w430 c0x9B988E", "")
btn.OnEvent("Click", GuiInstall)
cancel.OnEvent("Click", (*) => ExitApp())
g.OnEvent("Close", (*) => ExitApp())
g.Show()

GuiInstall(*) {
    global g, btn, cancel, status, TARGET, startWin
    btn.Enabled := false, cancel.Enabled := false
    status.Value := "Installing..."
    DoInstall(true, false, startWin.Value ? 1 : 0)
    if startWin.Value
        status.Value := "Done!  Per-Ax is starting and will run with Windows."
    else
        status.Value := "Done!  Per-Ax is starting (it will not start with Windows)."
    btn.Text := "Finish", btn.Enabled := true
    btn.OnEvent("Click", (*) => ExitApp())
    MsgBox("Per-Ax is installed and running.`n`nLook for the gold 'P' icon near your clock "
        . "(click the ^ arrow if you don't see it). Press Ctrl+Alt+X any time to open it.",
        APPNAME, "Iconi")
    ExitApp()
}

; startup: 1 = start with Windows, 0 = don't, -1 = leave the current choice alone (upgrade)
DoInstall(launch, upgraded := false, startup := -1) {
    global TARGET, REGKEY, APPNAME, PUBLISHER, RUNKEY
    ; stop any running copy so files aren't locked
    RunWait(A_ComSpec ' /c taskkill /F /IM PerAx.exe /IM PerAxApp.exe >nul 2>nul', , "Hide")
    Sleep(400)
    DirCreate(TARGET)
    ; extract the embedded payload (Expand-Archive reads the Compress-Archive zip reliably)
    tmp := A_Temp "\perax_payload.zip"
    FileInstall("payload.zip", tmp, 1)
    psfile := A_Temp "\perax_extract.ps1"
    try FileDelete(psfile)
    FileAppend("Expand-Archive -LiteralPath '" tmp "' -DestinationPath '" TARGET "' -Force", psfile)
    RunWait('powershell -NoProfile -ExecutionPolicy Bypass -File "' psfile '"', , "Hide")
    try FileDelete(psfile)
    try FileDelete(tmp)
    ; keep a copy of this installer for clean uninstall
    try FileCopy(A_ScriptFullPath, TARGET "\Uninstall.exe", 1)
    ; shortcuts (Desktop, Start Menu). Autostart is the HKCU Run value, never a Startup-folder
    ; shortcut: one mechanism, the same one Settings -> "Start with Windows" toggles.
    ico := TARGET "\assets\perax.ico"
    exe := TARGET "\PerAx.exe"
    FileCreateShortcut(exe, A_Desktop "\Per-Ax.lnk", TARGET, , APPNAME, ico)
    if (startup = 1)
        RegWrite('"' exe '"', "REG_SZ", RUNKEY, APPNAME)
    else if (startup = 0)
        try RegDelete(RUNKEY, APPNAME)
    DirCreate(A_Programs "\" APPNAME)
    FileCreateShortcut(exe, A_Programs "\" APPNAME "\Per-Ax.lnk", TARGET, , APPNAME, ico)
    FileCreateShortcut(TARGET "\Uninstall.exe", A_Programs "\" APPNAME "\Uninstall Per-Ax.lnk",
        TARGET, "/uninstall", "Uninstall " APPNAME, ico)
    ; Add/Remove Programs entry
    ver := "1.0.0"
    try ver := Trim(FileRead(TARGET "\VERSION"), " `t`r`n")
    if (upgraded) {
        try FileDelete(TARGET "\.updated_version")
        try FileAppend(ver, TARGET "\.updated_version")
    }
    RegWrite(APPNAME, "REG_SZ", REGKEY, "DisplayName")
    RegWrite('"' TARGET '\Uninstall.exe" /uninstall', "REG_SZ", REGKEY, "UninstallString")
    RegWrite(ico, "REG_SZ", REGKEY, "DisplayIcon")
    RegWrite(ver, "REG_SZ", REGKEY, "DisplayVersion")
    RegWrite(PUBLISHER, "REG_SZ", REGKEY, "Publisher")
    RegWrite(TARGET, "REG_SZ", REGKEY, "InstallLocation")
    RegWrite(1, "REG_DWORD", REGKEY, "NoModify")
    RegWrite(1, "REG_DWORD", REGKEY, "NoRepair")
    if (launch) {
        ; If the expected exe is missing (AV/quarantine or extraction issue), try common fallback paths
        if (!FileExist(exe)) {
            alt := TARGET "\app\PerAxApp\PerAxApp.exe"
            if (FileExist(alt)) {
                exe := alt
            } else {
                MsgBox("Installation finished but the launcher exe wasn't found.\n\nThis can happen if antivirus quarantined files or extraction failed.\nPlease check " TARGET " and re-run PerAx.exe if present.", APPNAME, "Iconi")
                return
            }
        }
        Run('"' exe '"', TARGET)
    }
}

Uninstall() {
    global TARGET, REGKEY, APPNAME, RUNKEY
    RunWait(A_ComSpec ' /c taskkill /F /IM PerAx.exe /IM PerAxApp.exe >nul 2>nul', , "Hide")
    Sleep(400)
    try FileDelete(A_Desktop "\Per-Ax.lnk")
    try RegDelete(RUNKEY, APPNAME)
    try DirDelete(A_Programs "\" APPNAME, true)
    try RegDeleteKey(REGKEY)
    ; remove the install folder. Uninstall.exe runs from INSIDE it, so a detached batch
    ; retries rmdir until the exe has exited and the folder unlocks, then deletes itself.
    bat := A_Temp "\perax_uninstall.bat"
    try FileDelete(bat)
    FileAppend('@echo off`r`n'
        . ':retry`r`n'
        . 'rmdir /s /q "' TARGET '" 2>nul`r`n'
        . 'if exist "' TARGET '" ( ping 127.0.0.1 -n 2 >nul & goto retry )`r`n'
        . 'del "%~f0"`r`n', bat)
    Run(A_ComSpec ' /c "' bat '"', , "Hide")
    MsgBox(APPNAME " has been removed.", APPNAME, "Iconi")
}
