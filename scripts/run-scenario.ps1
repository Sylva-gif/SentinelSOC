param([string]$BaseUrl = "http://localhost:8080")
$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = "python" }
& $pythonPath (Join-Path $PSScriptRoot "scenario.py") --base-url $BaseUrl
if ($LASTEXITCODE -ne 0) { throw "Le scénario a échoué." }
