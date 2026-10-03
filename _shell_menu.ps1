# Registers a Windows Explorer context-menu entry that hands the selected
# video files to GridPlayer (MOD). HKCU only - no admin rights needed.
#
# NOTE: this file is deliberately ASCII-only. Windows PowerShell 5.1 reads a
# BOM-less UTF-8 script using the system ANSI codepage, which mangles non-ASCII
# text into stray quotes and parse errors. The (Chinese) menu label therefore
# lives in _shell_menu_label.txt and is read back as explicit UTF-8.
#
# Usage:
#   powershell -File _shell_menu.ps1              # install
#   powershell -File _shell_menu.ps1 -Unregister  # remove

param(
    [switch]$Unregister,
    [string]$Launcher = '',
    [string]$Entry    = ''
)

$ErrorActionPreference = 'Stop'

$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$labelFile = Join-Path $root '_shell_menu_label.txt'
$label  = [System.IO.File]::ReadAllText($labelFile, [System.Text.Encoding]::UTF8).Trim()

# Default to this checkout's own launcher, so the script works wherever the
# repository sits. Override either one if you keep them somewhere else.
if (-not $Launcher) { $Launcher = Join-Path $root 'pyenv\Scripts\GridPlayer.exe' }
if (-not $Entry)    { $Entry    = Join-Path $root 'run_gridplayer.py' }

$verb = 'GridPlayerGrid'
$base = 'HKCU:\Software\Classes\SystemFileAssociations'

# The app's own video extension list, so this never drifts from what GridPlayer
# can actually open.
$exts = @(
    '3g2','3gp','3gp2','3gpp','amv','asf','avi','bik','crf','divx','drc','dv',
    'dvr-ms','evo','f4v','flv','gvi','gxf','h265','hevc','iso','m1v','m2t',
    'm2ts','m2v','m4v','mkv','mov','mp2','mp2v','mp4','mp4v','mpe','mpeg',
    'mpeg1','mpeg2','mpeg4','mpg','mpv2','mts','mtv','mxf','mxg','nsv','nuv',
    'ogg','ogm','ogv','ogx','ps','rec','rm','rmvb','rpl','thp','tod','ts',
    'tts','txd','vob','vro','webm','wm','wmv','wtv','xesc'
)

if ($Unregister) {
    $removed = 0
    foreach ($e in $exts) {
        $key = "$base\.$e\shell\$verb"
        if (Test-Path $key) {
            Remove-Item $key -Recurse -Force
            $removed++
        }
    }
    Write-Output "unregistered: removed $removed key(s)"
    exit 0
}

$iconFile = Join-Path $root 'GridPlayer.ico'

if (-not (Test-Path $Launcher)) { throw "launcher not found: $Launcher" }
if (-not (Test-Path $Entry))    { throw "entry script not found: $Entry" }
if (-not (Test-Path $iconFile)) { throw "icon not found: $iconFile" }

# "%1" is the file Windows is asking about. MultiSelectModel=Player means the
# command runs once PER selected file - GridPlayer's single-instance pipe then
# gathers them into the one running window, which is what makes a multi-select
# open as a grid.
$command = '"' + $Launcher + '" "' + $Entry + '" "%1"'

# GridPlayer.exe, not pythonw.exe: it is the same GUI interpreter under a name
# that says what it is, carrying the app's icon. Anything Windows remembers
# about the launcher - notably the "Open with" MRU - then shows GridPlayer's
# logo instead of Python's. Built by _make_launcher.py.
$icon    = '"' + $iconFile + '",0'

$written = 0
foreach ($e in $exts) {
    $key = "$base\.$e\shell\$verb"

    New-Item -Path $key -Force | Out-Null
    Set-Item -Path $key -Value $label
    New-ItemProperty -Path $key -Name 'MUIVerb'          -Value $label    -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $key -Name 'MultiSelectModel' -Value 'Player'  -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $key -Name 'Icon'             -Value $icon     -PropertyType String -Force | Out-Null

    New-Item -Path "$key\command" -Force | Out-Null
    Set-Item -Path "$key\command" -Value $command

    $written++
}

Write-Output "registered '$label' for $written extension(s)"
Write-Output "command: $command"
