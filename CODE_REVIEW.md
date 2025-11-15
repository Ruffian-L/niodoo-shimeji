# Code Review & Improvement Recommendations

**Date:** 2025-01-XX  
**Reviewer:** AI Code Review  
**Scope:** Full codebase review for improvements

---

## 🎯 Executive Summary

**Overall Assessment:** This is a well-architected, feature-rich autonomous desktop companion with solid separation of concerns. The code demonstrates good async patterns, privacy awareness, and system integration. However, there are opportunities for improvement in error handling, resource management, type safety, and code organization.

**Priority Areas:**
1. **HIGH:** Error handling & resource cleanup
2. **MEDIUM:** Type hints & documentation
3. **MEDIUM:** Performance optimizations
4. **LOW:** Code organization & refactoring

---

## 1. Code Quality & Architecture

### ✅ Strengths
- Clean separation of concerns (Brain, Controller, Memory, UI)
- Proper async/await patterns throughout
- Good use of dataclasses and type hints
- Privacy filtering before API calls
- Modular design with clear interfaces

### 🔧 Improvements Needed

#### 1.1 Missing Type Hints
**File:** `shimeji_dual_mode_agent.py`

**Issue:** Several methods lack return type hints or use `Any` too liberally.

```python
# Current (line 246)
async def respond(self, prompt: str, agent: "DualModeAgent") -> str:

# Better
async def respond(self, prompt: str, agent: "DualModeAgent") -> str:
    # Already good, but check for other methods
```

**Recommendation:**
- Add return type hints to all public methods
- Replace `Any` with more specific types where possible
- Use `TypedDict` for structured dictionaries (e.g., context dicts)

#### 1.2 Magic Numbers & Constants
**File:** Multiple files

**Issue:** Some magic numbers still exist despite previous cleanup.

```python
# speech_bubble.py line 274
self._reposition_timer.start(100)  # Magic number

# desktop_controller.py line 35
request_timeout: float = 2.5  # Could be env var
```

**Recommendation:**
```python
# Add to constants section
BUBBLE_REPOSITION_INTERVAL_MS = int(os.getenv("BUBBLE_REPOSITION_INTERVAL_MS", "100"))
DEFAULT_REQUEST_TIMEOUT = float(os.getenv("SHIMEJI_REQUEST_TIMEOUT", "2.5"))
```

#### 1.3 Inconsistent Error Handling
**File:** `shimeji_dual_mode_agent.py`

**Issue:** Some methods catch `Exception` too broadly, others don't catch at all.

```python
# Line 743 - too broad
except Exception as exc:  # pragma: no cover - runtime dependent
    LOGGER.exception("CLI prompt failed: %s", exc)

# Better: catch specific exceptions
except (genai.types.BlockedPromptException, genai.types.StopCandidateException) as exc:
    LOGGER.warning("Gemini API error: %s", exc)
    # Handle gracefully
except Exception as exc:
    LOGGER.exception("Unexpected error in CLI prompt: %s", exc)
    # Fallback behavior
```

---

## 2. Error Handling & Resilience

### 🔴 Critical Issues

#### 2.1 Resource Leaks
**File:** `modules/memory_manager.py`

**Issue:** SQLite connection not properly closed in error cases.

```python
# Line 49 - connection created but not in try/finally
self._conn = sqlite3.connect(self.db_path, check_same_thread=False)

# Recommendation: Use context manager
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
```

**File:** `modules/speech_bubble.py`

**Issue:** Qt timers and widgets may not be cleaned up on exceptions.

```python
# Line 277 - timer created but not guaranteed cleanup
self._fade_timer: Optional[QTimer] = None

# Recommendation: Add cleanup in __del__ or explicit cleanup method
def cleanup(self) -> None:
    if self._fade_timer:
        self._fade_timer.stop()
        self._fade_timer = None
    if self._reposition_timer:
        self._reposition_timer.stop()
```

#### 2.2 API Failure Recovery
**File:** `modules/desktop_controller.py`

**Issue:** Backoff mechanism is good, but could be more resilient.

**Current:** Exponential backoff with max cap  
**Improvement:** Add jitter to prevent thundering herd, reset on success

```python
import random

def _request(self, method: str, path: str, **kwargs) -> Response:
    # ... existing code ...
    except requests.RequestException as exc:
        # Add jitter to backoff
        jitter = random.uniform(0, self._current_backoff * 0.1)
        self._backoff_until = now + self._current_backoff + jitter
        # ... rest of error handling
```

#### 2.3 Vision API Error Handling
**File:** `shimeji_dual_mode_agent.py` (line 747)

**Issue:** Vision analysis has nested try/except that's hard to follow.

**Recommendation:** Extract to separate method with clearer error handling:

```python
async def _analyze_image_with_vision(self, image_path: str, question: str) -> Optional[str]:
    """Analyze an image using Gemini Vision API."""
    if not os.path.exists(image_path):
        LOGGER.warning("Screenshot file not found: %s", image_path)
        return None
    
    loop = asyncio.get_running_loop()
    vision_model = genai.GenerativeModel(DEFAULT_PRO_MODEL)
    
    try:
        # Try direct file path first (most efficient)
        response = await loop.run_in_executor(
            None, 
            lambda: vision_model.generate_content([image_path, question])
        )
        return self._extract_text_from_response(response)
    except Exception as exc:
        LOGGER.debug("Direct file path failed, trying PIL: %s", exc)
        return await self._analyze_with_pil_fallback(image_path, question, vision_model, loop)

async def _analyze_with_pil_fallback(self, image_path: str, question: str, 
                                     model, loop) -> Optional[str]:
    """Fallback using PIL Image."""
    try:
        import PIL.Image
        img = PIL.Image.open(image_path)
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content([img, question])
        )
        return self._extract_text_from_response(response)
    except ImportError:
        LOGGER.warning("PIL not available, trying file upload")
        return await self._analyze_with_upload_fallback(image_path, question, model, loop)
    except Exception as exc:
        LOGGER.error("PIL fallback failed: %s", exc)
        return None
```

---

## 3. Performance & Optimization

### 3.1 Unnecessary API Calls
**File:** `shimeji_dual_mode_agent.py`

**Issue:** `_anchor_loop` polls even when no mascot exists.

```python
# Line 532 - current
async def _anchor_loop(self) -> None:
    while self._running:
        anchor = await asyncio.to_thread(self.desktop_controller.get_primary_mascot_anchor)
        # ... always polls

# Better: Skip polling when no mascot
async def _anchor_loop(self) -> None:
    while self._running:
        mascots = await asyncio.to_thread(self.desktop_controller.list_mascots)
        if not mascots:
            await asyncio.sleep(2.0)  # Longer wait when no mascot
            continue
        anchor = await asyncio.to_thread(self.desktop_controller.get_primary_mascot_anchor)
        # ... rest of logic
```

### 3.2 Memory Usage
**File:** `modules/memory_manager.py`

**Issue:** Working memory deques could grow if not properly bounded (they are, but check usage).

**Current:** `deque(maxlen=20)` - good  
**Check:** Ensure episodic memory doesn't grow unbounded

```python
# Add cleanup for old episodes
def cleanup_old_episodes(self, days_to_keep: int = 30) -> None:
    """Remove episodes older than N days."""
    cutoff = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()
    with self._conn:
        self._conn.execute(
            "DELETE FROM episodes WHERE timestamp < ?",
            (cutoff,)
        )
```

### 3.3 Qt Timer Efficiency
**File:** `modules/speech_bubble.py`

**Issue:** Multiple timers running simultaneously.

**Current:** Reposition timer (100ms) + fade timer (50ms) + queue processor (200ms)  
**Optimization:** Consider combining or using single-shot timers where possible

```python
# Instead of continuous timer, use single-shot when needed
def _schedule_reposition(self) -> None:
    if not self._reposition_scheduled:
        QTimer.singleShot(100, self._update_position)
        self._reposition_scheduled = True
```

---

## 4. Security & Privacy

### ✅ Good Practices
- Privacy filtering before API calls
- Sensitive keyword blocklisting
- PII regex patterns

### 🔧 Improvements

#### 4.1 Clipboard Content Sanitization
**File:** `modules/productivity_tools.py`

**Issue:** Clipboard content sent to Gemini without additional sanitization.

**Recommendation:**
```python
@staticmethod
def read_clipboard() -> Optional[str]:
    """Read current clipboard content."""
    content = # ... existing code ...
    if content:
        # Additional sanitization before returning
        # Check for very long content (potential paste attack)
        if len(content) > 10000:
            LOGGER.warning("Clipboard content too long, truncating")
            return content[:10000] + "... [truncated]"
    return content
```

#### 4.2 Bash Command Validation
**File:** `modules/productivity_tools.py`

**Issue:** No validation of bash commands before execution.

**Recommendation:**
```python
# Add dangerous command blocklist
DANGEROUS_COMMANDS = {
    "rm -rf", "dd if=", "mkfs", "fdisk", "format",
    "> /dev/sd", "shutdown", "reboot", "init 0"
}

@staticmethod
def execute_bash_command(command: str, timeout: float = 10.0) -> dict:
    """Execute a bash command safely and return output."""
    # Validate command
    cmd_lower = command.lower()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous in cmd_lower:
            return {
                "error": f"Command blocked: contains dangerous pattern '{dangerous}'",
                "returncode": -1
            }
    
    # Check command length
    if len(command) > 1000:
        return {"error": "Command too long (max 1000 chars)", "returncode": -1}
    
    # ... rest of execution
```

#### 4.3 API Key Exposure Risk
**File:** `shimeji_dual_mode_agent.py`

**Issue:** API key loaded from env but not validated format.

**Recommendation:**
```python
def validate_api_key(key: str) -> bool:
    """Validate Gemini API key format."""
    # Gemini keys are typically base64-like strings
    if not key or len(key) < 20:
        return False
    # Add more validation if needed
    return True

# In main():
api_key = os.getenv("GEMINI_API_KEY")
if not api_key or not validate_api_key(api_key):
    raise RuntimeError("Invalid or missing GEMINI_API_KEY")
```

---

## 5. Code Organization & Maintainability

### 5.1 Large File Size
**File:** `shimeji_dual_mode_agent.py` (973 lines)

**Issue:** Main agent file is getting large.

**Recommendation:** Extract classes to separate files:
- `brains/proactive_brain.py` - ProactiveBrain class
- `brains/cli_brain.py` - CLIBrain class
- `servers/invocation_server.py` - InvocationServer class
- `decisions/decision_executor.py` - Decision execution logic

### 5.2 Duplicate Code
**File:** `modules/speech_bubble.py`

**Issue:** Message formatting duplicated between ChatWindow and BubbleBox.

**Recommendation:**
```python
def format_message_html(author: str, text: str, style: str = "chat") -> str:
    """Format message as HTML with consistent styling."""
    escaped_text = html.escape(text)
    if style == "chat":
        return f"<b style='color:#00ffff'>{html.escape(author)}:</b> {escaped_text}"
    elif style == "bubble":
        return f"<b style='color:#333'>{html.escape(author)}:</b><br>{escaped_text}"
    return escaped_text
```

### 5.3 Configuration Management
**Issue:** Configuration scattered across multiple files and env vars.

**Recommendation:** Create centralized config:

```python
# config.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class AgentConfig:
    flash_model: str
    pro_model: str
    personality: str
    proactive_interval: int
    reaction_interval: int
    listen_host: str
    listen_port: int
    anchor_poll_interval: float
    mascot_cache_ttl: float
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            flash_model=os.getenv("GEMINI_MODEL_NAME", DEFAULT_FLASH_MODEL),
            # ... etc
        )
```

---

## 6. Documentation & Type Hints

### 6.1 Missing Docstrings
**Files:** Multiple

**Issue:** Some methods lack docstrings, especially in utility classes.

**Recommendation:** Add docstrings following Google style:

```python
def _get_state_reaction(self, current: str, previous: Optional[str]) -> Optional[str]:
    """Get a personality-driven reaction to state changes.
    
    Args:
        current: Current behavior name (e.g., "Dragged", "Jumping")
        previous: Previous behavior name, or None if first state
        
    Returns:
        Random reaction string matching the personality, or None if no reaction
        
    Examples:
        >>> agent._get_state_reaction("Dragged", None)
        "Hey! Put me down!"
        
        >>> agent._get_state_reaction("Sit", "Walk")
        None  # No special reaction for this transition
    """
```

### 6.2 Type Hints for Complex Types
**Issue:** Some complex types use `Dict[str, Any]` instead of TypedDict.

**Recommendation:**
```python
from typing import TypedDict

class ContextDict(TypedDict):
    title: str
    application: str
    pid: int
    source: str

class MascotDict(TypedDict):
    id: int
    name: str
    anchor: Dict[str, float]
    active_behavior: Optional[str]
```

---

## 7. Testing & Reliability

### 7.1 Missing Unit Tests
**Issue:** No tests for critical paths (memory, emotion model, privacy filter).

**Recommendation:** Add tests:

```python
# tests/test_memory_manager.py
def test_working_memory_capacity():
    mem = WorkingMemory(capacity=5)
    for i in range(10):
        mem.record_observation({"test": i})
    assert len(mem.observations) == 5  # Should cap at 5

# tests/test_privacy_filter.py
def test_email_scrubbing():
    filter = PrivacyFilter()
    result = filter.sanitise("Contact me at user@example.com")
    assert "[EMAIL]" in result
    assert "user@example.com" not in result
```

### 7.2 Integration Test Coverage
**Issue:** No integration tests for agent workflows.

**Recommendation:** Add mock-based integration tests:

```python
# tests/test_agent_integration.py
@pytest.mark.asyncio
async def test_cli_mode_switching():
    agent = DualModeAgent(...)
    await agent.start()
    
    # Mock Gemini response
    with patch('genai.GenerativeModel') as mock_model:
        mock_model.return_value.generate_content.return_value = ...
        response = await agent.handle_cli_request("test")
        assert agent.mode == AgentMode.PROACTIVE  # Should switch back
```

---

## 8. User Experience

### 8.1 Error Messages
**File:** Multiple

**Issue:** Some error messages are too technical for end users.

**Recommendation:**
```python
# Instead of:
LOGGER.error("Shijima API request failed (%s %s): %s", method, url, exc)

# Show user-friendly message:
user_message = "Can't connect to Shimeji. Is it running?"
self.overlay.show_chat_message("System", user_message)
LOGGER.error("Shijima API request failed (%s %s): %s", method, url, exc)
```

### 8.2 Loading States
**Issue:** No feedback when Gemini is processing (especially for vision analysis).

**Recommendation:**
```python
# Show loading indicator
self.overlay.show_chat_message("Shimeji", "Analyzing screenshot... ⏳")
analysis = await self._analyze_image_with_vision(...)
# Message will be replaced by result
```

### 8.3 Chat History Persistence
**File:** `modules/speech_bubble.py`

**Issue:** Chat history saved on every message (could be slow).

**Recommendation:** Debounce saves:

```python
def _save_history(self) -> None:
    """Debounced save to avoid excessive I/O."""
    if self._save_timer:
        self._save_timer.stop()
    self._save_timer = QTimer.singleShot(2000, self._do_save)  # Save after 2s idle

def _do_save(self) -> None:
    """Actually save the history."""
    try:
        with open("chat_history.json", "w", encoding="utf-8") as handle:
            json.dump(self._chat_history, handle)
    except Exception as exc:
        LOGGER.warning("Failed to persist chat history: %s", exc)
```

---

## 9. Specific Code Fixes

### 9.1 Deprecated datetime.utcnow()
**File:** `modules/memory_manager.py` line 17

**Issue:** `datetime.utcnow()` is deprecated in Python 3.12+

**Fix:**
```python
from datetime import UTC, datetime

def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
```

### 9.2 Unused Import
**File:** `shimeji_dual_mode_agent.py` line 31

**Issue:** `wikipediaapi` imported but only used in one method.

**Recommendation:** Move import to method or add error handling:

```python
def _get_random_fact(self, topic: Optional[str] = None) -> str:
    try:
        import wikipediaapi
    except ImportError:
        return "Did you know? The universe is expanding faster than expected!"
    
    wiki = wikipediaapi.Wikipedia('en')
    # ... rest of method
```

### 9.3 Print Statement Left in Code
**File:** `modules/speech_bubble.py` line 357

**Issue:** Debug print statement still present.

**Fix:** Remove or convert to LOGGER.debug:
```python
# Remove this:
print(f"[BUBBLE] Added to bubble_box: {entry.author}: {entry.text}", flush=True)

# Or convert to:
LOGGER.debug("Added to bubble_box: %s: %s", entry.author, entry.text)
```

---

## 10. Performance Monitoring

### 10.1 Add Metrics
**Recommendation:** Add simple performance tracking:

```python
class PerformanceMetrics:
    def __init__(self):
        self.api_call_times: deque = deque(maxlen=100)
        self.decision_times: deque = deque(maxlen=100)
    
    def record_api_call(self, duration: float):
        self.api_call_times.append(duration)
    
    def get_avg_api_time(self) -> float:
        if not self.api_call_times:
            return 0.0
        return sum(self.api_call_times) / len(self.api_call_times)
```

---

## Priority Action Items

### 🔴 High Priority (Do First)
1. Fix resource leaks (SQLite connections, Qt timers)
2. Add command validation for bash execution
3. Improve error handling in vision API calls
4. Remove debug print statements

### 🟡 Medium Priority (Do Soon)
1. Extract large classes to separate files
2. Add comprehensive type hints
3. Create centralized configuration
4. Add unit tests for critical paths
5. Debounce chat history saves

### 🟢 Low Priority (Nice to Have)
1. Add performance metrics
2. Improve documentation strings
3. Refactor duplicate code
4. Add integration tests

---

## Conclusion

This is **excellent code** for a complex, real-world project. The architecture is sound, the features are impressive, and the code quality is generally high. The improvements suggested above are mostly polish and hardening rather than fundamental issues.

**Key Strengths:**
- Clean async architecture
- Good separation of concerns
- Privacy-aware design
- Comprehensive feature set

**Main Areas for Improvement:**
- Error handling robustness
- Resource management
- Type safety
- Test coverage

**Estimated Effort:**
- High priority fixes: 4-6 hours
- Medium priority: 8-12 hours
- Low priority: 4-8 hours

**Total:** ~16-26 hours of focused improvement work.

---

*End of Code Review*

