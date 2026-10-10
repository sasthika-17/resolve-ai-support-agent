param([string]$PythonPath = 'python')

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $PythonPath -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Check that Python 3.12 is installed.' }
    }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Review the pip error above.' }
}
finally { Pop-Location }
Write-Output 'Run .\.venv\Scripts\python.exe run.py and open http://127.0.0.1:8010'
