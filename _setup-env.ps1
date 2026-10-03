param(
    # Interpreter used to create the venv. Pass -BasePython to point at a
    # specific one if `python` is not on your PATH.
    [string]$BasePython = 'python'
)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$log  = Join-Path $root '_setup.log'
New-Item -ItemType Directory -Force -Path "$root\data" | Out-Null
function Say($m) { $m | Tee-Object -FilePath $log -Append }

Say "=== creating venv ==="
$basePy = $BasePython
Say "base python: $(& $basePy -c 'import sys; print(sys.version)')"
& $basePy -m venv "$root\pyenv" 2>&1 | Tee-Object -FilePath $log -Append
$py = "$root\pyenv\Scripts\python.exe"
if (-not (Test-Path $py)) { Say 'VENV FAILED'; exit 1 }
Say "venv python: $(& $py -c 'import sys; print(sys.version)')"

$mirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
Say "=== pip upgrade ==="
& $py -m pip install --upgrade pip -i $mirror --timeout 60 2>&1 | Tee-Object -FilePath $log -Append

Say "=== installing dependencies ==="
& $py -m pip install -i $mirror --timeout 60 `
    'pyqt5==5.15.11' 'pyqt5-qt5==5.15.2' `
    'pydantic>=2.12.5,<3.0.0' 'pydantic-extra-types>=2.10.6,<3.0.0' `
    'streamlink>=8.4.0,<9.0.0' 'yt-dlp[default]>=2026.7.4,<2027.0.0' 2>&1 | Tee-Object -FilePath $log -Append

Say "=== verify imports ==="
& $py -c "import PyQt5.QtWidgets, pydantic, pydantic_extra_types, streamlink; print('IMPORTS OK'); import PyQt5.QtCore as c; print('Qt', c.QT_VERSION_STR)" 2>&1 | Tee-Object -FilePath $log -Append
Say "=== ENV SETUP DONE ==="
