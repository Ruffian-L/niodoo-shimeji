"""Decision execution logic extracted from DualModeAgent."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Callable, Dict, TYPE_CHECKING

from modules.brains.shared import ProactiveDecision
from modules.productivity_tools import ProductivityTools

if TYPE_CHECKING:
    from shimeji_dual_mode_agent import DualModeAgent

LOGGER = logging.getLogger(__name__)


class DecisionExecutor:
    """Executes proactive decisions using a handler registry pattern."""
    
    def __init__(self, agent: "DualModeAgent"):
        self.agent = agent
        self._handlers: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], int]] = {
            "set_behavior": self._handle_set_behavior,
            "observe_and_wait": self._handle_observe_and_wait,
            "show_dialogue": self._handle_show_dialogue,
            "fetch_fact": self._handle_fetch_fact,
            "read_clipboard": self._handle_read_clipboard,
            "execute_bash": self._handle_execute_bash,
            "take_screenshot": self._handle_take_screenshot,
            "analyze_screenshot": self._handle_analyze_screenshot,
            "check_system_status": self._handle_check_system_status,
            "save_episodic_memory": self._handle_save_episodic_memory,
        }
    
    async def execute(self, decision: ProactiveDecision, context_snapshot: Dict[str, Any]) -> int:
        """Execute a decision and return the next interval."""
        action = decision.action
        args = decision.arguments
        timestamp = datetime.now(UTC).isoformat()
        self.agent._recent_actions.append(f"{timestamp}:{action}")
        self.agent.memory.record_action(action, args)
        
        handler = self._handlers.get(action)
        if handler:
            return await handler(args, context_snapshot)
        
        # Try plugin handlers
        for plugin in get_registered_plugins():
            try:
                plugin_declarations = plugin.get_function_declarations()
                plugin_actions = [decl.get("name") for decl in plugin_declarations]
                if action in plugin_actions:
                    await plugin.execute(action, args)
                    return self.agent._reaction_interval
            except Exception as exc:
                LOGGER.warning("Plugin %s failed to execute action %s: %s", plugin.__class__.__name__, action, exc)
        
        LOGGER.warning("Unknown proactive action '%s'; defaulting to standard interval", action)
        self.agent._dispatch_dialogue()
        return self.agent._proactive_interval
    
    async def _handle_set_behavior(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle set_behavior action."""
        behaviour = args.get("behavior_name") or "Idle"
        mascot_id = self.agent.desktop_controller.ensure_mascot()
        if mascot_id is None:
            LOGGER.debug("Deferring behaviour '%s' because no mascot is active", behaviour)
            self.agent.desktop_controller.wait_for_mascot(timeout=5.0)
            return self.agent._reaction_interval
        if self.agent.desktop_controller.set_behavior(behaviour, mascot_id=mascot_id):
            self.agent.emotions.on_behavior(behaviour)
            LOGGER.info("Proactive behavior triggered: %s", behaviour)
            # Publish behavior change event
            from modules.event_bus import EventType
            self.agent._event_bus.publish(EventType.BEHAVIOR_CHANGED, {"behavior": behaviour, "mascot_id": mascot_id})
        return self.agent._proactive_interval
    
    async def _handle_observe_and_wait(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle observe_and_wait action."""
        wait = int(args.get("duration_seconds", self.agent._proactive_interval))
        wait = max(1, min(wait, 300))
        LOGGER.debug("Observe-and-wait for %s seconds", wait)
        self.agent.emotions.on_observe_only(wait)
        self.agent._dispatch_dialogue()
        return wait
    
    async def _handle_show_dialogue(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle show_dialogue action."""
        text = args.get("text", "...")
        duration = int(args.get("duration_seconds", 6))
        self.agent.overlay.show_bubble_message("Shimeji", text, duration=duration)
        self.agent.emotions.on_dialogue()
        return self.agent._reaction_interval
    
    async def _handle_fetch_fact(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle fetch_fact action."""
        topic = args.get("topic")
        fact = self.agent._get_random_fact(topic)
        self.agent.overlay.show_bubble_message("Shimeji", fact, duration=8)
        return self.agent._reaction_interval
    
    async def _handle_read_clipboard(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle read_clipboard action."""
        clipboard_content = ProductivityTools.read_clipboard()
        if clipboard_content:
            self.agent.overlay.show_chat_message("Shimeji", f"You copied: {clipboard_content[:500]}")
        else:
            self.agent.overlay.show_bubble_message("Shimeji", "Clipboard is empty!", duration=3)
        return self.agent._reaction_interval
    
    async def _handle_execute_bash(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle execute_bash action."""
        command = args.get("command", "")
        if command:
            result = ProductivityTools.execute_bash_command(command)
            output = result.get("stdout", result.get("error", "No output"))
            self.agent.overlay.show_chat_message("Shimeji", f"Command: `{command}`\n\nOutput:\n```\n{output[:1000]}\n```")
        return self.agent._reaction_interval
    
    async def _handle_take_screenshot(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle take_screenshot action."""
        screenshot_path = ProductivityTools.take_screenshot()
        if screenshot_path:
            self.agent.overlay.show_bubble_message("Shimeji", f"Screenshot saved! Let me analyze it...", duration=5)
            LOGGER.info("Screenshot captured: %s", screenshot_path)
        else:
            self.agent.overlay.show_bubble_message("Shimeji", "Couldn't take screenshot!", duration=3)
        return self.agent._reaction_interval
    
    async def _handle_analyze_screenshot(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle analyze_screenshot action."""
        screenshot_path = ProductivityTools.take_screenshot()
        if not screenshot_path:
            self.agent.overlay.show_bubble_message("Shimeji", "Couldn't take screenshot!", duration=3)
            return self.agent._reaction_interval
        
        question = args.get("question", "What do you see in this screenshot? Describe what's on screen.")
        self.agent.overlay.show_chat_message("Shimeji", "Analyzing screenshot... ⏳")
        self.agent.overlay.show_bubble_message("Shimeji", "Analyzing screenshot... ⏳", duration=3)
        
        try:
            analysis = await self.agent._analyze_image_with_vision(str(screenshot_path), question)
            if analysis:
                self.agent.overlay.show_chat_message("Shimeji", f"Screenshot Analysis:\n{analysis}")
            else:
                self.agent.overlay.show_chat_message("Shimeji", "Couldn't analyze screenshot.")
        except Exception as exc:
            LOGGER.error("Vision analysis failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", "Analysis failed. Please try again.")
            self.agent.overlay.show_bubble_message("Shimeji", "Analysis failed!", duration=5)
        return self.agent._reaction_interval
    
    async def _handle_check_system_status(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle check_system_status action."""
        battery = ProductivityTools.get_battery_status()
        cpu = ProductivityTools.get_cpu_usage()
        memory = ProductivityTools.get_memory_usage()
        
        status_parts = []
        if battery.get("percentage"):
            status_parts.append(f"Battery: {battery['percentage']} ({battery.get('state', 'unknown')})")
        if cpu is not None:
            status_parts.append(f"CPU: {cpu:.1f}%")
        if memory:
            status_parts.append(f"RAM: {memory['used_percent']}% used")
        
        status_msg = "\n".join(status_parts) if status_parts else "System status unavailable"
        self.agent.overlay.show_chat_message("Shimeji", f"System Status:\n{status_msg}")
        
        # React to low battery
        if battery.get("percentage"):
            pct = int(battery["percentage"].rstrip("%"))
            if pct < 20 and battery.get("state") != "charging":
                self.agent.overlay.show_bubble_message("Shimeji", f"Hey! Battery is at {pct}%! Plug in!", duration=8)
        
        return self.agent._reaction_interval
    
    async def _handle_save_episodic_memory(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle save_episodic_memory action."""
        fact = args.get("fact")
        metadata_raw = args.get("metadata")
        metadata = None
        if isinstance(metadata_raw, str) and metadata_raw.strip():
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {"note": metadata_raw}
        if fact:
            enriched_metadata = metadata or {}
            enriched_metadata.setdefault("context", context)
            self.agent.memory.save_fact(fact, enriched_metadata)
        self.agent._dispatch_dialogue()
        return self.agent._reaction_interval

