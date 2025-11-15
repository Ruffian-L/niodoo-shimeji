# Test Plan - Niodoo Shimeji AI Desktop Companion

## Pre-Integration Tests

### Test 1: Build Verification
**Objective**: Verify all components compile without errors

```bash
cd /workspace/Niodoo-Final/cpp-qt-brain-integration
rm -rf build
./build-shimeji.sh
```

**Expected Result:**
- ✅ CMake configuration completes
- ✅ All source files compile without errors
- ✅ `ShimejiCompanion` executable created in `build/` directory
- ✅ File size > 1MB (indicates proper linking)

**Validation:**
```bash
ls -lh build/ShimejiCompanion
file build/ShimejiCompanion
ldd build/ShimejiCompanion | grep Qt6
```

### Test 2: Dependency Check
**Objective**: Verify all Qt6 libraries are properly linked

```bash
ldd build/ShimejiCompanion
```

**Expected Libraries:**
- ✅ libQt6Core.so
- ✅ libQt6Gui.so
- ✅ libQt6Widgets.so
- ✅ libQt6Network.so

### Test 3: Basic Execution
**Objective**: Verify executable runs without crashing

```bash
cd build
./ShimejiCompanion &
SHIMEJI_PID=$!
sleep 5
ps -p $SHIMEJI_PID
kill $SHIMEJI_PID
```

**Expected Result:**
- ✅ Process starts
- ✅ No immediate segfault
- ✅ Process can be gracefully terminated

## Integration Tests

### Test 4: Telemetry Client Connection
**Objective**: Verify TelemetryClient connects to telemetry server

**Setup:**
```bash
# Terminal 1: Start niodoo_real_integrated with telemetry
cd /workspace/Niodoo-Final/niodoo_real_integrated
source ../niodoo_real_integrated.env
export NIODOO_TELEMETRY_ENABLED=true
export NIODOO_TELEMETRY_PORT=9999
cargo run --release
```

**Test:**
```bash
# Terminal 2: Run ShimejiCompanion
cd /workspace/Niodoo-Final/cpp-qt-brain-integration/build
./ShimejiCompanion 2>&1 | tee shimeji_test.log
```

**Expected Console Output:**
```
TelemetryClient initialized
Connecting to telemetry server: 127.0.0.1 : 9999
Connected to telemetry server
```

**Validation:**
```bash
# Check connection established
grep "Connected to telemetry server" shimeji_test.log
```

### Test 5: Cognitive State Reception
**Objective**: Verify telemetry packets are received and parsed

**Test:**
Run a generation cycle in niodoo_real_integrated to trigger telemetry broadcast

**Expected Console Output:**
```
Cognitive state updated - Quadrant: Discover PAD: [0.5, 0.7, 0.6] Iteration: 1
PAD State: 0.5 0.7 0.6
Compass Quadrant: "Discover" Confidence: 0.85
```

**Validation:**
```bash
# Check for PAD state updates
grep "PAD State:" shimeji_test.log | wc -l  # Should be > 0

# Check for compass quadrant updates
grep "Compass Quadrant:" shimeji_test.log | wc -l  # Should be > 0
```

### Test 6: Consciousness State Mapping
**Objective**: Verify PAD states map to correct consciousness states

**Test Cases:**

| PAD Input | Expected State |
|-----------|---------------|
| [0.8, 0.8, 0.7] | Excited |
| [0.7, 0.5, 0.6] | Joyful |
| [-0.5, 0.8, 0.3] | Fearful |
| [-0.6, 0.3, 0.2] | Sad |
| [0.3, 0.7, 0.7] | Analytical |

**Validation:**
Check console output for consciousness state changes matching input PAD values

### Test 7: Animation Updates
**Objective**: Verify widget updates animations based on consciousness state

**Test:**
1. Observe widget while telemetry is active
2. Trigger different emotional states in niodoo_real_integrated
3. Verify visual changes

**Expected Behavior:**
- ✅ Widget color changes based on emotional state
- ✅ Animation speed increases with higher arousal
- ✅ Facial expression changes (eyes, mouth)
- ✅ Smooth transitions between states

### Test 8: Chat Dialog Integration
**Objective**: Verify chat interface can communicate with AI

**Setup:**
```bash
# Terminal 1: Start llama.cpp server
cd /workspace/Niodoo-Final/llama.cpp
./llama-server -m models/qwen2.5-3b-instruct-q4_k_m.gguf --port 8000
```

**Test:**
1. Double-click Shimeji widget
2. Chat dialog should appear
3. Type "Hello, how are you?"
4. Press Send or Enter

**Expected Result:**
- ✅ Chat dialog opens
- ✅ Message appears in chat history
- ✅ "AI is thinking..." message appears
- ✅ AI response received and displayed
- ✅ Timestamps shown for all messages

**Validation:**
```bash
# Check network requests in console
grep "Sending message to API:" shimeji_test.log
grep "Received response:" shimeji_test.log
```

### Test 9: System Tray Integration
**Objective**: Verify system tray icon functionality

**Test:**
1. Right-click system tray icon
2. Verify menu appears with:
   - Show
   - Hide
   - Quit
3. Test each option

**Expected Behavior:**
- ✅ Tray icon visible in system tray
- ✅ "Show" makes widget visible
- ✅ "Hide" hides widget (still in tray)
- ✅ "Quit" closes application
- ✅ Double-click tray icon toggles visibility

### Test 10: Widget Dragging
**Objective**: Verify widget can be dragged around screen

**Test:**
1. Left-click and hold on widget
2. Drag to different screen positions
3. Release mouse button
4. Verify widget stays in new position

**Expected Behavior:**
- ✅ Widget follows mouse while dragging
- ✅ Widget position updates smoothly
- ✅ Widget stays within screen bounds
- ✅ No flickering or artifacts

## Stress Tests

### Test 11: Rapid State Changes
**Objective**: Verify widget handles rapid telemetry updates

**Test:**
Run high-frequency generation cycles in niodoo_real_integrated

**Expected Behavior:**
- ✅ No crashes
- ✅ No memory leaks
- ✅ Smooth animation transitions
- ✅ CPU usage reasonable (<20% of one core)

**Validation:**
```bash
# Monitor resource usage
top -p $(pgrep ShimejiCompanion)

# Check for memory leaks
valgrind --leak-check=full ./ShimejiCompanion
```

### Test 12: Connection Loss Recovery
**Objective**: Verify graceful handling of telemetry disconnection

**Test:**
1. Start ShimejiCompanion with telemetry connected
2. Stop niodoo_real_integrated
3. Observe widget behavior
4. Restart niodoo_real_integrated
5. Verify reconnection

**Expected Behavior:**
- ✅ Widget shows "Sad" state on disconnection
- ✅ Console shows "Disconnected from telemetry server"
- ✅ Console shows "Attempting to reconnect..."
- ✅ Widget shows "Joyful" state on reconnection
- ✅ Telemetry data resumes flowing

### Test 13: Long-Running Stability
**Objective**: Verify application stability over extended period

**Test:**
```bash
# Run for 1 hour
./ShimejiCompanion &
SHIMEJI_PID=$!
sleep 3600
ps -p $SHIMEJI_PID  # Should still be running
kill $SHIMEJI_PID
```

**Monitor:**
- Memory usage (should remain stable)
- CPU usage (should remain low when idle)
- No crash logs

## User Acceptance Tests

### Test 14: End-to-End Workflow
**Objective**: Complete workflow from user perspective

**Scenario:**
1. User starts all services
2. Shimeji appears on desktop
3. User drags pet to corner of screen
4. AI processes something (consciousness state changes)
5. Pet shows excitement (color changes, animation speeds up)
6. User double-clicks pet
7. Chat opens
8. User asks "What are you thinking about?"
9. AI responds with thoughtful answer
10. User closes chat
11. Pet continues animating based on AI state

**Success Criteria:**
- ✅ All steps complete without errors
- ✅ Visual feedback is clear and responsive
- ✅ Chat interaction feels natural
- ✅ No unexpected crashes or freezes

## Regression Tests

### Test 15: After Code Changes
**Checklist:**
- [ ] Build completes without warnings
- [ ] All unit tests pass (if implemented)
- [ ] Telemetry connection still works
- [ ] Chat still sends/receives messages
- [ ] Consciousness state mapping unchanged (or intentionally changed)
- [ ] No new memory leaks
- [ ] Performance hasn't degraded

## Test Results Template

```markdown
## Test Session: [DATE]

### Environment
- OS: [e.g., Ubuntu 24.04]
- Qt Version: [e.g., 6.5.0]
- Compiler: [e.g., GCC 13.3.0]
- niodoo_real_integrated: [git commit hash]

### Test Results
| Test ID | Test Name | Status | Notes |
|---------|-----------|--------|-------|
| Test 1  | Build Verification | ✅ PASS | |
| Test 2  | Dependency Check | ✅ PASS | |
| Test 3  | Basic Execution | ✅ PASS | |
| Test 4  | Telemetry Connection | ✅ PASS | |
| Test 5  | State Reception | ✅ PASS | |
| Test 6  | State Mapping | ✅ PASS | |
| Test 7  | Animations | ✅ PASS | |
| Test 8  | Chat Integration | ✅ PASS | |
| Test 9  | System Tray | ✅ PASS | |
| Test 10 | Widget Dragging | ✅ PASS | |
| Test 11 | Rapid Changes | ✅ PASS | |
| Test 12 | Reconnection | ✅ PASS | |
| Test 13 | Long-Running | ✅ PASS | |
| Test 14 | End-to-End | ✅ PASS | |

### Issues Found
[List any issues discovered during testing]

### Performance Metrics
- Memory usage (idle): [e.g., 45 MB]
- Memory usage (active): [e.g., 60 MB]
- CPU usage (idle): [e.g., <1%]
- CPU usage (active): [e.g., 5-8%]
- Startup time: [e.g., 2.3 seconds]

### Conclusion
[Overall assessment of test session]
```

## Automated Testing Script

```bash
#!/bin/bash
# automated_test.sh - Run basic integration tests

echo "=== Shimeji Companion Automated Tests ==="

# Test 1: Build
echo "Test 1: Building..."
cd /workspace/Niodoo-Final/cpp-qt-brain-integration
rm -rf build
./build-shimeji.sh > /dev/null 2>&1
if [ -f "build/ShimejiCompanion" ]; then
    echo "✅ Build successful"
else
    echo "❌ Build failed"
    exit 1
fi

# Test 2: Dependencies
echo "Test 2: Checking dependencies..."
if ldd build/ShimejiCompanion | grep -q "Qt6"; then
    echo "✅ Qt6 libraries linked"
else
    echo "❌ Qt6 libraries not found"
    exit 1
fi

# Test 3: Execution
echo "Test 3: Testing execution..."
timeout 5 ./build/ShimejiCompanion > /dev/null 2>&1 &
PID=$!
sleep 2
if ps -p $PID > /dev/null; then
    echo "✅ Process started successfully"
    kill $PID 2>/dev/null
else
    echo "❌ Process failed to start"
    exit 1
fi

echo ""
echo "=== All automated tests passed! ==="
echo "Run manual tests for full validation"
```

