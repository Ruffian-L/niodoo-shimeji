# Installation Guide - Niodoo Shimeji AI Desktop Companion

## Prerequisites

### Required Dependencies

#### Qt6 Development Libraries

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y \
    qt6-base-dev \
    qt6-base-dev-tools \
    libqt6core6 \
    libqt6gui6 \
    libqt6widgets6 \
    libqt6network6 \
    cmake \
    build-essential \
    pkg-config
```

**Fedora/RHEL:**
```bash
sudo dnf install -y \
    qt6-qtbase-devel \
    qt6-qttools-devel \
    cmake \
    gcc-c++ \
    make
```

**Arch Linux:**
```bash
sudo pacman -S qt6-base qt6-tools cmake base-devel
```

**macOS (Homebrew):**
```bash
brew install qt@6 cmake
export CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@6:$CMAKE_PREFIX_PATH"
```

#### Verify Qt6 Installation

```bash
# Check if qmake is available
which qmake6 || which qmake

# Check Qt version
qmake6 --version || qmake --version

# Expected output should include Qt 6.x.x
```

### niodoo_real_integrated Setup

The companion requires a running instance of niodoo_real_integrated with telemetry enabled:

```bash
cd /workspace/Niodoo-Final/niodoo_real_integrated

# Source environment variables
source ../niodoo_real_integrated.env

# Enable telemetry
export NIODOO_TELEMETRY_ENABLED=true
export NIODOO_TELEMETRY_PORT=9999

# Build and run
cargo run --release
```

### llama.cpp Server Setup

For chat functionality, you need llama.cpp server running:

```bash
cd /workspace/Niodoo-Final/llama.cpp

# Start server with your model
./llama-server \
    -m /workspace/llama.cpp/models/qwen2.5-3b-instruct-q4_k_m.gguf \
    --port 8000 \
    --ctx-size 2048
```

## Building the Shimeji Companion

### Quick Build

```bash
cd /workspace/Niodoo-Final/cpp-qt-brain-integration
./build-shimeji.sh
```

### Manual Build

```bash
cd /workspace/Niodoo-Final/cpp-qt-brain-integration
mkdir -p build
cd build

# Configure with CMake
cmake ..

# Build
make -j$(nproc) ShimejiCompanion

# Or build everything
make -j$(nproc)
```

### Build Verification

```bash
# Check if executable was created
ls -lh build/ShimejiCompanion

# Check dependencies
ldd build/ShimejiCompanion

# Expected Qt libraries should be linked
```

## Running the Companion

### 1. Start Prerequisites

Terminal 1 - niodoo_real_integrated:
```bash
cd /workspace/Niodoo-Final/niodoo_real_integrated
source ../niodoo_real_integrated.env
export NIODOO_TELEMETRY_ENABLED=true
export NIODOO_TELEMETRY_PORT=9999
cargo run --release
```

Terminal 2 - llama.cpp server:
```bash
cd /workspace/Niodoo-Final/llama.cpp
./llama-server -m models/qwen2.5-3b-instruct-q4_k_m.gguf --port 8000
```

### 2. Start Shimeji Companion

Terminal 3:
```bash
cd /workspace/Niodoo-Final/cpp-qt-brain-integration/build
./ShimejiCompanion
```

## Troubleshooting

### Qt6 Not Found During Build

**Error:**
```
CMake Error: Could not find a package configuration file provided by "Qt6"
```

**Solution:**
1. Install Qt6 development packages (see above)
2. Set CMAKE_PREFIX_PATH:
```bash
export CMAKE_PREFIX_PATH="/usr/lib/x86_64-linux-gnu/cmake/Qt6:$CMAKE_PREFIX_PATH"
cmake ..
```

### Missing Qt6 Components

**Error:**
```
Could not find Qt6::Core, Qt6::Widgets, or Qt6::Network
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt install qt6-base-dev libqt6network6

# Find Qt6 installation
find /usr -name "Qt6Config.cmake" 2>/dev/null

# Set CMAKE_PREFIX_PATH to the directory containing Qt6Config.cmake
export CMAKE_PREFIX_PATH="/path/to/qt6"
```

### Compilation Errors

**Error:**
```
error: 'QWidget' does not name a type
```

**Solution:**
- Make sure all Qt6 headers are installed
- Check that Qt version is 6.2 or higher
- Verify MOC (Meta-Object Compiler) is running:
```bash
cmake .. -DCMAKE_AUTOMOC=ON
```

### Runtime: Telemetry Connection Failed

**Error in console:**
```
"Failed to connect to telemetry server"
```

**Solution:**
1. Verify niodoo_real_integrated is running
2. Check telemetry is enabled:
```bash
echo $NIODOO_TELEMETRY_ENABLED  # Should be "true"
echo $NIODOO_TELEMETRY_PORT     # Should be "9999"
```
3. Test connection manually:
```bash
nc -zv 127.0.0.1 9999
```
4. Check firewall:
```bash
sudo ufw allow 9999
```

### Runtime: Chat Not Working

**Error:**
```
"Failed to send message" or "Connection refused"
```

**Solution:**
1. Verify llama.cpp server is running:
```bash
curl http://127.0.0.1:8000/v1/models
```
2. Check server logs for errors
3. Verify model is loaded correctly

### Runtime: Widget Not Visible

**Issue:**
Desktop pet doesn't appear

**Solution:**
1. Check system tray - right-click tray icon and select "Show"
2. For Wayland compositors, you may need special permissions
3. Check Qt platform:
```bash
QT_DEBUG_PLUGINS=1 ./ShimejiCompanion
```

### Runtime: Transparent Window Issues

**Issue:**
Window is not transparent or shows artifacts

**Solution:**
1. Enable compositor (for X11):
```bash
# Check if compositor is running
ps aux | grep compton

# Or use picom
picom &
```
2. For KDE Plasma:
   - System Settings → Display and Monitor → Compositor → Enable
3. For GNOME:
   - Should work out of the box with Mutter

## Platform-Specific Notes

### Linux (X11)
- Should work out of the box with most window managers
- Requires compositor for transparency

### Linux (Wayland)
- May need `QT_QPA_PLATFORM=wayland` or `xcb`
- Some window managers may not support frameless windows

### macOS
- Requires Qt6 from Homebrew
- May need code signing for distribution

### Windows
- Not tested yet (but Qt6 is cross-platform)
- MinGW or MSVC build required

## Development Build

For development with debug symbols:

```bash
cd build
cmake -DCMAKE_BUILD_TYPE=Debug ..
make -j$(nproc) ShimejiCompanion

# Run with debugger
gdb ./ShimejiCompanion
```

## Next Steps

After successful installation:
1. Read `SHIMEJI_COMPANION_README.md` for usage guide
2. Check `CHANGELOG.md` for latest features
3. See `src/shimeji_companion_main.cpp` for integration examples

