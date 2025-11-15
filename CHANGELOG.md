# Changelog

## 2025-01-15

### Repository Cleanup - Removed Legacy Code and Development Documents

- **Removed development artifacts**: Deleted temporary markdown files that were cluttering the repository:
  - `CODE_REVIEW.md` - Code review document (development artifact, no longer needed)
  - `ENHANCEMENT_REVIEW.md` - Enhancement review document (development artifact, no longer needed)
  - `RENAME_GUIDE.md` - Folder rename guide (temporary documentation, no longer needed)
  - `cpp-qt-brain-integration/IMPLEMENTATION_SUMMARY.md` - Implementation summary (historical documentation, no longer needed)
  - `cpp-qt-brain-integration/TEST_PLAN.md` - Test plan document (outdated, no longer needed)
- **Removed legacy Python files**: Deleted old agent implementations replaced by `shimeji_dual_mode_agent.py`:
  - `gemini_shimeji_agent.py` (295 lines) - Old single-mode agent, replaced by dual-mode agent
  - `niodoo_shimeji_bridge.py` (225 lines) - Old bridge, functionality integrated into dual-mode agent
- **Removed legacy C++ code**: Deleted unused BrainIntegration application and related components:
  - `cpp-qt-brain-integration/src/main.cpp` - Old BrainIntegration entry point
  - `cpp-qt-brain-integration/src/MainWindow.cpp` - Unused main window
  - `cpp-qt-brain-integration/src/EmotionalAIManager.cpp` - Unused emotional AI manager
  - `cpp-qt-brain-integration/src/BrainSystemBridge.cpp` - Unused brain system bridge
  - `cpp-qt-brain-integration/src/NeuralNetworkEngine.cpp` - Unused neural network engine
  - `cpp-qt-brain-integration/src/NiodoPerformanceOptimizer.cpp` - Unused performance optimizer
  - `cpp-qt-brain-integration/src/RustBrainBridge.cpp` - Unused Rust bridge
  - All corresponding header files (MainWindow.h, EmotionalAIManager.h, BrainSystemBridge.h, NeuralNetworkEngine.h, NiodoPerformanceOptimizer.h, RustBrainBridge.h)
- **Updated CMakeLists.txt**: Removed BrainIntegration executable build configuration, removed ONNX Runtime dependencies (not used by ShimejiCompanion), simplified to only build ShimejiCompanion
- **Fixed README.md**: Removed references to deleted CODE_REVIEW.md and ENHANCEMENT_REVIEW.md files
- **Professional repository**: Repository now contains only production code and documentation (README, CHANGELOG, LICENSE) and essential subproject documentation
- **Cleaner structure**: Removed ~1000+ lines of legacy code and documentation to make repository more professional and ready for git commit/push

## 2025-01-15

### Fixed Duplicate Message Spam

- **Single candidate processing**: Only process the first candidate from Gemini responses to prevent duplicate messages
- **Sentence deduplication**: Added smart deduplication to remove exact duplicate sentences from responses
- **Better text combining**: Improved logic for combining multiple text parts from Gemini into a single coherent message
- **No more spam**: Fixed issue where "Got it. I've read the document..." and other messages were appearing twice

### Improved Helpfulness for Real Questions

- **Updated CLI brain prompt**: Modified system instruction to prioritize helpfulness over personality when users ask real questions
- **Context-aware personality**: 
  - Casual chat: Can still be playful and slightly tsundere
  - Real questions/technical help: Direct, clear, and helpful - minimal teasing
- **User-focused**: When people need actual help, Gemini now focuses on being useful rather than cute
- **Clear instructions**: Explicitly tells Gemini to minimize tsundere/playfulness when providing real assistance
- **Better UX**: Users get answers without annoying personality getting in the way

### Fixed Function Calling Response Format Error

- **Fixed `'str' object has no attribute 'items'` error**: Gemini API expects function response to be a structured value (dict), not a plain string
- **Proper response format**: Function responses are now wrapped in `{"result": response_string}` structure
- **Function chaining now works**: Fixed the error that was preventing function call chaining from working properly

### Drag-and-Drop File Analysis (Enhanced for Long Documents)

- **Drag-and-drop support**: Chat window now accepts file drops for analysis
- **Image analysis**: Drop images (PNG, JPG, GIF, etc.) and Gemini will analyze them using Vision API
- **PDF support**: Drop PDF files and Gemini will extract text and analyze the document (requires PyPDF2 or pdfplumber)
- **Text file support**: Drop markdown, code files, text files, and more - Gemini will read and analyze them
- **Supported formats**: Images (all formats), PDFs, Markdown (.md), code files (.py, .js, .ts, .html, .css, etc.), text files (.txt), config files (.json, .yaml, .xml), and more
- **Automatic file type detection**: Uses MIME types and file extensions to determine how to handle each file
- **User feedback**: Shows file name when dropped and analysis results in chat
- **Long document support**: Increased content limit from 10k to 100k characters for analyzing very long documents
- **Increased token limit**: Set `max_output_tokens` to 8192 so Gemini can provide comprehensive analysis of long documents
- **Better prompts**: File analysis prompts now explicitly ask for "thorough" and "comprehensive" analysis

### Reduced Chat Spam & Fixed Duplicate Greetings

- **Removed automatic clipboard reading**: Proactive brain no longer has `read_clipboard` tool - users must manually request it
- **Added clipboard button (📋)**: New button in chat UI that reads clipboard and asks Gemini about it
- **Reduced chat spam**: Proactive dialogue messages now only show in speech bubbles, NOT in chat panel (except initial greeting)
- **Fixed duplicate greeting**: Greeting flag is now set before dispatching to prevent duplicates
- **Less verbose proactive brain**: Updated instructions to keep dialogue SHORT and INFREQUENT - "Be quiet most of the time"

### Enhanced Function Calling with Chaining Support (Real Gemini CLI-style)

- **Multi-step function calling loop**: CLI brain now implements proper function calling chaining like the real Gemini CLI
- **Automatic iteration loop**: Up to 10 function calls can be chained in sequence - Gemini calls function → sees result → calls next function → etc.
- **Proper function response format**: Function execution results are properly formatted and added to conversation history in the correct Gemini API format
- **Function result feedback**: Each function call's output is fed back into the conversation so Gemini can see results and make decisions for the next call
- **Improved execute_bash description**: Made it crystal clear that commands WILL BE EXECUTED - "This ACTUALLY RUNS the command - use it to delete files, edit configs, run scripts, etc."
- **Real tool chaining examples**: Gemini can now do: `ls ~/Desktop/*prime*.py` → see file exists → `rm ~/Desktop/prime_counter.py` → verify deleted, all in one turn
- **Better command execution**: When user confirms a delete/edit operation, Gemini will actually execute it instead of just describing what it would do
- **Debug logging**: Added logging to track function call chaining iterations and help debug issues

### Fixed Battery Status Detection

- **Auto-detect battery device**: Now automatically finds the correct battery device instead of hardcoding BAT0
- **Smart device selection**: Tries all battery devices and uses the one with `power supply: yes` (real battery)
- **Skip invalid batteries**: Ignores devices that show "should be ignored" or have `power supply: no`
- **Calculate from energy**: If percentage line is missing, calculates percentage from energy/energy-full values
- **Fallback to /sys**: Falls back to reading `/sys/class/power_supply/BAT*/capacity` if upower fails
- **Fixed 0% bug**: No longer shows 0% from invalid battery devices (like BAT0 when BAT1 is the real battery)

### Allow Sensitive Commands with Warnings

- **Updated command execution rules**: Gemini can now run sensitive commands (like editing SSH config, system files, etc.) but must warn first
- **Warning and confirmation flow**: 
  - For sensitive commands: Gemini warns user about what it will do
  - Asks for confirmation (user says "proceed", "yes", "go ahead", etc.)
  - Then executes the command if confirmed
- **Relaxed command blocking**: Only truly destructive commands are blocked (like `rm -rf /`, `shutdown`, etc.)
- **Allowed sensitive operations**: Editing config files, SSH config, system configs, installing packages, etc. are now allowed with warnings
- **User control**: Users can now get help with system administration tasks without Gemini refusing

### Enhanced Shim Script with Process Cleanup

- **Automatic process cleanup**: `shim` script now automatically finds and kills old processes before starting
- **Kills multiple process types**:
  - Old `shimeji_dual_mode_agent.py` processes
  - Old `shijima-qt` processes  
  - Any Python processes running the agent script
- **Graceful shutdown**: Attempts graceful kill first, then force kill (SIGKILL) if processes don't exit
- **Clean startup**: Waits for processes to clean up before starting new instance
- **Status messages**: Shows what it's doing (killing old processes, starting fresh, etc.)
- **Prevents conflicts**: Ensures no duplicate processes or background zombies interfere with new instance

### Fixed Duplicate Greeting Messages

- **Removed duplicate greeting**: Fixed issue where two greeting messages were appearing in chat panel on startup
- **Single greeting**: Now shows only one greeting message ("Shimeji: I'm awake and ready!") that appears in both the speech bubble and chat panel
- **Cleaner startup**: Removed redundant "Gemini: Hi! I'm your Shimeji companion..." message that was duplicating the Shimeji greeting

### SQLite Chat Database with Import/Export

- **Created `modules/chat_database.py`**: Comprehensive SQLite-based chat management system with:
  - Multiple chat session support (each `shim` run creates a new session)
  - Session metadata (title, creation time, message counts)
  - Message storage with timestamps and author tracking
  - Import/export functionality (JSON and Markdown formats)
  - Session listing and management
  - Graceful session creation on startup
- **Updated `modules/speech_bubble.py`**: 
  - Replaced JSON file storage with SQLite database
  - Added Import button alongside Export button in chat UI
  - Added folder button (📁) to open exports directory in file manager
  - Import dialog automatically opens in current directory (where exports are saved)
  - Export dialog defaults to current directory with sensible filename
  - Fixed export error where path type checking was incorrect
  - Automatic new session creation each time `shim` is run
  - Export supports both Markdown and JSON formats via file dialog
  - Import allows creating new session or appending to current session
  - Real-time database persistence (no more debounced saves)
  - Session-aware message loading and filtering
- **Database Location**: `var/chat_history.db` (automatically created)
- **Backward Compatibility**: Old `chat_history.json` files are ignored (database takes precedence)

### Credits & Attribution Updates

- **Added Niodoo.com attribution**: Updated README, LICENSE, and all documentation to credit Niodoo.com as the project creator
- **Proper Shijima-Qt credits**: Added comprehensive credits section acknowledging [pixelomer](https://github.com/pixelomer) and [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt) with links
- **Original Shimeji creators**: Acknowledged the original Shimeji concept and the Shimeji community in credits
- **License clarification**: Documented that Shijima-Qt uses GPL v3 while NiodooLocal integration uses MIT License
- **Updated install script**: Enhanced to always pull the latest Shijima-Qt from git with proper fetch, pull, and submodule update steps. Now handles both main and master branches and ensures submodules are up to date

### GitHub-Ready: Project Open Source Preparation

- **Created `.gitignore`**: Comprehensive ignore file excluding build artifacts, virtual environments, sensitive files (API keys, databases), Python cache, Qt build files, and OS-specific files
- **Created `README.md`**: Comprehensive documentation including:
  - Project overview and features
  - Quick start guide
  - Installation instructions
  - Usage examples
  - Architecture diagram
  - Configuration guide
  - Privacy & security information
  - Troubleshooting section
  - Contributing guidelines
- **Created `LICENSE`**: MIT License for open-source distribution
- **Created `shimeji.env.example`**: Template configuration file without sensitive API keys for safe version control
- **Updated `install.sh`**: Now automatically creates `shimeji.env` from example file if it doesn't exist, and provides clearer instructions for API key setup
- **Security**: Ensured all sensitive files (API keys, chat history, databases) are excluded from version control

### Fixed Speech Bubble Export Button Error

- **Fixed AttributeError in ChatWindow**: Corrected method name in export button connection from `_export_to_markdown` to `export_to_markdown` in `modules/speech_bubble.py` line 193. The button was trying to connect to a non-existent private method instead of the actual public method, causing the SpeechBubbleOverlay thread to crash on startup.

### Installation Script Created

- **Created `install.sh`**: Comprehensive installation script that automates the entire NiodooLocal setup process
- **System Dependencies**: Installs Qt6 development packages, build tools (cmake, gcc), Python3, and system utilities (xclip, wl-clipboard, gnome-screenshot, scrot, pydbus) with support for apt-get, dnf, and pacman package managers
- **Shijima-Qt Integration**: Automatically clones or updates Shijima-Qt from https://github.com/pixelomer/Shijima-Qt.git, initializes submodules, and builds the project using qmake6/qmake
- **Python Environment**: Creates and configures Python virtual environment (`shimeji_venv`) with all required dependencies: google-generativeai, requests, PySide6, pydbus, watchdog
- **Bash Configuration**: Automatically adds to `~/.bashrc`:
  - `export QT_QPA_PLATFORM=xcb` for Qt platform compatibility
  - `alias kill-shimeji='pkill -f shimeji_dual_mode_agent.py'` for easy process management
  - `alias shim='${ROOT_DIR}/shim'` for convenient command access
- **Script Permissions**: Makes `shim` script executable automatically
- **Installation Verification**: Validates that Shijima-Qt binary, Python venv, and shim script are all properly set up
- **User-Friendly**: Provides clear progress indicators, error handling, and post-installation instructions

## 2025-01-15

### Fixed Zombie Process Issue & System Diagnostics

- **Zombie Process Prevention**: Fixed `ensure_shimeji_running()` in `shimeji_dual_mode_agent.py` to properly detach spawned `shijima-qt` processes using `start_new_session=True` in `subprocess.Popen()`. This prevents child processes from becoming zombies when they exit, as they're now detached from the parent process group.
- **Process Cleanup**: Killed duplicate `shimeji_dual_mode_agent.py` processes (PIDs 13760, 14573) that were spawning zombie `shijima-qt` processes. Reduced zombie count from 5 to 3 (remaining zombies are from system processes, not the agent).
- **System Performance**: Addressed high load average (3.74 → 2.31) caused by duplicate agent processes and zombie accumulation.
- **System Diagnostics Performed**: 
  - **File Descriptor Leak**: Identified 214,125 open file descriptors system-wide, with Firefox holding 43,672 and GNOME Shell holding 21,199. This is likely the primary cause of system lag.
  - **GPU Status**: RTX 5080 showing 428W power draw at 0% utilization (driver reporting anomaly), 59°C temp, 295MB/16GB VRAM used.
  - **CPU/Memory**: Load average improving (2.31), 19GB memory available, multiple Cursor processes using 20-44% CPU each.
  - **Disk I/O**: Normal (0.50% utilization).
  - **Recommendations**: Restart Firefox to clear ~43k open FDs, consider restarting Cursor to reduce open file count.

## 2025-01-XX

### Enhancement Review Implementation - Phases 1-2 Complete

#### Phase 1: High-Impact Quick Wins
- **Periodic Memory Cleanup**: Added `_cleanup_loop()` task that runs every hour (configurable via `MEMORY_CLEANUP_INTERVAL`) to clean up old episodic memories (default 30 days, configurable via `MEMORY_CLEANUP_DAYS`)
- **Rate Limiting**: Implemented `RateLimiter` class with sliding window algorithm (default 60 calls/60s, configurable via `GEMINI_RATE_LIMIT_MAX` and `GEMINI_RATE_LIMIT_WINDOW`). Integrated into both `ProactiveBrain` and `CLIBrain` to prevent API quota exhaustion
- **Structured Logging**: Created `modules/structured_logger.py` with JSON-formatted logging for decisions, API calls, errors, mode switches, and behavior changes. Integrated into agent for better observability
- **Input Sanitization**: Added `_sanitize_prompt()` method to `CLIBrain` that removes control characters and limits prompt length to 10000 characters to prevent injection attacks

#### Phase 2: Architecture Improvements
- **Extracted Brain Classes**: Moved `ProactiveBrain` and `CLIBrain` to separate modules (`modules/brains/proactive_brain.py` and `modules/brains/cli_brain.py`). Created `modules/brains/shared.py` for shared types (`ProactiveDecision`, `RateLimiter`)
- **Decision Executor**: Created `modules/decision_executor.py` with handler registry pattern. Extracted all decision execution logic from `DualModeAgent._execute_decision()` into separate handler methods for better maintainability
- **Plugin System**: Created `modules/plugin_base.py` with `ToolPlugin` ABC. Added plugin registry to `modules/tool_schema_factory.py` with `register_plugin()` and `get_registered_plugins()`. Plugins can extend function declarations and execute custom actions
- **Event Bus**: Created `modules/event_bus.py` with `EventBus` class supporting pub/sub pattern. Integrated into `DualModeAgent` to publish events for context changes, behavior changes, mode switches, and decisions

#### Phase 3: Observability & UX
- **Performance Metrics**: Added `PerformanceMetrics` dataclass to track API call times, decision times, context updates, and errors. Integrated metrics recording into proactive loop and brain classes. Added `get_metrics()` method to `DualModeAgent`
- **Health Check Endpoint**: Added health check support to `InvocationServer` that responds to "HEALTH" or "GET /health" requests with status, mode, mascot availability, memory stats, uptime, and performance metrics
- **Visual Feedback for API Calls**: Added typing indicator to `ChatWindow` with animated dots ("Shimeji is thinking...") that shows during Gemini API calls and hides on response
- **Keyboard Shortcuts**: Added keyboard shortcuts to `ChatWindow`: Escape to hide, Ctrl+Enter to submit, Tab to focus input field

#### Phase 4: Polish & Extensibility
- **Configuration Hot Reload**: Added `_watch_config()` method using `watchdog` library to watch `shimeji.env` for changes and reload configuration without restart. Updates rate limiter and intervals dynamically
- **Chat History Search & Export**: Added search box to filter chat history by query and export button to save history as markdown file with timestamp
- **Type-Safe Configuration**: Migrated `AgentConfig` in `config.py` to Pydantic `BaseModel` with field validators (model names, interval ranges, port ranges). Falls back to dataclass if Pydantic not available
- **Integration Test Suite**: Created `tests/integration/test_agent_workflow.py` with tests for mode switching, decision execution, and memory operations. Created `tests/fixtures/mock_gemini.py` for mocking Gemini API responses

#### Additional Enhancements
- **Connection Pooling**: Added HTTP connection pooling to `DesktopController` using `requests.adapters.HTTPAdapter` with pool_connections=10, pool_maxsize=20, max_retries=3 to reduce connection overhead

## 2025-11-13

### ShimejiCompanion Local Setup Completed

- **Copied ShimejiCompanion code from RunPod** (`/workspace/Niodoo-Final/cpp-qt-brain-integration`) to local Ubuntu 25.10 laptop
- **Fixed Qt6 compatibility issues** referencing [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt):
  - Replaced deprecated `QDesktopWidget` (removed in Qt6) with `QScreen`
  - Updated `enterEvent(QEvent*)` to `enterEvent(QEnterEvent*)` for Qt6
  - Replaced deprecated `qrand()` with C++11 `std::random_device` and `std::mt19937`
  - Fixed anonymous class syntax in event filter (replaced with lambda)
- **Installed Qt6 dependencies** on local machine: `qt6-base-dev`, `qt6-base-dev-tools`, `libqt6network6`, `cmake`, `build-essential`
- **Built ShimejiCompanion successfully** using CMake and make
- **Set up SSH tunnel** to RunPod telemetry service: `ssh -N -L 9999:localhost:9999 root@38.80.152.77 -p 30534`
- **Launched ShimejiCompanion** - GUI now running locally, displaying consciousness states (currently showing sad face emotion)
- ShimejiCompanion connects to RunPod's `niodoo_real_integrated` telemetry on port 9999 through secure SSH tunnel

### Architecture
- **Local**: ShimejiCompanion Qt6 GUI (displays emotions, consciousness states)
- **Remote RunPod**: `niodoo_real_integrated` Rust backend (telemetry server on port 9999)
- **Connection**: SSH tunnel forwards localhost:9999 → RunPod:9999

### Shijima-Qt Desktop Pet Deployed

- **Replaced basic emotion widget** with full [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt) desktop pet
- **Cloned and built Shijima-Qt** from source with all submodules (libshijima, libshimejifinder, cpp-httplib)
- **Installed additional dependencies**: qt6-multimedia-dev, libarchive-dev
- **Fixed submodule URLs** from SSH to HTTPS for public access
- **Successfully compiled** with release optimizations and LTO
- **Launched Shijima-Qt** - now have actual animated Shimeji character walking/bouncing on desktop!
- **GNOME Shell extension** auto-installed (required logout/login on Wayland)

### Niodoo-Shimeji Integration Bridge

- **Created `niodoo_shimeji_bridge.py`** - Python bridge connecting Niodoo telemetry to Shijima-Qt
- **Telemetry integration**: Reads real-time cognitive/emotional state from RunPod via SSH tunnel (port 9999)
- **Behavior mapping**: Maps PAD emotional states to Shimeji behaviors:
  - High arousal + positive → Jump (excited)
  - High arousal + negative → Fall (panic)
  - Low arousal + positive → SitDown (content)
  - Compass quadrants → Different behaviors (Panic→Fall, Discover→Climb, Persist→Walk, Master→Jump)
- **HTTP API control**: Sends commands to Shijima-Qt API (localhost:32456)
- **Real-time updates**: Shimeji behavior changes based on AI's emotional state
- **Chat bubble support**: Framework ready for displaying AI responses above Shimeji (Qt overlay TODO)

### Gemini-Powered Autonomous Shimeji Agent

- **Created `gemini_shimeji_agent.py`** - REAL autonomous AI agent using Gemini API
- **Function calling integration**: Gemini can control Shimeji via API calls (jump, sit, climb, walk, fall, spawn_friend)
- **Autonomous decision-making**: AI decides what to do based on time, context, and personality
- **No fake stubs**: Uses actual Gemini 1.5 Flash with real function calling
- **Personality system**: Configurable character personalities (playful_helper, tsundere, etc.)
- **Self-aware NPC**: Acts like a desktop companion that makes its own decisions
- **Created Deep Research Prompt**: Comprehensive prompt for Gemini Deep Research on autonomous desktop companions

### Dual-Mode Agent Infrastructure Progress

- **Added `modules/privacy_filter.py`** implementing keyword block-listing and regex-based PII scrubbing to ensure all desktop context is sanitised before reaching Gemini APIs. The filter supports recursive sanitisation of nested payloads and standardises sensitive window titles to "User in sensitive application".
- **Introduced `modules/context_sniffer.py`** providing a Wayland-safe GNOME window focus client using `pydbus`. The sniffer integrates with the "Window Calls Extended" shell extension, exposes synchronous polling as well as signal-based subscriptions, and gracefully handles missing dependencies.
- **Implemented `modules/desktop_controller.py`** and `shimeji_dual_mode_agent.py`, delivering the dual-mode asyncio state machine that orchestrates proactive (Gemini 2.5 Flash) and CLI (Gemini 2.5 Pro) behaviours, integrates privacy-filtered desktop context, exposes a TCP CLI invocation server, and routes mascot actions through a resilient Shijima-Qt HTTP client.
- **Automated behaviour schema generation** via `modules/tool_schema_factory.py`, parsing Shijima `actions.xml` files at runtime to build Gemini function declarations with enum-constrained behaviour names and wiring the desktop controller to validate the discovered action set.
- **Integrated `modules/memory_manager.py`** to provide working-memory deques and SQLite-backed episodic recall, wiring the proactive loop to inject recent observations and relevant long-term memories into Gemini decisions and enabling on-device fact persistence.
- **Created `modules/emotion_model.py`** and extended the proactive prompt pipeline to inject boredom/happiness/energy state, giving Gemini a feedback loop to vary behaviour (e.g. high boredom triggers playful actions, low energy prefers rest).
- **Enabled paid-tier friendly context caching** by attempting to create a Gemini cached-content entry (configurable via environment). The proactive brain now reuses context when available and gracefully falls back when caching is unavailable.
- **Shipped `modules/speech_bubble.py`** — a threaded PySide6 overlay that renders Markdown dialogue bubbles with click-through toggling, window translucency, and syntax highlighting ready text, backed by the desktop controller’s dialogue queue and lifecycle-managed by the agent.

### NPC Follow-Up Enhancements

- **Upgraded speech bubble overlay** (`modules/speech_bubble.py`) with anchor-aware positioning so chat bubbles and the chat panel follow the active mascot, clamp to the visible screen, and refresh every 200 ms without flicker. Added translucent themed chat UI, continuous reposition timers, and transparent window flags for a cleaner NPC feel.
- **Exposed mascot anchor polling** via `DesktopController.get_primary_mascot_anchor()` enabling real-time tracking of the Shijima-Qt sprite.
- **Extended `shimeji_dual_mode_agent.py`** to:
  - Poll mascot anchors asynchronously and stream position updates into the overlay.
  - Humanise behaviour announcements (“I’ll chase your mouse for a bit”) and tighten the proactive persona prompt to keep Gemini talking like the embodied pet.
  - Replace deprecated `datetime.utcnow()` usage with timezone-aware logging, start the chat panel with a friendly greeting, and ensure anchor polling respects configurable intervals (`SHIMEJI_ANCHOR_POLL`).
- **Hardened startup/shutdown** by introducing exponential backoff, log throttling, and graceful fallback when the Shijima API is offline (`SHIMEJI_API_BACKOFF_*` envs), preventing connect-refused spam during launch or exit.
- **Ensured CHANGELOG discipline** by recording all NPC upgrades and prompting adjustments here for auditability.

### Shonen Jump Arch-Nemesis Best Friend Persona Upgrade

- **Persona Overhaul**: Transformed prompts in `shimeji_dual_mode_agent.py` to embody a "cute arch-nemesis best friend" in Shonen Jump style—energetic, tsundere rival who's playfully competitive but loyal (e.g., "Hah, think you can beat me? I'll help... this time!").
- **Bubble Jazz**: Added fade-in animations and sound effects (via `playsound`) to speech bubbles in `modules/speech_bubble.py` for more dynamic pops.
- **Mouse Chase Tool**: Extended `DesktopController` with `chase_mouse()` method, callable proactively for fun interactions.
- **Fact Fetcher**: Integrated Wikipedia API tool (`fetch_fact`) in `tool_schema_factory.py` and handled in agent for sharing random facts.
- **Chat UX Polish**: Added emoji injection to responses, persistent history saving/loading to JSON in `speech_bubble.py`'s ChatWindow.
- **Cleanup**: Refactored magic numbers to env vars; added basic unit tests in new `tests/` folder (run with `python -m unittest discover tests`).

### How to Run

#### Option 1: Niodoo Telemetry Bridge (Emotion-driven)
```bash
# 1. SSH tunnel to RunPod (already running)
ssh -N -L 9999:localhost:9999 root@38.80.152.77 -p 30534 -i ~/.ssh/id_ed25519 &

# 2. Start Shijima-Qt
cd /home/ruffian/NiodooLocal/Shijima-Qt && ./shijima-qt &

# 3. Start the bridge
python3 /home/ruffian/NiodooLocal/niodoo_shimeji_bridge.py
```

#### Option 2: Autonomous Gemini Agent (AI-driven) - RECOMMENDED
```bash
# 1. Get Gemini API key (free): https://makersuite.google.com/app/apikey

# 2. Edit shimeji.env and add your API key
nano /home/ruffian/NiodooLocal/shimeji.env
# Change: GEMINI_API_KEY=your_api_key_here
# Model: gemini-2.5-flash (already configured)

# 3. Start Shijima-Qt
cd /home/ruffian/NiodooLocal/Shijima-Qt && ./shijima-qt &

# 4. Start autonomous agent
/home/ruffian/NiodooLocal/shimeji_venv/bin/python /home/ruffian/NiodooLocal/gemini_shimeji_agent.py
```

#### Gemini Deep Research
Paste contents of `/home/ruffian/NiodooLocal/gemini_deep_research_prompt.txt` into Gemini Deep Research for comprehensive analysis.

### Chat UI Overhaul: Taskbar Panel + Standalone Bubbles

- **Docked Taskbar Panel**: Modified `ChatWindow` in `speech_bubble.py` to dock fixed on left screen edge (x=0, vertically centered, taller 300x600). Persistent history, input field—full conversation here. Close button hides (not closes) for quick toggle.
- **Standalone Bubbles**: Kept as non-interactive pop-ups above Shimeji (can't type, just display short Shimeji responses). Route full responses to panel, truncated (first 20 words + ...) to bubbles.
- **Queue Cleanup**: Removed unnecessary repositioning for panel (fixed dock); ensured bubbles still follow anchor.
- **Typing Fix**: Ensured input field focuses on open; if still can't type, it's a Qt focus issue—added `activateWindow()`.
- **Visibility Fixes**: Converted chat panel to non-translucent always-on-top window, forced immediate show/raise with explicit docking logs, and retained Qt timers to prevent garbage collection so bubbles/panel refresh reliably.
- **Dual Chat Windows Working**: Created TWO persistent QWidget chat boxes: (1) green panel docked bottom-right (movable, with title bar) for user input/full history, (2) white transparent BubbleBox that follows the Shimeji anchor, shows most recent message, auto-fades after duration. Both use identical window creation approach (Qt.Window + always-on-top) so GNOME renders them reliably.
- **Reduced Emoji Spam**: Toned down emoji injection to only add one at sentence end (! or ?), not throughout the text.
- **Dynamic Bubble Sizing**: Chat bubble now adjusts both width (200-420px) and height (60-300px) based on text content with proper word wrapping, preventing cut-off messages and eliminating empty space for short replies.
- **CLI Mode Function Calling**: Enabled behavior control tools in CLI mode so when you type "make it sit" or "jump", Gemini actually calls set_behavior() to control the Shimeji instead of just responding with text. Both proactive and CLI modes now have full control.
- **Behavior Verification & Logging**: Added get_current_behavior() to confirm mascot state after commands, expanded behavior descriptions for clarity, increased mascot cache TTL to 2s (reduces GET spam), and slowed anchor polling to 0.5s for better performance.
- **Discovered Shimeji Behavior System**: Analyzed Shijima-Qt source—behaviors are state-machine driven, not instant commands. API calls next_behavior() which queues transitions based on physics/conditions (e.g., "Sit" requires being on floor). Behaviors flash quickly because mascot transitions through states automatically per behaviors.xml logic.
- **Reactive State Responses**: Extended anchor loop to detect behavior changes (Dragged, Thrown, Pinched, ClimbWall, ClimbCeiling, Jumping, Running, Sprawl) and trigger personality-driven reactions in real-time with randomized responses (e.g., "Hey! Put me down!" when picked up, "Spider-Shimeji!" when climbing, "OUCH!" when thrown). Makes the Shimeji feel alive and responsive to user interactions.
- **Fixed CLI Response Parsing**: Corrected text extraction from Gemini responses to handle both function calls AND text content properly, so asking for code/help returns the full response instead of just "Done!".
- **Reduced Proactive Spam**: Removed proactive brain's show_dialogue and set_behavior messages from chat panel—they only appear in bubbles now. Chat panel reserved for user conversations, so messages persist longer without being flooded by autonomous chatter. Also eliminated "Got it! [Executed...]" spam when Gemini calls functions—only shows actual text responses.

## 2025-11-14

### SSH Config Updated for New RunPod Instance

- **Updated `runpod-direct` host**: Changed port from 30062 to 30137
- **Updated `runpod-ssh` host**: Changed user from zcmel8xlq1qtuj-64411d6e to ohnw3f8dbyjpxf-64411b39
- Both hosts point to same infrastructure: 38.80.152.77 (direct TCP) and ssh.runpod.io (proxied)
- **Usage**: `ssh runpod-direct` for direct TCP with SCP/SFTP support, `ssh runpod-ssh` for proxied connection

### Productivity Integrations

- **Created `modules/productivity_tools.py`** with system integration utilities: clipboard reading (xclip/wl-paste), bash command execution, screenshot capture (gnome-screenshot/scrot), battery/CPU/memory monitoring via /proc and upower.
- **Extended Function Schema** in `tool_schema_factory.py` with 5 new tools: read_clipboard, execute_bash, take_screenshot, check_system_status, plus existing fetch_fact—giving Gemini full system access.
- **Wired Productivity Actions** into agent execution loop: Gemini can now read what you copy, run bash commands and show output, capture screenshots for analysis, monitor system health and warn on low battery (<20%).
- **Updated Proactive Prompt** to inform Gemini of its new capabilities and encourage proactive tool use (e.g., "check battery when bored, read clipboard if user is copying code").
- **Installed System Dependencies**: xclip, wl-clipboard (Wayland), gnome-screenshot, scrot for cross-platform clipboard/screenshot support.
- **Fixed Shimeji Behaviour Control**: Updated `DesktopController` to always refresh mascot IDs before triggering behaviours, include the `id` field in PUT requests per Shijima-Qt API spec, and retry once on 404 errors—resolving "No such mascot" failures that prevented Gemini from controlling the pet.

### Vision Analysis Integration

- **Added `analyze_screenshot` Function**: New tool that captures a screenshot and analyzes it with Gemini Vision API (Gemini 2.5 Pro) to understand what's on screen, debug code, identify errors, or describe visual context.
- **Implemented `_analyze_image_with_vision` Method**: Async method that uploads screenshots to Gemini, sends them with a question/prompt, extracts detailed analysis, and cleans up uploaded files automatically.
- **Updated Tool Schema**: Added `analyze_screenshot` function declaration with optional `question` parameter for targeted analysis (e.g., "What error do you see?", "What code is on screen?").
- **Enhanced Proactive Prompt**: Updated to mention vision AI capability so Gemini knows it can see and understand screenshots.
- **Full Vision Pipeline**: Screenshot → Upload to Gemini → Vision Analysis → Display in Chat Panel. Shimeji can now actually SEE your screen and help debug, read code, identify UI elements, or describe what you're working on.
- **Fixed Screenshot Detection**: Improved `take_screenshot()` to check file existence first (not just returncode) because `gnome-screenshot` outputs warnings to stderr on Wayland but still succeeds. Added better error logging to debug screenshot failures.

All per user request for separated persistent log vs. temporary speech bubbles.

## 2025-01-XX

### Enhancement Review & Recommendations

- **Created `ENHANCEMENT_REVIEW.md`** - Comprehensive enhancement review identifying new improvement opportunities beyond existing fixes
- **Review Categories:**
  - Performance & Scalability (memory cleanup, connection pooling, batch updates, async operations)
  - Feature Additions & Extensibility (plugin system, rate limiting, health checks, config hot reload)
  - Observability & Monitoring (structured logging, performance metrics, error tracking)
  - Code Organization & Maintainability (extract brain classes, decision executor, type-safe config)
  - User Experience Improvements (keyboard shortcuts, chat search/export, visual feedback)
  - Architecture Enhancements (event bus, state machine, dependency injection)
  - Security Enhancements (input sanitization, API key rotation)
  - Testing Enhancements (integration tests, mock Gemini API)
- **Priority Implementation Plan:** Organized into 4 phases with estimated effort (8-14 days total)
- **Key Recommendations:**
  - Phase 1 Quick Wins: Periodic memory cleanup, rate limiting, structured logging, input sanitization
  - Phase 2 Architecture: Extract classes, plugin system, event bus
  - Phase 3 Observability: Metrics, health checks, UX improvements
  - Phase 4 Polish: Config hot reload, chat features, type safety, integration tests

### Comprehensive Code Review & Fixes

- **Created `CODE_REVIEW.md`** - Full codebase review with improvement recommendations organized by priority
- **Implemented all high and medium priority fixes from code review:**

#### Resource Management & Cleanup
- **Fixed SQLite connection leaks** in `modules/memory_manager.py`: Added context manager support to `MemoryManager`, made `EpisodicMemory._conn` Optional with proper cleanup, added `cleanup_old_episodes()` method for episodic memory pruning (30-day default)
- **Fixed Qt timer leaks** in `modules/speech_bubble.py`: Added `cleanup()` method to `BubbleBox` for `_fade_timer` and `_reposition_timer`, ensured cleanup in shutdown path
- **Fixed deprecated `datetime.utcnow()`**: Replaced with `datetime.now(UTC)` in `memory_manager.py` for Python 3.12+ compatibility

#### Security Hardening
- **Command validation** in `modules/productivity_tools.py`: Added `DANGEROUS_COMMANDS` blocklist (rm -rf, dd, mkfs, shutdown, etc.), command length validation (max 1000 chars), validation before execution with user-friendly error messages
- **Clipboard sanitization**: Added `MAX_CLIPBOARD_LENGTH` (10000 chars) to prevent paste attacks, truncation with warning logs
- **API key validation**: Added `validate_api_key()` function in `shimeji_dual_mode_agent.py` with format checking, validation in `main()` before configuration

#### Error Handling Improvements
- **Refactored vision API error handling**: Split `_analyze_image_with_vision()` into separate methods (`_analyze_with_pil_fallback`, `_analyze_with_upload_fallback`, `_extract_text_from_response`) with clearer error paths and proper cleanup
- **Specific exception types**: Replaced broad `except Exception` with `genai_types.BlockedPromptException` and `genai_types.StopCandidateException` in CLI prompt handling
- **Backoff jitter**: Added random jitter (10% of backoff time) to exponential backoff in `desktop_controller.py` to prevent thundering herd

#### Code Cleanup
- **Removed debug print statement** in `speech_bubble.py` line 357, replaced with proper logging
- **Moved `wikipediaapi` import** to method level in `_get_random_fact()` with ImportError handling and fallback

#### Type Hints & Documentation
- **Added TypedDict classes**: Created `ContextDict` and `MascotDict` for structured data types
- **Added comprehensive docstrings**: Enhanced `_get_state_reaction()` with Google-style docstring including Args, Returns, and Examples sections

#### Configuration Management
- **Created `config.py`**: Centralized configuration with `AgentConfig` dataclass that loads from environment variables, includes all magic numbers as constants (`BUBBLE_REPOSITION_INTERVAL_MS`, `DEFAULT_REQUEST_TIMEOUT`, etc.)

#### Performance Optimizations
- **Skip anchor polling when no mascot**: Modified `_anchor_loop()` to check `list_mascots()` first, wait 2 seconds when no mascot exists instead of continuous polling
- **Reduced API calls in anchor loop**: Optimized `_anchor_loop()` to extract anchor and behavior from single `list_mascots()` call instead of making 3 separate API calls per iteration (reduced from ~3 calls/iteration to 1 call/iteration)
- **Debounced chat history saves**: Added 2-second debounce timer in `ChatWindow._save_history()` to avoid excessive I/O on every message
- **Episodic memory cleanup**: Added `cleanup_old_episodes()` method for automatic pruning of old memories
- **Reduced cache warning noise**: Changed context cache warning from WARNING to DEBUG level when caches API is unavailable

#### Testing Infrastructure
- **Created unit tests**: Added `tests/test_memory_manager.py` (working memory capacity, episodic memory, context manager), `tests/test_privacy_filter.py` (email scrubbing, blocklist filtering, nested structures), `tests/test_productivity_tools.py` (command validation, clipboard limits)

#### User Experience Improvements
- **Loading indicators**: Added "Analyzing screenshot... ⏳" message for vision API calls
- **Improved error messages**: More user-friendly error messages (e.g., "Analysis failed. Please try again." instead of raw exception text)

- **Review Categories:**
  - Code Quality & Architecture (type hints, constants, error handling)
  - Error Handling & Resilience (resource leaks, API recovery, vision API)
  - Performance & Optimization (unnecessary API calls, memory usage, Qt timers)
  - Security & Privacy (clipboard sanitization, command validation, API key validation)
  - Code Organization & Maintainability (file size, duplicate code, configuration)
  - Documentation & Type Hints (missing docstrings, TypedDict usage)
  - Testing & Reliability (unit tests, integration tests)
  - User Experience (error messages, loading states, chat persistence)
- **Overall Assessment:** Excellent code quality with opportunities for hardening and polish
- **Key Findings:** 
  - Strong architecture and async patterns
  - Need for better resource cleanup (SQLite, Qt timers) - **FIXED**
  - Missing command validation for bash execution - **FIXED**
  - Opportunity to extract large classes to separate files - **OPTIONAL, DEFERRED**
  - Need for comprehensive test coverage - **FIXED**

