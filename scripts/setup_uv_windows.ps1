# AI ETF Trader - UV Setup Script for Windows
# This script automates the UV environment setup on Windows

param(
    [switch]$Force = $false,
    [switch]$Verbose = $false
)

# Color output
function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor Cyan
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor Yellow
}

# Get project root
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Info "AI ETF Trader - UV Setup"
Write-Info "Project Root: $ProjectRoot"
Write-Info ""

# Step 1: Check if UV is installed
Write-Info "Step 1: Checking UV installation..."
$uvVersion = uv --version 2>$null
if ($null -eq $uvVersion) {
    Write-WarningMsg "UV is not installed"
    Write-Info "Installing UV..."
    
    try {
        irm https://astral.sh/uv/install.ps1 | iex
        Write-Success "UV installed successfully"
        
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    catch {
        Write-ErrorMsg "Failed to install UV: $_"
        Write-Info "Please install UV manually from: https://astral.sh/uv/install.ps1"
        exit 1
    }
}
else {
    Write-Success "UV is installed: $uvVersion"
}

Write-Info ""

# Step 2: Check Python version
Write-Info "Step 2: Checking Python version..."
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "3\.11") {
    Write-Success "Python 3.11 is available: $pythonVersion"
}
else {
    Write-WarningMsg "Python 3.11 not found. Current: $pythonVersion"
    Write-Info "UV will use its default Python version"
}

Write-Info ""

# Step 3: Check if virtual environment exists
Write-Info "Step 3: Checking virtual environment..."
if ((Test-Path ".venv") -and -not $Force) {
    Write-WarningMsg "Virtual environment already exists"
    Write-Info "Use -Force flag to recreate"
}
else {
    if ($Force -and (Test-Path ".venv")) {
        Write-Info "Removing existing virtual environment..."
        Remove-Item -Recurse -Force ".venv"
        Write-Success "Virtual environment removed"
    }
    
    Write-Info "Creating virtual environment..."
    try {
        uv sync
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Virtual environment created successfully"
        }
        else {
            Write-ErrorMsg "Failed to create virtual environment"
            exit 1
        }
    }
    catch {
        Write-ErrorMsg "Error creating virtual environment: $_"
        exit 1
    }
}

Write-Info ""

# Step 4: Verify installation
Write-Info "Step 4: Verifying installation..."
try {
    $pythonPath = ".venv\Scripts\python.exe"
    if (Test-Path $pythonPath) {
        Write-Success "Python executable found: $pythonPath"
        
        # Check version
        $version = & $pythonPath --version 2>&1
        Write-Success "Python version: $version"
        
        # Check key dependencies
        Write-Info "Checking key dependencies..."
        $deps = @("flask", "pandas", "akshare", "schedule", "openai", "python-dotenv")
        
        foreach ($dep in $deps) {
            $check = & $pythonPath -c "import $dep; print('OK')" 2>&1
            if ($check -eq "OK") {
                Write-Success "$dep is installed"
            }
            else {
                Write-WarningMsg "$dep check failed"
            }
        }
    }
    else {
        Write-ErrorMsg "Python executable not found"
        exit 1
    }
}
catch {
    Write-ErrorMsg "Verification failed: $_"
    exit 1
}

Write-Info ""

# Step 5: Display next steps
Write-Info "Step 5: Next steps..."
Write-Info ""
Write-Success "Setup completed successfully!"
Write-Info ""
Write-Info "To activate the virtual environment, run:"
Write-Host "  .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Info ""
Write-Info "To start the web application, run:"
Write-Host "  uv run python -m src.web_app" -ForegroundColor Yellow
Write-Info ""
Write-Info "To run the daily task, run:"
Write-Host "  uv run python -m src.daily_once" -ForegroundColor Yellow
Write-Info ""
Write-Info "For more information, see:"
Write-Host "  - UV_QUICK_START.md" -ForegroundColor Yellow
Write-Host "  - UV_MIGRATION_GUIDE.md" -ForegroundColor Yellow
Write-Info ""

exit 0
