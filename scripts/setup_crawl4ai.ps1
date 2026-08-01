# Powershell setup script for optional Crawl4AI dynamic browser acquisition

$ErrorActionPreference = "Stop"

$workspaceRoot = Get-Location
if (-not (Test-Path "$workspaceRoot\requirements-crawl4ai.txt") -or -not (Test-Path "$workspaceRoot\hermes")) {
    Write-Error "Error: Must run setup_crawl4ai.ps1 from the Hermes workspace root directory."
    exit 1
}

Write-Host "Installing Crawl4AI optional dependencies into virtual environment..."
& ".\.venv\Scripts\python.exe" -m pip install -r "$workspaceRoot\requirements-crawl4ai.txt"

Write-Host "Setting up Playwright browser runtime for Crawl4AI..."
& ".\.venv\Scripts\crawl4ai-setup.exe"

Write-Host "Running Crawl4AI doctor diagnostic check..."
& ".\.venv\Scripts\crawl4ai-doctor.exe"

Write-Host "Crawl4AI setup completed successfully."
