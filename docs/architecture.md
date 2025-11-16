# Living Agent Platform – Current Architecture Baseline

This repository already embodies many pieces of the proposed "Living Agent" Platform. The goal of this baseline document is to map existing code to the four LAP pillars (Presentation, Cognitive, Persistence, Communications) so future work can focus on deliberate, low-risk migrations rather than broad rewrites. File paths below are relative to the repository root.

## Pillars at a Glance

| Pillar | Scope | Representative modules / assets |
| --- | --- | --- |
| Presentation | Mascot rendering, overlays, direct UI affordances | `Shijima-Qt/`, `modules/desktop_controller.py`, `modules/speech_bubble.py`, `modules/presentation_api.py`, `modules/mascot_state_machine.py`, input sensors feeding UI (`modules/gesture_recognizer.py`, `modules/voice_handler.py`) |
| Cognitive | Agent brains, reasoning loops, orchestration | `shimeji_dual_mode_agent.py`, `modules/agent_core.py`, `modules/multi_agent.py`, `modules/decision_executor.py`, `modules/dialogue_manager.py`, `modules/context_manager.py`, `modules/genai_utils.py`, `modules/brains/` |
| Persistence | Memory, embeddings, analytics | `modules/memory_manager.py`, `modules/vector_memory.py`, `modules/vector_store.py`, `modules/chat_database.py`, `modules/user_model_synthesis.py`, `modules/pattern_learner.py`, `modules/workflow_pattern_recognizer.py`, `modules/metrics.py` |
| Communications | APIs, IPC, sensors feeding the bus | `shimeji_mcp_server.py`, `modules/invocation_server.py`, `modules/event_bus.py`, `modules/journal_monitor.py`, `modules/dbus_integration.py`, `modules/system_monitor.py`, `modules/tool_schema_factory.py` |

## Presentation Layer
- **Shijima-Qt/** – C++ desktop mascot application that renders the embodied companion and exposes an HTTP API (`Shijima-Qt/HTTP-API.md`).
- **modules/desktop_controller.py** – Python facade for the Shijima-Qt HTTP API (spawn, behavior control, avatar state queries).
- **modules/speech_bubble.py** – PySide overlay window for chat balloons and UI affordances anchored to the mascot position.
- **modules/presentation_api.py** – Defines `AvatarClient` and `UIEventSink` abstractions plus a `SpeechBubbleUISink` adapter that translates neutral `UIEvent` objects into Qt overlay calls. `DualModeAgent` now talks only to this interface, so alternative clients (e.g., Flutter, Tauri) can plug in without touching the core.
- **modules/mascot_state_machine.py** – Behavioral state transitions (idle, proactive, reactions) consumed by the overlay/controller pair.
- **modules/context_sniffer.py**, **modules/gesture_recognizer.py**, **modules/voice_handler.py** – Input sensors that feed the avatar-centric UI with focus, gesture, and voice context.

Together these components provide the "living dashboard" experience described in the blueprint, but the Python side is now decoupled from Qt-specific primitives via the presentation adapters.

## Cognitive Layer
- **shimeji_dual_mode_agent.py** – Async orchestrator that coordinates proactive (pet) and CLI modes, wires up all managers, and owns the main event loops. Marked internally as **Runner** (process/UI wiring) vs **Brain** (cognitive flows) to guide extraction.
- **modules/agent_core.py** – Core cognitive helpers that encapsulate reusable behaviours (CLI prompt handling, image/vision analysis helpers, response formatting) behind an interface that does not depend on Qt or process wiring. Future work will migrate the proactive decision loop and alert handling here.
- **modules/multi_agent.py**, **modules/decision_executor.py** – Role-specific agent logic that decomposes tasks into research/execution/analysis/monitoring phases.
- **modules/dialogue_manager.py**, **modules/context_manager.py**, **modules/emotion_model.py** – Conversation state, persona management, and emotion tracking.
- **modules/genai_utils.py**, **modules/brains/** – Gemini model wrappers, caching, rate limiting, and function-calling support.
- **modules/productivity_tools.py**, **modules/file_handler.py**, **modules/system_monitor.py** – Tool execution layer reachable from Gemini function calls or proactive routines.
- **modules/privacy_filter.py**, **modules/permission_manager.py**, **modules/input_sanitizer.py** – Local privacy and safety filters that gate data flowing into the cognitive core.

This stack already approximates a supervisor/worker layout; `AgentCore` is the convergence point for long-lived "brain" logic that other services (FastAPI backend, MCP servers) can reuse without dragging in presentation concerns.

## Persistence Layer
- **modules/memory_manager.py** – Episodic SQLite store (facts, preferences, event log, potential workflows) with recall helpers and a `get_vector_memory()` hook.
- **modules/vector_store.py** – Backend-agnostic interface (`BaseVectorStore`) plus concrete `SQLiteVectorStore` and `QdrantVectorStore` implementations, selected at runtime by `VectorStoreConfig.from_env()`.
- **modules/vector_memory.py** – Thin façade over the active vector store backend that exposes `store_embedding`, `semantic_search`, and `update_episode_embeddings`. Used by `DecisionExecutor` to power the `semantic_memory_search` action and by future maintenance tasks.
- **modules/chat_database.py** – Conversation history persistence for the CLI and overlay chat experiences.
- **modules/user_model_synthesis.py**, **modules/pattern_learner.py**, **modules/workflow_pattern_recognizer.py** – Higher-level analytics that derive user models and workflow hypotheses from stored events.
- **var/** – Runtime artifacts (screenshots, logs) referenced by ingestion and journaling utilities.

All data is local-first today; semantic memory is optional and selected via environment variables (e.g., `VECTOR_STORE_BACKEND=sqlite|qdrant`). Migrating to Qdrant or encrypted stores can build on these access patterns without changing callers.

## Communications Layer
- **shimeji_mcp_server.py** – Model Context Protocol server exposing mascot control tools to external agents.
- **modules/invocation_server.py** – Local HTTP/TCP bridge that lets shell/CLI clients issue commands to the orchestrator.
- **modules/event_bus.py** – Pub/Sub spine that distributes alerts, dialogue updates, and system metrics across components.
- **modules/journal_monitor.py**, **modules/dbus_integration.py**, **modules/system_monitor.py** – Event emitters feeding the bus with desktop state.
- **Shijima-Qt/HTTP-API.md**, **cpp-qt-brain-integration/** – C++/Python bridge and test harnesses for the mascot API surface.

This layer currently relies on custom protocols and HTTP endpoints. A FastAPI + WebSocket "Synapse" can wrap these without losing functionality.

## High-Level Data Flow
1. `ContextSniffer`, D-Bus, and system monitors publish desktop events onto `EventBus`.
2. `DualModeAgent` consumes events, queries `MemoryManager`/`VectorMemory`, and invokes Gemini via `GenAIUtils`.
3. Decisions and tool calls run through `DecisionExecutor` → `ProductivityTools` / `FileHandler`.
4. Avatar and UI updates use `DesktopController` + `SpeechBubbleOverlay`, while external consumers can interact through `shimeji_mcp_server` or `invocation_server`.

## Immediate Next Steps (Phase 0 → Phase 1)
- Extract abstraction interfaces for avatar control and UI events so Presentation logic no longer depends on raw Qt calls.
- Introduce an `AgentCore` module that houses the cognitive logic currently embedded in `shimeji_dual_mode_agent.py`.
- Wrap memory and vector operations behind selectable backends to prepare for Qdrant/SQLCipher adoption.
- Document event types carried by `modules/event_bus.py` to ease future WebSocket mirroring.

With this baseline recorded, subsequent LAP phases can reference concrete modules when introducing FastAPI, CrewAI, Flutter, or alternative storage engines.

## Tooling & Integration Audit (Phase 0)

| Module | Callables reviewed | Purpose | Exposure guidance |
| --- | --- | --- | --- |
| `modules/productivity_tools.ProductivityTools` | `get_battery_status`, `get_cpu_usage`, `get_memory_usage` | System telemetry for status cards / proactive hints | **MCP-safe** (read-only) |
| | `read_clipboard`, `take_screenshot`, `execute_bash_command`, `cleanup_zombie_processes` | High-privilege desktop access (clipboard, shell, screenshots) | **Internal-only** until explicit consent + UX surfaces exist |
| `modules/file_handler.FileHandler` | `set_context`, delegated file drop handling | Drives proactive analysis of dropped files before routing to agents | **Internal-only** (operates on arbitrary user files) |
| `modules/system_monitor.MonitoringManager` | `_route_alert`, `_should_alert` | Emits `SystemAlert` events consumed by AgentCore | **Internal** (event producer; not a user-facing tool) |
| `modules/journal_monitor.JournalMonitor` | `_journal_callback` | Watches journald/system logs for context cues | **Internal** (continuous sensor feed) |
| `modules/desktop_controller.DesktopController` | `list_mascots`, `ensure_mascot`, `set_behavior`, `spawn_friend`, `show_dialogue`, `drain_dialogue_queue`, `get_primary_mascot_anchor` | Mascot lifecycle + animation controls | **MCP-safe** when routed through AvatarClient and permission gated |
| | `_request`, `_refresh_active_mascot`, `_invalidate_mascot_cache` | HTTP plumbing details | **Internal** |
| `modules/tool_schema_factory` | `register_plugin`, `build_proactive_function_declarations`, `load_behavior_names` | Generates JSON schema for tools exposed to LLMs | **MCP-safe** helpers (no side effects themselves) |

> Follow-up: expose MCP-safe functions through the evolving `AvatarClient`/`UIEventSink` abstractions so future FastAPI endpoints and MCP servers reuse a single policy surface.

## Test Coverage Snapshot

| Area | Existing tests | Notes / gaps |
| --- | --- | --- |
| Memory & persistence | `tests/test_memory_manager.py`, `tests/test_productivity_tools.py` (screenshot path), `tests/test_metrics.py`, `tests/test_decision_executor.py` | Add dedicated semantic search regression tests for `VectorMemory`/`SQLiteVectorStore` when sentence-transformers and Qdrant are enabled in CI. |
| Agent orchestration | `tests/test_dual_mode_agent_init.py`, `tests/test_decision_executor.py`, `tests/test_dialogue_manager.py`, `tests/integration/test_agent_workflow.py` | Need a headless "CLI mode" smoke test that runs `DualModeAgent.handle_cli_request` without starting Qt. |
| Sensors / integrations | `tests/test_context_manager.py`, `tests/test_latest_context_property.py`, `tests/test_speech_bubble.py` | Add mocks for `ContextSniffer` + `JournalMonitor` once FastAPI synapse consumes their events. |
| Tooling / privacy | `tests/test_permission_manager.py`, `tests/test_privacy_filter.py`, `tests/test_input_sanitizer.py` | Expand to cover `ProductivityTools.execute_bash_command` allow-list + clipboard redaction. |

> Action item: open tickets for the CLI smoke test and ProductiviyTools redaction coverage so Phase 1 refactors do not regress safety.

## Current Workstreams (Phase 0)

1. **Documentation hardening** – keep this file aligned with every LAP milestone so contributor onboarding stays effortless.
2. **DualModeAgent annotations** – mark Runner vs Brain sections inline before the `AgentCore` extraction begins.
3. **Tool audit** – catalog every callable exposed via `productivity_tools.py`, `file_handler.py`, `system_monitor.py`, `journal_monitor.py`, `desktop_controller.py`, `tool_schema_factory.py` and flag each as MCP-safe vs internal.
4. **Testing gaps** – note missing smoke tests (e.g., CLI-only run without Qt) and add follow-up tickets so coverage keeps pace with refactors.

## LAP Migration Snapshot

* **Short term** – keep Shijima-Qt + PySide overlay running, add abstraction layers (`presentation_api`, `AgentCore`, `VectorStore`/`VectorMemory`).
* **Medium term** – introduce `lap_backend/` FastAPI endpoints (`/chat`, `/proactive-tick`, `/synapse`, `/memory/*`) and optional Qdrant backend.
* **Long term** – optional Flutter client, CrewAI multi-agent orchestration, local model backends (Ollama/vLLM/ONNX) selected via `ModelBackend` configuration.
