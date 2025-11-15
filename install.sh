#!/usr/bin/env bash
set -euo pipefail

# niodoo-shimeji Installation Script
# Installs niodoo-shimeji project, Shijima-Qt, and configures environment

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIJIMA_QT_REPO="https://github.com/pixelomer/Shijima-Qt.git"
SHIJIMA_QT_DIR="${ROOT_DIR}/Shijima-Qt"
BASH_RC="${HOME}/.bashrc"

echo "=========================================="
echo "niodoo-shimeji Installation Script"
echo "=========================================="
echo ""

# Check if running as root (we shouldn't need root for most things)
if [[ $EUID -eq 0 ]]; then
   echo "Warning: Running as root. This script should be run as a regular user." >&2
   read -p "Continue anyway? (y/N) " -n 1 -r
   echo
   if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      exit 1
   fi
fi

# Step 1: Install system dependencies
echo "[1/7] Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        git \
        build-essential \
        cmake \
        qt6-base-dev \
        qt6-base-dev-tools \
        qt6-multimedia-dev \
        libqt6network6 \
        libxcb-cursor0 \
        libarchive-dev \
        python3 \
        python3-venv \
        python3-pip \
        python3-systemd \
        xclip \
        wl-clipboard \
        gnome-screenshot \
        scrot \
        pydbus \
        || echo "Warning: Some packages may have failed to install"
elif command -v dnf &> /dev/null; then
    sudo dnf install -y \
        git \
        gcc-c++ \
        cmake \
        qt6-qtbase-devel \
        qt6-qtmultimedia-devel \
        qt6-qtnetwork \
        libxcb-cursor \
        libarchive-devel \
        python3 \
        python3-pip \
        python3-systemd \
        xclip \
        wl-clipboard \
        gnome-screenshot \
        scrot \
        python3-pydbus \
        || echo "Warning: Some packages may have failed to install"
elif command -v pacman &> /dev/null; then
    sudo pacman -S --noconfirm \
        git \
        base-devel \
        cmake \
        qt6-base \
        qt6-multimedia \
        qt6-network \
        libxcb \
        libarchive \
        python \
        python-pip \
        python-systemd \
        xclip \
        wl-clipboard \
        gnome-screenshot \
        scrot \
        python-pydbus \
        || echo "Warning: Some packages may have failed to install"
else
    echo "Warning: Unsupported package manager. Please install dependencies manually:"
    echo "  - git, build-essential/cmake, Qt6 dev packages"
    echo "  - python3, python3-venv, python3-pip, python3-systemd"
    echo "  - xclip, wl-clipboard, gnome-screenshot, scrot"
    echo "  - pydbus"
fi
echo ""

# Step 2: Clone or update Shijima-Qt
echo "[2/7] Setting up Shijima-Qt..."
if [[ -d "${SHIJIMA_QT_DIR}" ]]; then
    echo "  Shijima-Qt directory exists, pulling latest from git..."
    cd "${SHIJIMA_QT_DIR}"
    if [[ -d .git ]]; then
        echo "  Fetching latest changes..."
        git fetch origin || echo "Warning: git fetch failed"
        echo "  Pulling latest code..."
        git pull --rebase origin main || git pull --rebase origin master || echo "Warning: git pull failed, continuing with existing code"
        echo "  Updating submodules..."
        git submodule update --init --recursive || echo "Warning: submodule update failed"
    else
        echo "  Warning: ${SHIJIMA_QT_DIR} exists but is not a git repository"
        echo "  Removing and re-cloning..."
        cd "${ROOT_DIR}"
        rm -rf "${SHIJIMA_QT_DIR}"
        echo "  Cloning latest Shijima-Qt from ${SHIJIMA_QT_REPO}..."
        git clone --recursive "${SHIJIMA_QT_REPO}" "${SHIJIMA_QT_DIR}"
    fi
else
    echo "  Cloning latest Shijima-Qt from ${SHIJIMA_QT_REPO}..."
    git clone --recursive "${SHIJIMA_QT_REPO}" "${SHIJIMA_QT_DIR}"
fi
echo ""

# Step 3: Build Shijima-Qt
echo "[3/7] Building Shijima-Qt..."
cd "${SHIJIMA_QT_DIR}"
if [[ -f Makefile ]]; then
    echo "  Cleaning previous build..."
    make clean || true
fi

echo "  Running qmake..."
if command -v qmake6 &> /dev/null; then
    qmake6 || qmake
elif command -v qmake &> /dev/null; then
    qmake
else
    echo "  Error: qmake not found. Please install Qt6 development packages."
    exit 1
fi

echo "  Compiling (this may take a few minutes)..."
make -j$(nproc) || {
    echo "  Warning: Build failed. Trying with single core..."
    make
}
echo ""

# Verify binary exists
if [[ ! -f "${SHIJIMA_QT_DIR}/shijima-qt" ]]; then
    echo "  Error: shijima-qt binary not found after build!"
    exit 1
fi
echo "  ✓ Shijima-Qt built successfully"
echo ""

# Step 4: Set up Python virtual environment
echo "[4/7] Setting up Python virtual environment..."
VENV_DIR="${ROOT_DIR}/shimeji_venv"
if [[ -d "${VENV_DIR}" ]]; then
    echo "  Virtual environment already exists, skipping creation..."
else
    echo "  Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi

echo "  Activating virtual environment and installing Python packages..."
source "${VENV_DIR}/bin/activate"

# Install Python dependencies
pip install --upgrade pip setuptools wheel
pip install \
    google-generativeai \
    requests \
    PySide6 \
    pydbus \
    watchdog \
    psutil \
    || echo "Warning: Some Python packages may have failed to install"

# Install optional dependencies for enhanced monitoring
echo "  Installing optional monitoring dependencies..."
# Note: nvidia-ml-py is optional - GPU monitoring requires NVIDIA GPU
pip install \
    nvidia-ml-py \
    || echo "  Note: nvidia-ml-py not available (GPU monitoring disabled - install manually if needed)"

# Install comprehensive enhancement dependencies
echo "  Installing comprehensive enhancement dependencies..."
pip install \
    vosk \
    pyaudio \
    pyttsx3 \
    scikit-learn \
    schedule \
    numpy \
    pandas \
    sentence-transformers \
    sqlcipher3 \
    Pillow \
    || echo "  Warning: Some enhancement packages may have failed to install"

echo "  ✓ Python environment ready"
echo ""

# Step 5: Configure bashrc with QT_QPA_PLATFORM
echo "[5/7] Configuring bash environment..."
if ! grep -q "QT_QPA_PLATFORM=xcb" "${BASH_RC}" 2>/dev/null; then
    echo "" >> "${BASH_RC}"
    echo "# niodoo-shimeji: Set Qt platform to xcb" >> "${BASH_RC}"
    echo "export QT_QPA_PLATFORM=xcb" >> "${BASH_RC}"
    echo "  ✓ Added QT_QPA_PLATFORM=xcb to ${BASH_RC}"
else
    echo "  ✓ QT_QPA_PLATFORM=xcb already configured in ${BASH_RC}"
fi

# Add alias/function for killing shimeji agent
if ! grep -q "# niodoo-shimeji: Kill shimeji agent" "${BASH_RC}" 2>/dev/null; then
    echo "" >> "${BASH_RC}"
    echo "# niodoo-shimeji: Kill shimeji agent" >> "${BASH_RC}"
    echo "alias kill-shimeji='pkill -f shimeji_dual_mode_agent.py'" >> "${BASH_RC}"
    echo "  ✓ Added kill-shimeji alias to ${BASH_RC}"
else
    echo "  ✓ kill-shimeji alias already configured in ${BASH_RC}"
fi

# Add alias for running shim
if ! grep -q "# niodoo-shimeji: Run shim command" "${BASH_RC}" 2>/dev/null; then
    echo "" >> "${BASH_RC}"
    echo "# niodoo-shimeji: Run shim command" >> "${BASH_RC}"
    echo "alias shim='${ROOT_DIR}/shim'" >> "${BASH_RC}"
    echo "  ✓ Added shim alias to ${BASH_RC}"
else
    echo "  ✓ shim alias already configured in ${BASH_RC}"
fi
echo ""

# Step 6: Make shim script executable
echo "[6/7] Setting up shim script..."
if [[ -f "${ROOT_DIR}/shim" ]]; then
    chmod +x "${ROOT_DIR}/shim"
    echo "  ✓ shim script is now executable"
else
    echo "  Warning: shim script not found at ${ROOT_DIR}/shim"
fi
echo ""

# Step 7: Verify installation
echo "[7/7] Verifying installation..."
ERRORS=0

# Check Shijima-Qt binary
if [[ -x "${SHIJIMA_QT_DIR}/shijima-qt" ]]; then
    echo "  ✓ Shijima-Qt binary found and executable"
else
    echo "  ✗ Shijima-Qt binary missing or not executable"
    ERRORS=$((ERRORS + 1))
fi

# Check Python venv
if [[ -f "${VENV_DIR}/bin/python" ]]; then
    echo "  ✓ Python virtual environment ready"
else
    echo "  ✗ Python virtual environment not found"
    ERRORS=$((ERRORS + 1))
fi

# Check shim script
if [[ -x "${ROOT_DIR}/shim" ]]; then
    echo "  ✓ shim script is executable"
else
    echo "  ✗ shim script not found or not executable"
    ERRORS=$((ERRORS + 1))
fi

# Check shimeji.env
if [[ -f "${ROOT_DIR}/shimeji.env" ]]; then
    echo "  ✓ shimeji.env configuration file found"
    if ! grep -q "GEMINI_API_KEY=" "${ROOT_DIR}/shimeji.env" 2>/dev/null || \
       grep -q "GEMINI_API_KEY=your_api_key_here" "${ROOT_DIR}/shimeji.env" 2>/dev/null; then
        echo "  ⚠ Warning: GEMINI_API_KEY may not be configured in shimeji.env"
    fi
else
    if [[ -f "${ROOT_DIR}/shimeji.env.example" ]]; then
        echo "  Creating shimeji.env from example..."
        cp "${ROOT_DIR}/shimeji.env.example" "${ROOT_DIR}/shimeji.env"
        echo "  ✓ shimeji.env created from example"
        echo "  ⚠ Warning: Please configure GEMINI_API_KEY in shimeji.env"
    else
        echo "  ⚠ Warning: shimeji.env not found and no example file available"
    fi
fi

echo ""

# Final summary
if [[ $ERRORS -eq 0 ]]; then
    echo "=========================================="
    echo "Installation completed successfully! ✓"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Source your bashrc or restart terminal:"
    echo "     source ~/.bashrc"
    echo ""
    echo "  2. Configure your Gemini API key:"
    echo "     nano ${ROOT_DIR}/shimeji.env"
    echo "     # Set GEMINI_API_KEY=your_actual_api_key"
    echo "     # Get a free key at: https://makersuite.google.com/app/apikey"
    echo ""
    echo "  3. Run the agent:"
    echo "     shim"
    echo "     # or"
    echo "     ${ROOT_DIR}/shim"
    echo ""
    echo "  4. To stop the agent:"
    echo "     kill-shimeji"
    echo "     # or"
    echo "     pkill -f shimeji_dual_mode_agent.py"
    echo ""
else
    echo "=========================================="
    echo "Installation completed with $ERRORS error(s) ⚠"
    echo "=========================================="
    echo ""
    echo "Please review the errors above and fix them manually."
    exit 1
fi

