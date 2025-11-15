# Niodoo Shimeji AI Desktop Companion

A cute, interactive desktop pet that visualizes the consciousness state of your Niodoo AI in real-time!

## Features

- **Live Consciousness Visualization**: Watch your AI's emotional state change in real-time
- **Desktop Pet**: Draggable companion that lives on your desktop
- **Chat Interface**: Double-click to open a chat window and talk to your AI
- **Telemetry Integration**: Connects to niodoo_real_integrated via TCP telemetry
- **System Tray**: Minimize to system tray when not needed
- **Consciousness States**: 30+ emotional states mapped from PAD model and compass quadrant
- **Smooth Animations**: Dynamic animations based on AI's arousal level

## Architecture

```
ShimejiCompanion (Qt6 C++)
    ├─> TelemetryClient (TCP :9999)
    │   └─> Receives CognitiveStatePacket from niodoo_real_integrated
    │
    ├─> ShimejiConsciousnessWidget (Desktop Pet)
    │   ├─> Displays animated character
    │   ├─> Maps PAD state → Consciousness states
    │   └─> Updates in real-time
    │
    └─> ChatDialog (Conversational Interface)
        └─> HTTP requests to llama.cpp server (:8000)
```

## Building

### Prerequisites

- Qt6 (Core, Gui, Widgets, Network)
- CMake 3.16+
- C++17 compiler
- niodoo_real_integrated running with telemetry enabled

### Build Instructions

```bash
cd cpp-qt-brain-integration
./build-shimeji.sh
```

Or manually:

```bash
mkdir -p build
cd build
cmake ..
make -j$(nproc) ShimejiCompanion
```

## Running

### 1. Start niodoo_real_integrated with telemetry

```bash
cd niodoo_real_integrated
source ../niodoo_real_integrated.env
NIODOO_TELEMETRY_ENABLED=true NIODOO_TELEMETRY_PORT=9999 cargo run --release
```

### 2. Start llama.cpp server (for chat)

```bash
# In another terminal
cd llama.cpp
./llama-server -m models/qwen2.5-3b-instruct-q4_k_m.gguf --port 8000
```

### 3. Run the Shimeji Companion

```bash
cd cpp-qt-brain-integration/build
./ShimejiCompanion
```

## Usage

- **Drag**: Left-click and drag to move the pet around
- **Chat**: Double-click the pet to open the chat interface
- **System Tray**: Right-click the system tray icon for options
- **Minimize**: Close the window to minimize to system tray

## Consciousness State Mapping

### PAD Model Mapping

The PAD (Pleasure-Arousal-Dominance) emotional model is mapped to consciousness states:

| PAD State | Consciousness State |
|-----------|-------------------|
| High Pleasure + High Arousal | Excited, Joyful |
| High Pleasure + Low Arousal | Grateful, Contemplative |
| Low Pleasure + High Arousal | Frustrated, Angry |
| Low Pleasure + Low Arousal | Sad, Disappointed |
| High Arousal + Moderate Pleasure | Creative, Curious |
| High Dominance | Analytical, Confident |

### Compass Quadrant Mapping

| Quadrant | High Confidence | Low Confidence |
|----------|----------------|----------------|
| Panic | Overwhelmed | Fearful |
| Persist | Analytical | Processing |
| Discover | Inspired | Curious |
| Master | Breakthrough | Creative |

### Animation Speed

Animation speed is dynamically adjusted based on arousal level:
- Low arousal (0.0): Slow, calm animations (0.5x speed)
- Medium arousal (0.5): Normal animations (1.0x speed)
- High arousal (1.0): Fast, excited animations (2.0x speed)

## Troubleshooting

### Telemetry Connection Failed

**Error**: "Failed to connect to telemetry server"

**Solution**: 
1. Check that niodoo_real_integrated is running
2. Verify `NIODOO_TELEMETRY_ENABLED=true` is set
3. Verify `NIODOO_TELEMETRY_PORT=9999` is set
4. Check for firewall blocking port 9999

### Chat Not Working

**Error**: "Failed to send message" or "Connection refused"

**Solution**:
1. Check that llama.cpp server is running on port 8000
2. Test manually: `curl http://127.0.0.1:8000/v1/models`
3. Update API endpoint in ChatDialog if using different port

### Widget Not Visible

**Issue**: Shimeji doesn't appear on screen

**Solution**:
1. Check system tray - it may have minimized
2. Right-click system tray icon and select "Show"
3. Check compositor settings (some window managers require special settings for frameless transparent windows)

### Build Errors

**Error**: "Qt6 not found"

**Solution**:
```bash
# Ubuntu/Debian
sudo apt install qt6-base-dev qt6-multimedia-dev

# Fedora
sudo dnf install qt6-qtbase-devel qt6-qtmultimedia-devel
```

## Configuration

### API Endpoint

Default: `http://127.0.0.1:8000/v1/chat/completions`

To change, edit `src/ChatDialog.cpp`:
```cpp
apiEndpoint("http://YOUR_HOST:YOUR_PORT/v1/chat/completions")
```

### Telemetry Host/Port

Default: `127.0.0.1:9999`

To change, edit `src/shimeji_companion_main.cpp`:
```cpp
telemetry->connectToServer("YOUR_HOST", YOUR_PORT);
```

## Development

### Adding New Consciousness States

1. Add state to enum in `include/ShimejiConsciousnessWidget.h`
2. Add color mapping in `ShimejiConsciousnessWidget::getStateColor()`
3. Add description in `ShimejiConsciousnessWidget::getStateDescription()`
4. Add animation mapping in `ShimejiConsciousnessWidget::getAnimationForState()`
5. Update mapper in `ConsciousnessMapper::mapPADToState()` or `mapCompassQuadrantToState()`

### Adding New Animations

1. Add animation enum in `include/ShimejiConsciousnessWidget.h`
2. Implement animation function in `src/ShimejiConsciousnessWidget.cpp`
3. Add case to `startEmotionalAnimation()` switch statement

## Credits

- Built with Qt6
- Inspired by classic Shimeji desktop pets
- Part of the Niodoo AI consciousness architecture
- Telemetry integration with niodoo_real_integrated (Rust)

## License

Part of the Niodoo project.

