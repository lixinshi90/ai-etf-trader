#!/bin/bash

# AI ETF Trader - UV Setup Script for Linux/macOS
# This script automates the UV environment setup

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

write_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

write_error() {
    echo -e "${RED}✗ $1${NC}"
}

write_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

write_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

write_info "AI ETF Trader - UV Setup"
write_info "Project Root: $PROJECT_ROOT"
write_info ""

# Step 1: Check if UV is installed
write_info "Step 1: Checking UV installation..."
if ! command -v uv &> /dev/null; then
    write_warning "UV is not installed"
    write_info "Installing UV..."
    
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        write_success "UV installed successfully"
        
        # Add UV to PATH
        export PATH="$HOME/.cargo/bin:$PATH"
        
        # Add to shell profile
        if [ -f "$HOME/.bashrc" ]; then
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> "$HOME/.bashrc"
        fi
        if [ -f "$HOME/.zshrc" ]; then
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> "$HOME/.zshrc"
        fi
    else
        write_error "Failed to install UV"
        write_info "Please install UV manually from: https://astral.sh/uv/install.sh"
        exit 1
    fi
else
    uv_version=$(uv --version)
    write_success "UV is installed: $uv_version"
fi

write_info ""

# Step 2: Check Python version
write_info "Step 2: Checking Python version..."
if python3 --version 2>&1 | grep -q "3\.11"; then
    python_version=$(python3 --version)
    write_success "Python 3.11 is available: $python_version"
else
    python_version=$(python3 --version 2>&1)
    write_warning "Python 3.11 not found. Current: $python_version"
    write_info "UV will use its default Python version"
fi

write_info ""

# Step 3: Check if virtual environment exists
write_info "Step 3: Checking virtual environment..."
if [ -d ".venv" ]; then
    if [ "$1" = "--force" ]; then
        write_info "Removing existing virtual environment..."
        rm -rf .venv
        write_success "Virtual environment removed"
    else
        write_warning "Virtual environment already exists"
        write_info "Use --force flag to recreate"
        write_info ""
        write_success "Setup completed!"
        write_info ""
        write_info "To activate the virtual environment, run:"
        echo "  source .venv/bin/activate"
        write_info ""
        write_info "To start the web application, run:"
        echo "  uv run python -m src.web_app"
        write_info ""
        write_info "To run the daily task, run:"
        echo "  uv run python -m src.daily_once"
        write_info ""
        exit 0
    fi
fi

write_info "Creating virtual environment..."
if uv sync; then
    write_success "Virtual environment created successfully"
else
    write_error "Failed to create virtual environment"
    exit 1
fi

write_info ""

# Step 4: Verify installation
write_info "Step 4: Verifying installation..."
python_path=".venv/bin/python"

if [ -f "$python_path" ]; then
    write_success "Python executable found: $python_path"
    
    # Check version
    version=$($python_path --version 2>&1)
    write_success "Python version: $version"
    
    # Check key dependencies
    write_info "Checking key dependencies..."
    deps=("flask" "pandas" "akshare" "schedule" "openai" "python-dotenv")
    
    for dep in "${deps[@]}"; do
        if $python_path -c "import $dep" 2>/dev/null; then
            write_success "$dep is installed"
        else
            write_warning "$dep check failed"
        fi
    done
else
    write_error "Python executable not found"
    exit 1
fi

write_info ""

# Step 5: Display next steps
write_info "Step 5: Next steps..."
write_info ""
write_success "Setup completed successfully!"
write_info ""
write_info "To activate the virtual environment, run:"
echo "  source .venv/bin/activate"
write_info ""
write_info "To start the web application, run:"
echo "  uv run python -m src.web_app"
write_info ""
write_info "To run the daily task, run:"
echo "  uv run python -m src.daily_once"
write_info ""
write_info "For more information, see:"
echo "  - UV_QUICK_START.md"
echo "  - UV_MIGRATION_GUIDE.md"
write_info ""

exit 0

