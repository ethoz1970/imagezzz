#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================="
echo "Symphony AI Image Generator - Setup Script"
echo "=========================================="
echo ""

# 1. Check for Python 3
if ! command -v python3 &> /dev/null
then
    echo "[!] Python 3 could not be found. Please install Python 3 and try again."
    exit 1
fi
echo "[v] Python 3 is installed."

# 2. Check for Ollama
if ! command -v ollama &> /dev/null
then
    echo "[!] Ollama could not be found. Please install it from https://ollama.com/ and make sure the app is running."
    exit 1
fi
echo "[v] Ollama is installed."

# 3. Pull the required vision model from Ollama
echo ""
echo "=> Pulling the 'llama3.2-vision' model (this may take a few minutes)..."
# Note: the Ollama application must be running in the background for this to work
ollama pull llama3.2-vision

# 4. Set up Python virtual environment
echo ""
echo "=> Setting up the Python virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate the virtual environment
source .venv/bin/activate

# Optional: upgrade pip
echo "=> Upgrading pip..."
pip install --upgrade pip

# 5. Install Python dependencies
echo ""
echo "=> Installing Python dependencies for your OS..."
OS_NAME=$(uname -s)
if [ "$OS_NAME" = "Darwin" ]; then
    echo "   Detected Apple Silicon (macOS). Installing requirements-mac.txt..."
    pip install -r requirements-mac.txt
elif [ "$OS_NAME" = "Linux" ]; then
    echo "   Detected Linux. Installing requirements-linux.txt..."
    pip install -r requirements-linux.txt
else
    echo "   Unknown OS. Attempting to install Linux requirements..."
    pip install -r requirements-linux.txt
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To run the application, make sure the Ollama app is open in the background, then run:"
echo ""
echo "  source .venv/bin/activate"
if [ "$OS_NAME" = "Darwin" ]; then
    echo "  PYTORCH_ENABLE_MPS_FALLBACK=1 python3 server.py"
else
    echo "  python3 server.py"
fi
echo ""
