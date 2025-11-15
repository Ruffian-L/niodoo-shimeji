# niodoo-shimeji 🎭

**An autonomous, embodied AI desktop companion powered by Google Gemini**

A project by [Niodoo.com](https://niodoo.com) - Building actually helpful Intelligence.

niodoo-shimeji brings a Shimeji desktop pet to life with real AI intelligence. Your desktop companion can see your screen, understand context, help with tasks, analyze documents, and interact with you through an animated character that actually thinks and responds.

![Shimeji Companion](https://img.shields.io/badge/Shimeji-AI%20Powered-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![Qt](https://img.shields.io/badge/Qt-6.0+-purple)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

### 🤖 Dual-Mode AI Agent
- **Proactive Mode**: Your Shimeji acts autonomously, making decisions based on context, time, and emotional state
- **CLI Mode**: On-demand assistant powered by Gemini 2.5 Pro for complex tasks and questions
- **Smart Mode Switching**: Automatically switches between modes based on user activity

### 🎨 Desktop Integration
- **Animated Shimeji Pet**: Powered by [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt) - a fully animated desktop companion
- **Context Awareness**: Understands what applications you're using (privacy-filtered)
- **Visual Feedback**: Speech bubbles and chat panel for interactions
- **Reactive Behaviors**: Shimeji reacts to being dragged, thrown, or interacted with

### 🧠 AI Capabilities
- **Vision AI**: Can analyze screenshots to help debug code, read UI elements, or understand what's on screen
- **Document Analysis**: Drag-and-drop files (images, PDFs, markdown, code files) directly into chat for Gemini to analyze
- **Function Calling with Chaining**: Real Gemini CLI-style tool chaining - Gemini can execute multiple commands in sequence (e.g., find file → verify → delete)
- **System Access**: Reads clipboard (on-demand), executes bash commands (safely), monitors system status
- **Memory System**: SQLite-based chat history with session management, import/export functionality
- **Privacy-First**: Automatically filters sensitive information before sending to AI

### 🛠️ Productivity Tools
- **Drag-and-Drop File Analysis**: Drop images, PDFs, markdown, code files into chat for instant analysis
- **Screenshot capture and analysis**: Vision AI understands what's on your screen
- **Clipboard button**: Manual clipboard reading with dedicated button (no automatic snooping)
- **System monitoring**: Battery, CPU, memory status with smart alerts
- **Bash command execution**: Safe command validation with function chaining support
- **Wikipedia fact fetching**: Random facts to share
- **Chat history management**: SQLite database with import/export (JSON/Markdown)

## 🚀 Quick Start

### Prerequisites
- Ubuntu/Debian (or compatible Linux distribution)
- Python 3.10+
- Qt6 development packages
- A free [Google Gemini API key](https://makersuite.google.com/app/apikey)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/Ruffian-L/niodoo-shimeji.git
cd niodoo-shimeji
```

2. **Run the installation script:**
```bash
./install.sh
```

The script will:
- Install all system dependencies (Qt6, build tools, Python packages)
- Clone and build Shijima-Qt
- Set up Python virtual environment
- Configure your bash environment
- Create necessary aliases

3. **Configure your API key:**
```bash
cp shimeji.env.example shimeji.env
nano shimeji.env
# Add your Gemini API key: GEMINI_API_KEY=your_actual_key_here
```

4. **Run the agent:**
```bash
shim
```

That's it! Your AI Shimeji companion is now running.

## 📖 Usage

### Starting the Agent

```bash
shim
```

This will:
- Launch the Shijima-Qt desktop pet
- Start the dual-mode AI agent
- Open a chat panel for interactions

### Stopping the Agent

```bash
kill-shimeji
# or
pkill -f shimeji_dual_mode_agent.py
```

### Chat Interface

- **Chat Panel**: Docked window for full conversations with persistent SQLite history
- **Speech Bubbles**: Quick pop-ups above the Shimeji character (proactive messages only show here, not in chat)
- **Drag-and-Drop**: Drop files directly into the chat window for analysis:
  - **Images**: PNG, JPG, GIF, WebP, etc. - analyzed with Vision API
  - **PDFs**: Text extraction and analysis (requires `pip install PyPDF2`)
  - **Text Files**: Markdown, code files, configs - read and analyzed
- **Clipboard Button (📋)**: Click to ask Gemini about your clipboard content
- **Import/Export**: Save chat sessions as JSON or Markdown, import previous conversations
- **Search**: Search through chat history
- **Keyboard Shortcuts**:
  - `Escape`: Hide chat panel
  - `Ctrl+Enter`: Submit message
  - `Tab`: Focus input field

### CLI Mode

Connect to the agent via TCP for programmatic access:

```bash
# Default port: 8770
echo "What's the weather like?" | nc localhost 8770
```

Or use the chat panel to interact directly.

## ⚙️ Configuration

Edit `shimeji.env` to customize:

```bash
# Gemini API
GEMINI_API_KEY=your_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash  # or gemini-2.5-pro

# Shimeji Settings
SHIMEJI_API_URL=http://127.0.0.1:32456/shijima/api/v1
SHIMEJI_UPDATE_INTERVAL=15

# Personality
SHIMEJI_PERSONALITY=playful_helper  # Options: playful_helper, tsundere, etc.

# Rate Limiting (optional)
GEMINI_RATE_LIMIT_MAX=60
GEMINI_RATE_LIMIT_WINDOW=60

# Memory Cleanup (optional)
MEMORY_CLEANUP_INTERVAL=3600  # seconds
MEMORY_CLEANUP_DAYS=30
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DualModeAgent                         │
│  ┌──────────────┐              ┌──────────────┐         │
│  │ Proactive    │              │ CLI Brain    │         │
│  │ Brain        │              │ (Gemini Pro) │         │
│  │ (Gemini      │              │              │         │
│  │  Flash)      │              │              │         │
│  └──────────────┘              └──────────────┘         │
│         │                            │                  │
│         └────────────┬───────────────┘                  │
│                      │                                   │
│         ┌────────────▼──────────────┐                   │
│         │   Decision Executor      │                   │
│         └────────────┬──────────────┘                   │
│                      │                                   │
│  ┌───────────────────┼───────────────────┐             │
│  │                   │                   │             │
│  ▼                   ▼                   ▼             │
│ Desktop          Memory            Speech Bubble        │
│ Controller       Manager           Overlay              │
│                  │                   │                   │
│                  ▼                   ▼                   │
│              SQLite DB         Qt Chat UI                │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              Shijima-Qt (Desktop Pet)                    │
│              HTTP API on port 32456                      │
└─────────────────────────────────────────────────────────┘
```

### Key Components

- **`shimeji_dual_mode_agent.py`**: Main orchestrator
- **`modules/brains/`**: AI brain implementations (ProactiveBrain, CLIBrain)
- **`modules/desktop_controller.py`**: Shijima-Qt API client
- **`modules/context_sniffer.py`**: Wayland-safe window focus detection
- **`modules/privacy_filter.py`**: PII scrubbing and sanitization
- **`modules/memory_manager.py`**: Episodic and working memory
- **`modules/speech_bubble.py`**: Qt overlay for chat UI
- **`modules/productivity_tools.py`**: System integration utilities

## 🔒 Privacy & Security

- **Privacy Filtering**: Automatically scrubs PII (emails, phone numbers, etc.) from context
- **Sensitive App Detection**: Recognizes sensitive applications and sanitizes window titles
- **Command Validation**: Bash commands are validated against a blocklist before execution
- **Local Memory**: Episodic memories stored locally in SQLite
- **No Data Collection**: All processing happens locally or through Google's Gemini API

## 🧪 Testing

Run the test suite:

```bash
python -m unittest discover tests
```

## 📝 Development

### Project Structure

```
niodoo-shimeji/
├── modules/              # Core modules
│   ├── brains/          # AI brain implementations (ProactiveBrain, CLIBrain)
│   ├── chat_database.py # SQLite chat history management
│   ├── context_sniffer.py
│   ├── desktop_controller.py
│   ├── memory_manager.py
│   ├── speech_bubble.py # Qt overlay with drag-and-drop support
│   ├── productivity_tools.py
│   └── ...
├── tests/               # Test suite
├── var/                 # Runtime data (chat database, etc.)
├── shimeji_dual_mode_agent.py  # Main entry point
├── install.sh           # Installation script
├── shim                 # Convenience launcher
└── shimeji.env.example  # Configuration template
```

### Adding New Features

1. Create a new module in `modules/`
2. Register tools in `modules/tool_schema_factory.py`
3. Add handlers in `modules/decision_executor.py`
4. Update tests in `tests/`
5. Document in `CHANGELOG.md`

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Update `CHANGELOG.md`
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments & Credits

### Project
- **NiodooLocal** is a project by [Niodoo.com](https://niodoo.com)
- Building actually helpful Intelligence

### Shimeji Desktop Pet
- **[Shijima-Qt](https://github.com/pixelomer/Shijima-Qt)** by [pixelomer](https://github.com/pixelomer) - The amazing cross-platform desktop pet framework built with Qt6
- **Original Shimeji Concept** - The Shimeji desktop pet concept originated from Japanese desktop companion culture. Special thanks to the original Shimeji creators and the entire Shimeji community for their creativity and contributions.

### AI & Technology
- **[Google Gemini](https://deepmind.google/technologies/gemini/)** - The AI that powers the intelligence
- The open-source community for inspiration and tools

### License Notes
- Shijima-Qt is licensed under GPL v3 - see [Shijima-Qt/LICENSE](Shijima-Qt/LICENSE)
- NiodooLocal integration code is licensed under MIT License - see [LICENSE](LICENSE)

## 🐛 Troubleshooting

### Shimeji not appearing
- Check if `shijima-qt` is running: `pgrep -f shijima-qt`
- Verify Qt platform: `echo $QT_QPA_PLATFORM` (should be `xcb`)
- Check logs for errors

### API errors
- Verify your Gemini API key in `shimeji.env`
- Check API quota limits
- Review rate limiting settings

### Chat panel not showing
- Check if PySide6 is installed: `pip list | grep PySide6`
- Look for Qt-related errors in logs
- Try restarting the agent

### Build issues
- Ensure all dependencies are installed: `./install.sh`
- Check Qt6 installation: `qmake6 --version`
- Review build logs in `Shijima-Qt/`

## 📚 Documentation

- [CHANGELOG.md](CHANGELOG.md) - Detailed change history

## 💬 Support

- Open an issue on GitHub for bugs or feature requests
- Check existing issues for solutions
- Review the troubleshooting section above

---

**Made with ❤️ for the Gemini and Ubuntu community**

A project by [Niodoo.com](https://niodoo.com) - *Building actually helpful Intelligence* 🚀

### Credits
- **Project**: [Niodoo.com](https://niodoo.com)
- **Shijima-Qt**: [pixelomer](https://github.com/pixelomer) - [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt)
- **Original Shimeji**: The Shimeji community and original creators

