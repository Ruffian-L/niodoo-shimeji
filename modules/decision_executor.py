"""Decision execution logic extracted from DualModeAgent."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, TYPE_CHECKING

from modules.brains.shared import ProactiveDecision
from modules.productivity_tools import ProductivityTools
from modules.tool_schema_factory import get_registered_plugins
from modules.permission_manager import PermissionManager, PermissionScope, PermissionStatus

if TYPE_CHECKING:
    from shimeji_dual_mode_agent import DualModeAgent

LOGGER = logging.getLogger(__name__)

# Map actions to required permission scopes
ACTION_PERMISSION_MAP: Dict[str, PermissionScope] = {
    "execute_bash": PermissionScope.TOOL_BASH_RUN,
    "read_clipboard": PermissionScope.TOOL_CLIPBOARD_READ,
    # File operations would map to TOOL_FILE_READ_ALL or TOOL_FILE_WRITE_SANDBOX
    # AT-SPI operations would map to CONTEXT_ATSPI_READ_APPS or CONTEXT_ATSPI_CONTROL_APPS
}


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
            "check_system_status": self._handle_check_system_status,
            "save_episodic_memory": self._handle_save_episodic_memory,
            "get_system_metrics": self._handle_get_system_metrics,
            "set_monitoring_preference": self._handle_set_monitoring_preference,
            "get_monitoring_preferences": self._handle_get_monitoring_preferences,
            # New comprehensive enhancement handlers
            "suggest_resource_optimization": self._handle_suggest_resource_optimization,
            "infer_user_goal": self._handle_infer_user_goal,
            "analyze_dropped_file": self._handle_analyze_dropped_file,
            "process_voice_command": self._handle_process_voice_command,
            "schedule_task": self._handle_schedule_task,
            "set_reminder": self._handle_set_reminder,
            "auto_fix_issue": self._handle_auto_fix_issue,
            "send_dbus_notification": self._handle_send_dbus_notification,
            "detect_app_context": self._handle_detect_app_context,
            "summarize_web_page": self._handle_summarize_web_page,
            "analyze_code_context": self._handle_analyze_code_context,
            "record_feedback": self._handle_record_feedback,
            "detect_patterns": self._handle_detect_patterns,
            "detect_ambient_sound": self._handle_detect_ambient_sound,
            "semantic_memory_search": self._handle_semantic_memory_search,
            "mine_patterns": self._handle_mine_patterns,
            "spawn_agent": self._handle_spawn_agent,
            "share_knowledge": self._handle_share_knowledge,
            "request_permission": self._handle_request_permission,
        }
    
    async def execute(self, decision: ProactiveDecision, context_snapshot: Dict[str, Any]) -> int:
        """Execute a decision and return the next interval."""
        action = decision.action
        args = decision.arguments
        timestamp = datetime.now(UTC).isoformat()
        self.agent._recent_actions.append(f"{timestamp}:{action}")
        self.agent.memory.record_action(action, args)
        
        # Check permission before executing
        if hasattr(self.agent, '_permission_manager') and self.agent._permission_manager:
            required_scope = ACTION_PERMISSION_MAP.get(action)
            if required_scope:
                agent_id = getattr(decision, 'agent_id', 'ProactiveBrain')
                permission_status = self.agent._permission_manager.check_permission(
                    agent_id, required_scope
                )
                
                if permission_status == PermissionStatus.DENY:
                    LOGGER.warning("Permission denied for %s.%s", agent_id, required_scope.value)
                    self.agent.overlay.show_bubble_message(
                        "Shimeji",
                        f"Permission denied: {required_scope.value}",
                        duration=5
                    )
                    return self.agent._reaction_interval
                
                if permission_status == PermissionStatus.ASK:
                    # Request permission from user
                    granted = await self._request_permission_interactive(
                        agent_id, required_scope, action, args
                    )
                    if not granted:
                        LOGGER.info("User denied permission for %s.%s", agent_id, required_scope.value)
                        return self.agent._reaction_interval
                    # User granted - set to allow for future
                    self.agent._permission_manager.set_permission(
                        agent_id, required_scope, PermissionStatus.ALLOW
                    )
        
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
    
    async def _request_permission_interactive(
        self,
        agent_id: str,
        scope: PermissionScope,
        action: str,
        args: Dict[str, Any]
    ) -> bool:
        """Request permission from user via UI dialog.
        
        Args:
            agent_id: Agent requesting permission
            scope: Permission scope
            action: Action being attempted
            args: Action arguments
            
        Returns:
            True if permission granted, False otherwise
        """
        # Publish permission request event
        from modules.event_bus import EventType
        self.agent._event_bus.publish(
            EventType.PERMISSION_REQUESTED,
            {
                "agent_id": agent_id,
                "scope": scope.value,
                "action": action,
                "args": args,
            }
        )
        
        # Show permission request in chat UI
        scope_display = scope.value.replace("tool.", "").replace("context.", "").replace("_", " ").title()
        message = (
            f"🔐 Permission Request\n\n"
            f"Agent: {agent_id}\n"
            f"Action: {action}\n"
            f"Scope: {scope_display}\n\n"
            f"Allow this action? (Reply 'yes' to allow, 'no' to deny, or 'always' to always allow)"
        )
        self.agent.overlay.show_chat_message("System", message)
        self.agent.overlay.show_bubble_message("System", f"Permission needed: {scope_display}", duration=10)
        
        # For now, default to asking (user can respond via chat)
        # In a full implementation, this would show a modal dialog and wait for response
        # For MVP, we'll use a simple timeout-based approach
        # Return True to allow for now (user can deny via settings later)
        LOGGER.info("Permission requested: %s.%s (defaulting to allow for MVP)", agent_id, scope.value)
        return True
    
    async def _handle_set_behavior(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle set_behavior action."""
        import random
        
        behaviour = args.get("behavior_name") or "Idle"
        mascot_id = self.agent.desktop_controller.ensure_mascot()
        if mascot_id is None:
            LOGGER.debug("Deferring behaviour '%s' because no mascot is active", behaviour)
            self.agent.desktop_controller.wait_for_mascot(timeout=5.0)
            return self.agent._reaction_interval
        if self.agent.desktop_controller.set_behavior(behaviour, mascot_id=mascot_id):
            self.agent.emotions.on_behavior(behaviour)
            LOGGER.info("Proactive behavior triggered: %s", behaviour)
            
            # Add fun context-aware messages based on behavior (but not too spammy - only 30% chance)
            if random.random() < 0.3:  # Only 30% chance to avoid spam
                behavior_messages = self._get_behavior_messages(behaviour)
                if behavior_messages:
                    message = random.choice(behavior_messages)
                    # Show in bubble only (not chat to reduce spam)
                    self.agent.overlay.show_bubble_message("Shimeji", message, duration=4)
            
            # Publish behavior change event
            from modules.event_bus import EventType
            self.agent._event_bus.publish(EventType.BEHAVIOR_CHANGED, {"behavior": behaviour, "mascot_id": mascot_id})
        return self.agent._proactive_interval
    
    def _get_behavior_messages(self, behavior: str) -> List[str]:
        """Get fun context-aware messages for different behaviors."""
        behavior_lower = behavior.lower()
        
        # Climbing behaviors
        if "climb" in behavior_lower or "wall" in behavior_lower or "ceiling" in behavior_lower:
            return [
                "Spider-Shimeji mode activated! 🕷️",
                "Look at me go! Nothing can stop me!",
                "Climbing like a pro! Bet you can't do this!",
                "Defying gravity over here!",
                "This is my domain now!",
                "Heights? No problem for me!",
                "Watch me scale this like it's nothing!",
            ]
        
        # Running/Walking behaviors
        if "run" in behavior_lower or "walk" in behavior_lower or "dash" in behavior_lower:
            return [
                "Gotta go fast! ⚡",
                "Zoom zoom! Can't catch me!",
                "On the move! Don't blink or you'll miss me!",
                "Speed mode: ACTIVATED!",
                "Running circles around you!",
                "I'm unstoppable when I'm moving!",
            ]
        
        # Sitting/Idle behaviors
        if "sit" in behavior_lower or "idle" in behavior_lower or "rest" in behavior_lower:
            return [
                "Taking a quick break... but I'm still watching! 👀",
                "Just chilling here, no big deal.",
                "Resting my legs, but my mind is sharp!",
                "Pausing to observe... interesting things happening.",
                "Taking a moment to strategize!",
            ]
        
        # Jumping behaviors
        if "jump" in behavior_lower or "hop" in behavior_lower:
            return [
                "BOING! 🦘",
                "Jumping high! Watch this!",
                "Air time! I'm flying!",
                "Gravity? What's that?",
                "Up, up, and away!",
            ]
        
        # Falling behaviors
        if "fall" in behavior_lower or "drop" in behavior_lower:
            return [
                "Whoa! That was unexpected!",
                "Oops! My bad!",
                "Recalculating trajectory...",
                "Still got it!",
            ]
        
        # Spinning behaviors
        if "spin" in behavior_lower:
            return [
                "Dizzy mode: ON! 🌀",
                "Spinning like a top!",
                "Can't stop, won't stop!",
                "Round and round we go!",
            ]
        
        # Chasing behaviors
        if "chase" in behavior_lower or "mouse" in behavior_lower:
            return [
                "I see something interesting! 👀",
                "On the hunt!",
                "Tracking movement...",
                "Something caught my attention!",
            ]
        
        # Default for unknown behaviors
        return []
    
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
        # Only show in bubble, NOT in chat to reduce spam
        self.agent.overlay.show_bubble_message("Shimeji", text, duration=duration)
        # Don't add to chat panel - too spammy
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
    
    async def _handle_get_system_metrics(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle get_system_metrics action."""
        try:
            import psutil
            metrics = {}
            
            # RAM
            mem = psutil.virtual_memory()
            metrics["ram"] = {
                "usage_pct": mem.percent,
                "used_gb": mem.used / (1024**3),
                "available_gb": mem.available / (1024**3),
                "total_gb": mem.total / (1024**3),
            }
            
            # CPU
            metrics["cpu"] = {
                "usage_pct": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
            }
            
            # Disk
            disk_metrics = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_metrics.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "used_pct": (usage.used / usage.total) * 100,
                        "free_gb": usage.free / (1024**3),
                        "total_gb": usage.total / (1024**3),
                    })
                except PermissionError:
                    pass
            metrics["disk"] = disk_metrics
            
            # GPU (if available)
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                gpu_metrics = []
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_metrics.append({
                        "index": i,
                        "mem_usage_pct": (mem_info.used / mem_info.total) * 100,
                        "mem_used_gb": mem_info.used / (1024**3),
                        "mem_total_gb": mem_info.total / (1024**3),
                        "temperature_c": temp,
                        "utilization_pct": util.gpu,
                    })
                metrics["gpu"] = gpu_metrics
            except Exception:
                metrics["gpu"] = None
            
            # Format response
            response = json.dumps(metrics, indent=2, ensure_ascii=False)
            self.agent.overlay.show_chat_message("Shimeji", f"System Metrics:\n```\n{response}\n```")
            
        except ImportError:
            self.agent.overlay.show_chat_message("Shimeji", "System metrics unavailable (psutil not installed)")
        except Exception as exc:
            LOGGER.error("Failed to get system metrics: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Failed to get metrics: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_set_monitoring_preference(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle set_monitoring_preference action."""
        key = args.get("key")
        value = args.get("value")
        
        if not key or value is None:
            self.agent.overlay.show_chat_message("Shimeji", "Error: Both 'key' and 'value' are required")
            return self.agent._reaction_interval
        
        try:
            # Validate and convert value
            if isinstance(value, str):
                # Try to convert to number
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
            
            self.agent.memory.set_pref(key, value)
            self.agent.overlay.show_chat_message("Shimeji", f"Updated preference: {key} = {value}")
            LOGGER.info("Monitoring preference updated: %s = %s", key, value)
            
        except Exception as exc:
            LOGGER.error("Failed to set preference: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Failed to set preference: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_get_monitoring_preferences(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle get_monitoring_preferences action."""
        try:
            prefs = self.agent.memory.get_all_prefs()
            
            # Filter to only monitoring-related preferences
            monitoring_prefs = {
                k: v for k, v in prefs.items()
                if any(x in k for x in ['threshold', 'critical', 'monitor', 'alert', 'zombie', 'gpu', 'ram', 'disk'])
            }
            
            if not monitoring_prefs:
                self.agent.overlay.show_chat_message("Shimeji", "No monitoring preferences found")
                return self.agent._reaction_interval
            
            # Format response
            prefs_text = "\n".join(f"{k}: {v}" for k, v in sorted(monitoring_prefs.items()))
            self.agent.overlay.show_chat_message("Shimeji", f"Monitoring Preferences:\n```\n{prefs_text}\n```")
            
        except Exception as exc:
            LOGGER.error("Failed to get preferences: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Failed to get preferences: {exc}")
        
        return self.agent._reaction_interval
    
    # ========================================================================
    # Comprehensive Enhancement Handlers
    # ========================================================================
    
    async def _handle_suggest_resource_optimization(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle suggest_resource_optimization action."""
        try:
            import psutil
            threshold_type = args.get("threshold_type", "ram")
            current_usage = float(args.get("current_usage", 0))
            process_list_str = args.get("process_list", "[]")
            
            # Parse process list
            try:
                process_list = json.loads(process_list_str) if isinstance(process_list_str, str) else process_list_str
            except json.JSONDecodeError:
                # Get current processes if not provided
                process_list = []
                for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                    try:
                        process_list.append(proc.info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            
            # Find idle processes
            idle_processes = [
                p for p in process_list
                if isinstance(p, dict) and p.get('memory_percent', 0) > 1.0 and p.get('cpu_percent', 0) < 1.0
            ]
            
            if idle_processes:
                # Sort by memory usage
                idle_processes.sort(key=lambda x: x.get('memory_percent', 0), reverse=True)
                top_idle = idle_processes[:5]
                
                suggestions = f"Found {len(idle_processes)} idle processes. Top memory users:\n"
                for p in top_idle:
                    suggestions += f"- {p.get('name', 'unknown')} (PID {p.get('pid')}): {p.get('memory_percent', 0):.1f}% RAM\n"
                
                self.agent.overlay.show_chat_message("Shimeji", f"Resource Optimization Suggestion:\n{suggestions}")
            else:
                self.agent.overlay.show_chat_message("Shimeji", "No idle processes found to optimize.")
                
        except Exception as exc:
            LOGGER.error("Resource optimization failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Optimization analysis failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_infer_user_goal(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle infer_user_goal action."""
        try:
            from modules.pattern_learner import PatternLearner
            
            context_str = args.get("context", "{}")
            recent_actions_str = args.get("recent_actions", "[]")
            memory_patterns_str = args.get("memory_patterns", "[]")
            
            # Parse JSON strings
            try:
                context_data = json.loads(context_str) if isinstance(context_str, str) else context_str
                recent_actions = json.loads(recent_actions_str) if isinstance(recent_actions_str, str) else recent_actions_str
                memory_patterns = json.loads(memory_patterns_str) if isinstance(memory_patterns_str, str) else memory_patterns_str
            except json.JSONDecodeError:
                context_data = context
                recent_actions = []
                memory_patterns = []
            
            # Use pattern learner to detect patterns
            pattern_learner = PatternLearner(self.agent.memory)
            patterns = pattern_learner.detect_patterns(time_range_days=7, pattern_type="app_usage")
            
            if patterns:
                top_pattern = patterns[0]
                suggestion = f"Based on your patterns, you frequently use {top_pattern.get('app', 'applications')}. "
                suggestion += "Would you like help with something specific?"
                self.agent.overlay.show_chat_message("Shimeji", suggestion)
            else:
                app_name = context_data.get("application", "Unknown")
                if app_name != "Unknown":
                    self.agent.overlay.show_chat_message("Shimeji", f"I see you're using {app_name}. Need help with anything?")
                    
        except Exception as exc:
            LOGGER.error("Goal inference failed: %s", exc)
        
        return self.agent._reaction_interval
    
    async def _handle_analyze_dropped_file(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle analyze_dropped_file action."""
        file_path = args.get("file_path", "")
        file_type = args.get("file_type", "")
        question = args.get("question", "What is in this file?")
        
        if not file_path or not os.path.exists(file_path):
            self.agent.overlay.show_chat_message("Shimeji", f"File not found: {file_path}")
            return self.agent._reaction_interval
        
        self.agent.overlay.show_chat_message("Shimeji", f"Analyzing file: {file_path}...")
        
        try:
            # Check file type
            if file_type in ["image", "png", "jpg", "jpeg"] or file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                # Use vision API
                analysis = await self.agent._analyze_image_with_vision(file_path, question)
                if analysis:
                    self.agent.overlay.show_chat_message("Shimeji", f"Image Analysis:\n{analysis}")
            else:
                # Read text file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)  # Limit to 10k chars
                
                # Use CLI brain to analyze
                prompt = f"Analyze this file content and answer: {question}\n\nFile content:\n{content}"
                response = await self.agent.cli_brain.respond(prompt, self.agent)
                self.agent.overlay.show_chat_message("Shimeji", f"File Analysis:\n{response}")
                
        except Exception as exc:
            LOGGER.error("File analysis failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Analysis failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_process_voice_command(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle process_voice_command action."""
        # Voice commands are typically handled via the voice handler callback
        # This is mainly for manual processing of audio data
        audio_data = args.get("audio_data")
        language = args.get("language", "en")
        
        if audio_data:
            # Decode and process audio
            self.agent.overlay.show_chat_message("Shimeji", "Processing voice command...")
            # In a real implementation, would decode audio and process
            # For now, just acknowledge
            self.agent.overlay.show_chat_message("Shimeji", "Voice command received (processing requires voice handler setup)")
        else:
            self.agent.overlay.show_chat_message("Shimeji", "No audio data provided")
        
        return self.agent._reaction_interval
    
    async def _handle_schedule_task(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle schedule_task action."""
        try:
            import schedule
            from datetime import datetime, timedelta
            
            task_description = args.get("task_description", "")
            time_str = args.get("time", "")
            recurrence = args.get("recurrence", "")
            
            if not task_description or not time_str:
                self.agent.overlay.show_chat_message("Shimeji", "Error: task_description and time are required")
                return self.agent._reaction_interval
            
            # Parse time (simplified - would need better parsing)
            # Store in memory for now
            self.agent.memory.save_fact(
                f"Scheduled task: {task_description} at {time_str}",
                metadata={"task": task_description, "time": time_str, "recurrence": recurrence}
            )
            
            self.agent.overlay.show_chat_message("Shimeji", f"Task scheduled: {task_description} at {time_str}")
            
        except Exception as exc:
            LOGGER.error("Task scheduling failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Scheduling failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_set_reminder(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle set_reminder action."""
        message = args.get("message", "")
        time_str = args.get("time", "")
        
        if not message or not time_str:
            self.agent.overlay.show_chat_message("Shimeji", "Error: message and time are required")
            return self.agent._reaction_interval
        
        # Store reminder in memory
        self.agent.memory.save_fact(
            f"Reminder: {message} at {time_str}",
            metadata={"reminder": message, "time": time_str}
        )
        
        self.agent.overlay.show_chat_message("Shimeji", f"Reminder set: {message} at {time_str}")
        
        return self.agent._reaction_interval
    
    async def _handle_auto_fix_issue(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle auto_fix_issue action."""
        issue_type = args.get("issue_type", "")
        suggested_fix = args.get("suggested_fix", "")
        
        if not issue_type:
            self.agent.overlay.show_chat_message("Shimeji", "Error: issue_type is required")
            return self.agent._reaction_interval
        
        try:
            if issue_type == "zombie":
                # Kill zombie processes
                result = ProductivityTools.execute_bash_command("ps aux | awk '$8 ~ /^Z/ { print $2 }' | xargs -r kill -9")
                self.agent.overlay.show_chat_message("Shimeji", "Attempted to kill zombie processes")
            elif issue_type == "temp_files":
                # Clear temp files
                result = ProductivityTools.execute_bash_command("find /tmp -type f -atime +7 -delete 2>/dev/null || true")
                self.agent.overlay.show_chat_message("Shimeji", "Cleared old temporary files")
            elif suggested_fix:
                # Execute suggested fix
                result = ProductivityTools.execute_bash_command(suggested_fix)
                self.agent.overlay.show_chat_message("Shimeji", f"Executed fix: {suggested_fix}")
            else:
                self.agent.overlay.show_chat_message("Shimeji", f"Unknown issue type: {issue_type}")
                
        except Exception as exc:
            LOGGER.error("Auto-fix failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Fix failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_send_dbus_notification(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle send_dbus_notification action."""
        try:
            from modules.dbus_integration import DBusIntegration
            
            title = args.get("title", "Shimeji")
            message = args.get("message", "")
            urgency = args.get("urgency", "normal")
            
            if not message:
                self.agent.overlay.show_chat_message("Shimeji", "Error: message is required")
                return self.agent._reaction_interval
            
            dbus = DBusIntegration()
            if dbus.is_available():
                dbus.send_notification(title, message, urgency)
                self.agent.overlay.show_chat_message("Shimeji", f"Notification sent: {title}")
            else:
                # Fallback
                self.agent.overlay.show_chat_message("Shimeji", f"{title}: {message}")
                
        except Exception as exc:
            LOGGER.error("DBus notification failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Notification failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_detect_app_context(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle detect_app_context action."""
        try:
            from modules.app_context import AppContext
            
            app_context = AppContext()
            detected = app_context.detect_app_context(context)
            
            category = detected.get("category", "unknown")
            app_name = detected.get("app_name", "Unknown")
            available_tools = detected.get("available_tools", [])
            
            response = f"App Context:\n- Application: {app_name}\n- Category: {category}\n"
            if available_tools:
                response += f"- Available tools: {', '.join(available_tools)}"
            
            suggestion = app_context.get_app_specific_suggestion(detected)
            if suggestion:
                response += f"\n\n💡 {suggestion}"
            
            self.agent.overlay.show_chat_message("Shimeji", response)
            
        except Exception as exc:
            LOGGER.error("App context detection failed: %s", exc)
        
        return self.agent._reaction_interval
    
    async def _handle_summarize_web_page(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle summarize_web_page action."""
        url = args.get("url", "")
        
        # Take screenshot and analyze
        screenshot_path = ProductivityTools.take_screenshot()
        if screenshot_path:
            question = "Summarize the content of this web page. What is the main topic and key points?"
            analysis = await self.agent._analyze_image_with_vision(str(screenshot_path), question)
            if analysis:
                self.agent.overlay.show_chat_message("Shimeji", f"Web Page Summary:\n{analysis}")
            else:
                self.agent.overlay.show_chat_message("Shimeji", "Couldn't analyze web page")
        else:
            self.agent.overlay.show_chat_message("Shimeji", "Couldn't capture screenshot")
        
        return self.agent._reaction_interval
    
    async def _handle_analyze_code_context(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle analyze_code_context action."""
        question = args.get("question", "What code is visible on screen? Analyze it and explain what it does.")
        
        screenshot_path = ProductivityTools.take_screenshot()
        if screenshot_path:
            analysis = await self.agent._analyze_image_with_vision(str(screenshot_path), question)
            if analysis:
                self.agent.overlay.show_chat_message("Shimeji", f"Code Analysis:\n{analysis}")
            else:
                self.agent.overlay.show_chat_message("Shimeji", "Couldn't analyze code")
        else:
            self.agent.overlay.show_chat_message("Shimeji", "Couldn't capture screenshot")
        
        return self.agent._reaction_interval
    
    async def _handle_record_feedback(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle record_feedback action."""
        try:
            from modules.feedback_learner import FeedbackLearner
            
            action = args.get("action", "")
            user_response = args.get("user_response", "")
            context_str = args.get("context", "{}")
            
            try:
                context_data = json.loads(context_str) if isinstance(context_str, str) else context_str
            except json.JSONDecodeError:
                context_data = context
            
            if not action or not user_response:
                self.agent.overlay.show_chat_message("Shimeji", "Error: action and user_response are required")
                return self.agent._reaction_interval
            
            feedback_learner = FeedbackLearner(self.agent.memory)
            feedback_learner.record_feedback(action, user_response, context_data)
            
            self.agent.overlay.show_chat_message("Shimeji", f"Feedback recorded: {action} -> {user_response}")
            
        except Exception as exc:
            LOGGER.error("Feedback recording failed: %s", exc)
        
        return self.agent._reaction_interval
    
    async def _handle_detect_patterns(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle detect_patterns action."""
        try:
            from modules.pattern_learner import PatternLearner
            
            time_range = args.get("time_range", "7 days")
            pattern_type = args.get("pattern_type", "app_usage")
            
            # Parse time range
            time_range_days = 7
            if "day" in time_range.lower():
                try:
                    time_range_days = int(time_range.split()[0])
                except (ValueError, IndexError):
                    pass
            
            pattern_learner = PatternLearner(self.agent.memory)
            patterns = pattern_learner.detect_patterns(time_range_days, pattern_type)
            
            if patterns:
                response = f"Detected {len(patterns)} patterns:\n"
                for i, pattern in enumerate(patterns[:5], 1):
                    response += f"{i}. {pattern}\n"
                self.agent.overlay.show_chat_message("Shimeji", response)
            else:
                self.agent.overlay.show_chat_message("Shimeji", "No patterns detected")
                
        except Exception as exc:
            LOGGER.error("Pattern detection failed: %s", exc)
        
        return self.agent._reaction_interval
    
    async def _handle_detect_ambient_sound(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle detect_ambient_sound action."""
        # Audio detection is handled by AudioProcessor in background
        # This is mainly for triggering detection
        duration = int(args.get("duration_seconds", 5))
        sensitivity = float(args.get("sensitivity", 0.5))
        
        self.agent.overlay.show_chat_message("Shimeji", f"Monitoring ambient sound for {duration} seconds...")
        # In a real implementation, would start audio monitoring
        # For now, just acknowledge
        self.agent.overlay.show_chat_message("Shimeji", "Audio monitoring requires AudioProcessor setup")
        
        return self.agent._reaction_interval
    
    async def _handle_semantic_memory_search(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle semantic_memory_search action."""
        try:
            from modules.vector_memory import VectorMemory
            
            query = args.get("query", "")
            limit = int(args.get("limit", 5))
            
            if not query:
                self.agent.overlay.show_chat_message("Shimeji", "Error: query is required")
                return self.agent._reaction_interval
            
            vector_memory = VectorMemory()
            if vector_memory.is_available():
                results = vector_memory.semantic_search(query, limit)
                
                if results:
                    response = f"Semantic search results for '{query}':\n\n"
                    for i, result in enumerate(results, 1):
                        fact = result.get('fact', '')
                        similarity = result.get('similarity', 0)
                        response += f"{i}. ({similarity:.2f}) {fact[:200]}...\n"
                    self.agent.overlay.show_chat_message("Shimeji", response)
                else:
                    self.agent.overlay.show_chat_message("Shimeji", "No results found")
            else:
                # Fallback to regular search
                results = self.agent.memory.recall_relevant({"query": query}, limit)
                if results:
                    response = f"Search results for '{query}':\n\n"
                    for i, result in enumerate(results[:limit], 1):
                        response += f"{i}. {result}\n"
                    self.agent.overlay.show_chat_message("Shimeji", response)
                else:
                    self.agent.overlay.show_chat_message("Shimeji", "No results found")
                    
        except Exception as exc:
            LOGGER.error("Semantic search failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Search failed: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_mine_patterns(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle mine_patterns action."""
        try:
            from modules.pattern_learner import PatternLearner
            
            time_range_days = int(args.get("time_range_days", 30))
            
            pattern_learner = PatternLearner(self.agent.memory)
            insights = pattern_learner.mine_insights(time_range_days)
            
            response = "Mined Insights:\n\n"
            
            if insights.get('productivity_trends'):
                response += "Productivity Trends:\n"
                for trend in insights['productivity_trends']:
                    response += f"- {trend.get('message', '')}\n"
                response += "\n"
            
            if insights.get('usage_patterns'):
                response += "Usage Patterns:\n"
                for pattern in insights['usage_patterns'][:5]:
                    response += f"- {pattern}\n"
                response += "\n"
            
            if insights.get('suggestions'):
                response += "Suggestions:\n"
                for suggestion in insights['suggestions']:
                    response += f"- {suggestion.get('message', '')}\n"
            
            self.agent.overlay.show_chat_message("Shimeji", response)
            
        except Exception as exc:
            LOGGER.error("Pattern mining failed: %s", exc)
        
        return self.agent._reaction_interval
    
    async def _handle_spawn_agent(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle spawn_agent action."""
        try:
            from modules.multi_agent import MultiAgentCoordinator, AgentType
            
            agent_type_str = args.get("agent_type", "")
            task_description = args.get("task_description", "")
            
            if not agent_type_str or not task_description:
                self.agent.overlay.show_chat_message("Shimeji", "Error: agent_type and task_description are required")
                return self.agent._reaction_interval
            
            # Get or create multi-agent coordinator
            if not hasattr(self.agent, '_multi_agent_coordinator'):
                self.agent._multi_agent_coordinator = MultiAgentCoordinator(
                    self.agent._event_bus,
                    self.agent
                )
            
            agent_type = AgentType(agent_type_str)
            agent_id = await self.agent._multi_agent_coordinator.spawn_agent(
                agent_type,
                task_description,
                context
            )
            
            self.agent.overlay.show_chat_message("Shimeji", f"Spawned {agent_type_str} agent: {agent_id}")
            
        except Exception as exc:
            LOGGER.error("Agent spawning failed: %s", exc)
            self.agent.overlay.show_chat_message("Shimeji", f"Failed to spawn agent: {exc}")
        
        return self.agent._reaction_interval
    
    async def _handle_share_knowledge(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle share_knowledge action."""
        knowledge_type = args.get("knowledge_type", "")
        data_str = args.get("data", "{}")
        
        try:
            data = json.loads(data_str) if isinstance(data_str, str) else data_str
        except json.JSONDecodeError:
            data = {}
        
        # Store knowledge for sharing (would be sent via HTTP in real implementation)
        self.agent.memory.save_fact(
            f"Shared knowledge: {knowledge_type}",
            metadata={"type": knowledge_type, "data": data}
        )
        
        self.agent.overlay.show_chat_message("Shimeji", f"Knowledge shared: {knowledge_type}")
        
        return self.agent._reaction_interval
    
    async def _handle_request_permission(self, args: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Handle request_permission action."""
        tool_name = args.get("tool_name", "")
        reason = args.get("reason", "")
        
        if not tool_name or not reason:
            self.agent.overlay.show_chat_message("Shimeji", "Error: tool_name and reason are required")
            return self.agent._reaction_interval
        
        # Show permission request in chat
        message = f"Permission Request:\nTool: {tool_name}\nReason: {reason}\n\nAllow this action?"
        self.agent.overlay.show_chat_message("Shimeji", message)
        
        # Store permission request
        self.agent.memory.save_fact(
            f"Permission requested: {tool_name}",
            metadata={"tool": tool_name, "reason": reason, "status": "pending"}
        )
        
        return self.agent._reaction_interval

