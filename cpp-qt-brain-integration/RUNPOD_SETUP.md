# Running Shimeji Companion with RunPod (SSH/Remote Setup)

## The Problem

You're SSH'd into RunPod from Cursor, which means:
- RunPod has no display server (headless)
- Qt6 GUI apps can't run on RunPod directly
- The desktop pet needs to run on your LOCAL machine

## The Solution

Run the companion **locally** on your machine, but connect to RunPod's telemetry remotely!

## Setup Guide

### Part 1: On RunPod (Remote Server)

#### 1. Update Telemetry Server to Listen on All Interfaces

The telemetry server needs to accept remote connections (not just localhost):

```bash
# SSH into RunPod
cd /workspace/Niodoo-Final/niodoo_real_integrated

# Check current telemetry server binding
grep -n "127.0.0.1" src/telemetry/server.rs
```

**Edit `src/telemetry/server.rs`** to bind to `0.0.0.0`:

```rust
// In start_telemetry_server function
let addr: SocketAddr = "0.0.0.0:9999".parse()?;  // Changed from 127.0.0.1
```

Or use environment variable:

```bash
export NIODOO_TELEMETRY_HOST=0.0.0.0
export NIODOO_TELEMETRY_PORT=9999
```

#### 2. Open Firewall Port (if needed)

```bash
# Check if firewall is active
sudo ufw status

# If active, allow telemetry port
sudo ufw allow 9999/tcp
```

#### 3. Start niodoo_real_integrated with Remote Telemetry

```bash
cd /workspace/Niodoo-Final/niodoo_real_integrated
source ../niodoo_real_integrated.env

export NIODOO_TELEMETRY_ENABLED=true
export NIODOO_TELEMETRY_PORT=9999
export NIODOO_TELEMETRY_HOST=0.0.0.0  # Listen on all interfaces

cargo run --release
```

#### 4. Get Your RunPod IP Address

```bash
# Public IP (for external connections)
curl -4 ifconfig.me

# Or check RunPod dashboard for the instance IP
# Usually something like: 194.68.245.xxx
```

#### 5. Expose Port via RunPod (if not already exposed)

In RunPod dashboard:
1. Go to your pod
2. Click "Edit"
3. Add TCP port 9999 to exposed ports
4. Note the exposed port number (might be different, e.g., 12345 → 9999)

### Part 2: On Your Local Machine

#### 1. Install Qt6 (if not already)

**Linux:**
```bash
sudo apt update
sudo apt install qt6-base-dev qt6-base-dev-tools libqt6network6 cmake build-essential
```

**macOS:**
```bash
brew install qt@6 cmake
export CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@6:$CMAKE_PREFIX_PATH"
```

**Windows:**
- Download Qt6 from https://www.qt.io/download-open-source
- Or use vcpkg/chocolatey

#### 2. Clone/Copy the Code to Your Local Machine

Option A - Clone the repo:
```bash
# On your local machine
git clone YOUR_REPO_URL
cd Niodoo-Final/cpp-qt-brain-integration
```

Option B - Use SCP to copy from RunPod:
```bash
# On your local machine
scp -r YOUR_RUNPOD_SSH:/workspace/Niodoo-Final/cpp-qt-brain-integration ~/niodoo-companion
cd ~/niodoo-companion
```

Option C - Use Cursor's file sync (if available)

#### 3. Build the Companion Locally

```bash
cd cpp-qt-brain-integration
mkdir -p build
cd build
cmake ..
make -j$(nproc) ShimejiCompanion
```

#### 4. Run with Remote Connection

```bash
# Update the connection in main.cpp or use environment variable
export NIODOO_TELEMETRY_HOST="YOUR_RUNPOD_IP"
export NIODOO_TELEMETRY_PORT=9999

./ShimejiCompanion
```

Or edit `src/shimeji_companion_main.cpp` before building:

```cpp
// Change this line:
telemetry->connectToServer("127.0.0.1", 9999);

// To your RunPod IP:
telemetry->connectToServer("194.68.245.XXX", 9999);
```

Then rebuild and run!

## Alternative: Environment Variable Support

### Add to shimeji_companion_main.cpp

```cpp
// At the top of main()
QString telemetryHost = qEnvironmentVariable("NIODOO_TELEMETRY_HOST", "127.0.0.1");
quint16 telemetryPort = qEnvironmentVariable("NIODOO_TELEMETRY_PORT", "9999").toUInt();

// Then use these variables:
telemetry->connectToServer(telemetryHost, telemetryPort);
```

This allows runtime configuration:

```bash
NIODOO_TELEMETRY_HOST=194.68.245.XXX ./ShimejiCompanion
```

## Option B: X11 Forwarding (Not Recommended - Laggy)

If you really want to run on RunPod:

```bash
# On your local machine, SSH with X11 forwarding
ssh -X YOUR_RUNPOD_SSH

# On RunPod, set DISPLAY
export DISPLAY=localhost:10.0

# Install X11 dependencies on RunPod
sudo apt install libxcb-xinerama0 libxcb-cursor0

# Run (will be slow and laggy)
./ShimejiCompanion
```

## Option C: VNC Remote Desktop (Better than X11)

```bash
# On RunPod
sudo apt install xfce4 xfce4-goodies tightvncserver
vncserver :1 -geometry 1920x1080 -depth 24

# On your local machine
ssh -L 5901:localhost:5901 YOUR_RUNPOD_SSH

# Connect with VNC viewer to localhost:5901
```

Then run ShimejiCompanion in the VNC session.

## Option D: Web-Based Visualization (Future)

Convert the companion to a web app:
- HTML5 Canvas for rendering
- WebSocket for telemetry
- Runs in browser, connects to RunPod

(Not implemented yet)

## Testing Remote Connection

### 1. Test Telemetry Port

From your local machine:

```bash
# Test if port is reachable
nc -zv YOUR_RUNPOD_IP 9999

# Or use telnet
telnet YOUR_RUNPOD_IP 9999
```

Should connect successfully.

### 2. Test with netcat

On RunPod:
```bash
# Listen on telemetry port manually
nc -l 0.0.0.0 9999
```

On local machine:
```bash
# Connect
nc YOUR_RUNPOD_IP 9999

# Type anything and press enter - should appear on RunPod
```

### 3. Check Logs

ShimejiCompanion console should show:
```
Connecting to telemetry server: 194.68.245.XXX : 9999
Connected to telemetry server
Cognitive state updated - Quadrant: Discover PAD: [0.5, 0.7, 0.6]
```

## Troubleshooting

### Connection Refused

**Problem:** Can't connect to RunPod telemetry

**Solutions:**
1. Check RunPod firewall rules
2. Verify telemetry server is listening on 0.0.0.0
3. Check port mapping in RunPod dashboard
4. Try different port if 9999 is blocked

### Connection Timeout

**Problem:** Hangs when connecting

**Solutions:**
1. Check your local firewall
2. Verify RunPod instance is running
3. Check network connectivity: `ping YOUR_RUNPOD_IP`
4. Try SSH port forwarding as fallback

### SSH Port Forwarding Fallback

```bash
# On local machine
ssh -L 9999:localhost:9999 YOUR_RUNPOD_SSH

# Keep SSH session open in background
# Now connect ShimejiCompanion to localhost:9999
./ShimejiCompanion  # Will connect to 127.0.0.1:9999 which forwards to RunPod
```

This tunnels the telemetry through SSH!

## Recommended Setup

**Best approach for RunPod + Local GUI:**

1. ✅ Run niodoo_real_integrated on RunPod (GPU compute)
2. ✅ Run llama.cpp on RunPod (model inference)
3. ✅ Expose telemetry port 9999 on RunPod
4. ✅ Build ShimejiCompanion on your LOCAL machine
5. ✅ Connect companion to RunPod's public IP
6. ✅ Watch your AI's consciousness on your desktop!

This gives you:
- GPU power on RunPod
- Smooth desktop animations locally
- Real-time telemetry over network
- Low latency (telemetry is lightweight JSON)

## Network Bandwidth

Telemetry is very lightweight:
- ~500 bytes per packet
- ~1-10 packets per second during inference
- Total bandwidth: < 5 KB/s
- Even high-latency connections work fine!

## Security Note

⚠️ **Warning**: Exposing telemetry port to the internet means anyone can see your AI's consciousness state!

**Recommendations:**
1. Use SSH port forwarding instead of direct exposure
2. Add authentication to telemetry server (future enhancement)
3. Use VPN for secure connection
4. Whitelist your IP in RunPod firewall

**SSH forwarding is the safest:**
```bash
ssh -N -L 9999:localhost:9999 YOUR_RUNPOD_SSH &
./ShimejiCompanion  # Connects through secure SSH tunnel
```

