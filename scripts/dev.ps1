param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "start", "stop", "test", "status", "reset")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $Root
try {
    switch ($Action) {
        "install" {
            if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
            if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3.12 -m venv .venv }
            & ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
            if ($LASTEXITCODE -ne 0) { throw "Installation Python impossible." }
            npm ci --prefix frontend
            if ($LASTEXITCODE -ne 0) { throw "Installation frontend impossible." }
            Write-Host "Installation terminée. Lancez .\scripts\dev.ps1 start"
        }
        "start" {
            if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
            docker compose up --build -d --wait
            if ($LASTEXITCODE -ne 0) { throw "Démarrage Docker impossible." }
            Write-Host "Console SOC: http://localhost:8080"
        }
        "stop" { docker compose down }
        "test" {
            if (Test-Path ".venv\Scripts\python.exe") {
                & ".venv\Scripts\python.exe" -m pytest backend\tests -q
                if ($LASTEXITCODE -ne 0) { throw "Les tests Python ont échoué." }
            } else {
                docker compose run --rm api pytest -q
                if ($LASTEXITCODE -ne 0) { throw "Les tests Python ont échoué." }
            }
            npm ci --prefix frontend
            if ($LASTEXITCODE -ne 0) { throw "Installation frontend impossible." }
            npm run build --prefix frontend
            if ($LASTEXITCODE -ne 0) { throw "Build frontend échoué." }
            npm audit --prefix frontend
            if ($LASTEXITCODE -ne 0) { throw "Audit frontend échoué." }
        }
        "status" { docker compose ps }
        "reset" {
            $answer = Read-Host "Tapez RESET pour supprimer les volumes PostgreSQL, Redis et preuves du laboratoire"
            if ($answer -ne "RESET") { throw "Réinitialisation annulée." }
            docker compose down -v
        }
    }
} finally {
    Pop-Location
}