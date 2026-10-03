$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath '.tools\uv.exe') {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { & '.\.tools\uv.exe' venv --python 3.12 }
    & '.\.tools\uv.exe' pip install -r requirements-audio.txt
} else {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 from python.org, then run setup.ps1 again.' }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-audio.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& '.\.venv\Scripts\python.exe' scripts\prepare_model.py
if ($LASTEXITCODE -ne 0) { throw 'Speech model preparation failed. Check internet access and rerun setup.ps1.' }
Write-Host 'Ready. Run start.bat. Add GROQ_API_KEY to .env when available for AI analysis.'
