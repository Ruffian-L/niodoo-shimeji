# AgentCore Expansion Plan

The LAP migration requires AgentCore to own **cognitive flows** (decisions, Gemini calls, long-running perception loops) while `DualModeAgent` focuses on process/lifecycle wiring. This note inventories the remaining "brain" logic inside `shimeji_dual_mode_agent.py` and outlines how to extract it cleanly into `modules/agent_core.py`.

## Current AgentCore Surface (v0)

| Concern | Who owns it today | Notes |
| --- | --- | --- |
| CLI prompt handling | `AgentCore.process_cli_prompt()` | Emits chat/bubble messages via `UIEventSink` and routes optional image analysis. |
| Emoji helpers + Gemini response parsing | `AgentCore.add_emojis()` + `_extract_text_from_response()` | Already stateless and reusable. |
| Vision helpers | `_analyze_image_with_vision()` (+ PIL/upload fallbacks) | Lives inside AgentCore but called only from DualModeAgent. |

The rest of the agent still calls Gemini, updates memories, and drives the mascot directly from the runner.

## Brain Logic Still Embedded in `DualModeAgent`

| Section (file + lines) | Why it is "brain" logic | Key dependencies | Extraction target |
| --- | --- | --- | --- |
| `_proactive_loop` – `shimeji_dual_mode_agent.py:L1014-L1055` | Pulls context/memory/emotion state, calls `proactive_brain.decide`, records metrics, and triggers execution interval selection. | `proactive_brain`, `memory`, `emotions`, `_recent_actions`, `_metrics`, `_decision_executor` | `AgentCore.run_proactive_cycle()` returning next interval + decision metadata. |
| `_handle_critical_alert` – `shimeji_dual_mode_agent.py:L750-L789` | Builds enriched context, queries Gemini proactively, executes returned decision. | Same set as `_proactive_loop` + `_critical_alert_cache`, `_event_bus` | `AgentCore.handle_critical_alert(alert)` should encapsulate rate limiting + execution. Runner just enqueues task when event fires. |
| `_vision_analysis_loop` – `shimeji_dual_mode_agent.py:L907-L959` | Periodically screens the desktop, requests permissions, invokes Gemini Vision, and updates context/memory. | `PermissionManager`, `ProductivityTools`, `AgentCore._analyze_image_with_vision`, `_merge_latest_context`, `_handle_detected_error` | `AgentCore.run_vision_probe(config)` orchestrates permission check, screenshot, analysis, and context merge. Runner only schedules the loop. |
| `_handle_detected_error` – `shimeji_dual_mode_agent.py:L962-L1006` | Crafts Gemini prompt, uses CLI brain to produce remediation, and emits UI events + mascot state transition. | `cli_brain`, `_emit_chat`, `_emit_bubble`, `_transition_mascot_state` | Move prompt construction + Gemini call into `AgentCore.resolve_detected_error()`. Runner can still own `_transition_mascot_state` by passing callback. |
| `handle_cli_request` – `shimeji_dual_mode_agent.py:L1121-L1150` | Swaps modes, calls `cli_brain.respond`, mirrors chat/bubble output, and pushes dialogues. | `cli_brain`, `avatar_client`, `_emit_chat`, `_emit_bubble`, `_dispatch_dialogue`, `_mode_lock` | `AgentCore.handle_cli_request()` should handle sanitizing + Gemini call; runner retains mode switching + dialogue dispatch triggers. |
| `_submit_cli_prompt` – `shimeji_dual_mode_agent.py:L1150-L1175` | Validates/sanitizes user input then schedules `_process_cli_prompt`. | `InputSanitizer`, `_loop`, `_emit_chat` | Keep in runner (UI callback) but let AgentCore expose a reusable sanitizer helper so other frontends reuse identical checks. |

_Note:_ `_execute_decision()` (L1056-L1070) already delegates to `DecisionExecutor`, so we keep it runner-side for now; AgentCore simply calls into it.

## Proposed AgentCore API (Phase 1)

```python
class AgentCore:
    def __init__(..., proactive_brain, memory, emotions, metrics, decision_executor,
                 context_manager, avatar_client, ui_event_sink, process_pool):
        ...

    async def proactive_cycle(self, *, context_snapshot):
        """Return next interval after running Gemini + decision executor."""

    async def handle_critical_alert(self, alert):
        """Wrap rate limiting + proactive decision triggered by system alerts."""

    async def handle_cli_request(self, prompt, *, mode_switcher, dialogue_dispatch):
        """Full CLI path used by server + UI sinks."""

    async def run_vision_probe(self, *, permission_manager, tools):
        """Capture screenshot, call Gemini Vision, merge context, and surface errors."""

    async def resolve_detected_error(self, error_text, *, on_alert_state):
        """Generate remediation plan via CLI brain and route UI updates."""
```

Runner responsibilities shrink to:
- Scheduling loops (`asyncio.create_task`),
- Feeding context snapshots or callbacks into AgentCore,
- Updating UI state (`_transition_mascot_state`, `_emit_anchor_update`),
- Managing process/permission lifecycles.

## Extraction Sequence

1. **Constructor refactor**: pass `proactive_brain`, `memory`, `emotions`, `_metrics`, `_decision_executor`, `_event_bus`, `_recent_actions`, and context accessor callbacks into `AgentCore`. Introduce a light `AgentCoreConfig` dataclass so tests can stub collaborators easily.
2. **Proactive loop migration**:
   - Move decision-making + metrics tracking into `AgentCore.proactive_cycle()`.
   - `DualModeAgent._proactive_loop()` reduces to context-change waiting + `interval = await self.core.proactive_cycle(...)`.
3. **System alert path**:
   - Transfer rate limiting cache + decision execution helper into AgentCore.
   - Runner’s `_on_system_alert` simply schedules `self.core.handle_critical_alert(alert)`.
4. **Vision + error helper**:
   - Fold `_vision_analysis_loop` and `_handle_detected_error` into AgentCore methods that receive callbacks for context merge + mascot state transitions.
   - Runner now only wires permission manager + screenshot interval and handles task lifecycle.
5. **CLI orchestration**:
   - Expand AgentCore to expose `handle_cli_request` used by `_submit_cli_prompt` and `InvocationServer` so non-UI callers reuse the same flow.

## Open Questions / Risks

- **Process pool ownership**: AgentCore currently only reads the executor for vision analysis. Once the proactive loop moves over, confirm no other module mutates `_process_pool` unexpectedly.
- **Testing**: New AgentCore APIs need dedicated unit tests mirroring existing integration checks (`tests/integration/test_agent_workflow.py`). Plan to add fixtures that stub context snapshots + decision executor outputs.
- **Permission manager access**: Vision probe currently imports `PermissionManager` inline. After extraction we should inject it to avoid circular imports.
- **State transitions**: Mascot state changes (`_transition_mascot_state`) touch PySide. AgentCore should receive callbacks instead of importing Qt directly.

Completing the above steps aligns AgentCore with LAP’s goal: brains (Gemini, memory, reasoning) live in one module, while `DualModeAgent` becomes a thin orchestrator that can be reused by other frontends or services.
