"""Dynamic Gemini tool schema generation for Shimeji behaviours."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Sequence

from modules.plugin_base import ToolPlugin

LOGGER = logging.getLogger(__name__)

# Global plugin registry
PLUGINS: List[ToolPlugin] = []


def register_plugin(plugin: ToolPlugin) -> None:
    """Register a tool plugin.
    
    Args:
        plugin: The plugin instance to register
    """
    PLUGINS.append(plugin)
    LOGGER.info("Registered plugin: %s", plugin.__class__.__name__)


def get_registered_plugins() -> List[ToolPlugin]:
    """Get all registered plugins.
    
    Returns:
        List of registered plugin instances
    """
    return PLUGINS.copy()
NAMESPACE = {"m": "http://www.group-finity.com/Mascot"}
DEFAULT_ACTION_PATH = (
    Path(__file__).resolve().parent.parent / "Shijima-Qt" / "DefaultMascot" / "actions.xml"
)
FALLBACK_BEHAVIOURS = ["Stand", "Walk", "Run", "Sit", "Fall", "Dash"]
EXCLUDED_KEYWORDS = {"multiply", "spawn", "split"}


def _resolve_path(candidate: Path) -> Path:
    return candidate.expanduser().resolve()


def load_behavior_names(action_paths: Iterable[Path] | None = None) -> List[str]:
    """Discover behaviour names from Shimeji actions.xml files."""

    paths = list(action_paths or [DEFAULT_ACTION_PATH])
    behaviours: List[str] = []

    for path in paths:
        resolved = _resolve_path(path)
        if not resolved.exists():
            LOGGER.debug("actions.xml not found at %s", resolved)
            continue
        try:
            tree = ET.parse(resolved)
            root = tree.getroot()
            for action in root.findall(".//m:Action", NAMESPACE):
                name = action.get("Name")
                action_type = action.get("Type", "")
                if not name:
                    continue
                # Skip embedded actions that are not user-triggerable.
                if action_type.lower() == "embedded":
                    continue
                behaviours.append(name)
        except ET.ParseError as exc:
            LOGGER.warning("Failed to parse %s: %s", resolved, exc)

    if not behaviours:
        LOGGER.warning("No behaviours discovered; falling back to defaults")
        behaviours = FALLBACK_BEHAVIOURS.copy()

    # Deduplicate while preserving order.
    seen = set()
    ordered: List[str] = []
    for behaviour in behaviours:
        key = behaviour.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    ordered = [
        name
        for name in ordered
        if not any(keyword in name.casefold() for keyword in EXCLUDED_KEYWORDS)
    ]
    return ordered


def build_proactive_function_declarations(
    behaviour_names: Sequence[str],
    include_spawn: bool = False,
) -> List[dict]:
    """Construct Gemini function schemas incorporating behaviour enumerations and plugins."""

    behaviour_enum = list(behaviour_names) if behaviour_names else FALLBACK_BEHAVIOURS
    behaviour_enum = [
        name for name in behaviour_enum if not any(keyword in name.casefold() for keyword in EXCLUDED_KEYWORDS)
    ]
    if not behaviour_enum:
        behaviour_enum = [
            name for name in FALLBACK_BEHAVIOURS if not any(keyword in name.casefold() for keyword in EXCLUDED_KEYWORDS)
        ]

    base_declarations = [
        {
            "name": "set_behavior",
            "description": "Trigger a named behaviour on the active Shijima mascot.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "behavior_name": {
                        "type": "STRING",
                        "enum": behaviour_enum,
                        "description": "One of the behaviours available in the loaded Shimeji actions.xml.",
                    }
                },
                "required": ["behavior_name"],
            },
        },
        {
            "name": "observe_and_wait",
            "description": "Pause and observe without taking visible action.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "duration_seconds": {
                        "type": "INTEGER",
                        "description": "Seconds to wait before thinking again.",
                    }
                },
                "required": ["duration_seconds"],
            },
        },
        {
            "name": "show_dialogue",
            "description": "Display a short thought bubble above the mascot.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "text": {"type": "STRING"},
                    "duration_seconds": {
                        "type": "INTEGER",
                        "description": "Optional display duration in seconds.",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "save_episodic_memory",
            "description": "Store an observation in episodic memory for future recall.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "fact": {"type": "STRING"},
                    "metadata": {"type": "STRING"},
                },
                "required": ["fact"],
            },
        },
        {
            "name": "fetch_fact",
            "description": "Look up a random fun fact to share with the user.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {
                        "type": "STRING",
                        "description": "Optional topic for the fact (e.g., 'space', 'animals').",
                    }
                },
            },
        },
        # read_clipboard removed from proactive tools - users must manually request it via chat button
        {
            "name": "execute_bash",
            "description": "Execute a bash command and return the output. IMPORTANT: This ACTUALLY RUNS the command - use it to delete files, edit configs, run scripts, etc. You can chain multiple calls: first find/locate files, then execute operations on them. Always execute the command when the user confirms - don't just describe what you would do.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "command": {
                        "type": "STRING",
                        "description": "The bash command to execute. Examples: 'rm ~/Desktop/prime_counter.py' to delete a file, 'ls ~/Desktop' to list files, 'cat ~/.ssh/config' to read a file, etc. This command WILL BE EXECUTED.",
                    }
                },
                "required": ["command"],
            },
        },

        {
            "name": "check_system_status",
            "description": "Check battery, CPU, and memory status to monitor system health.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "get_system_metrics",
            "description": "Get comprehensive system metrics including RAM, GPU, disk, and network status. Returns current usage percentages and details.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "set_monitoring_preference",
            "description": "Update a monitoring threshold or setting. Use this to customize alert thresholds (e.g., RAM threshold, disk threshold).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "key": {
                        "type": "STRING",
                        "description": "Preference key (e.g., 'ram_threshold_pct', 'disk_threshold_pct', 'gpu_temp_threshold_c')",
                    },
                    "value": {
                        "type": "STRING",
                        "description": "Preference value (will be converted to appropriate type)",
                    },
                },
                "required": ["key", "value"],
            },
        },
        {
            "name": "get_monitoring_preferences",
            "description": "Get all current monitoring preferences and thresholds. Returns a dictionary of all settings.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        # Proactive System Optimization
        {
            "name": "suggest_resource_optimization",
            "description": "Suggest resource optimizations when system resources are high (e.g., close idle apps when RAM > 80%).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "threshold_type": {
                        "type": "STRING",
                        "enum": ["ram", "cpu", "disk"],
                        "description": "Type of resource threshold crossed",
                    },
                    "current_usage": {
                        "type": "NUMBER",
                        "description": "Current usage percentage",
                    },
                    "process_list": {
                        "type": "STRING",
                        "description": "JSON string of process information for analysis",
                    },
                },
                "required": ["threshold_type", "current_usage"],
            },
        },
        {
            "name": "infer_user_goal",
            "description": "Infer user goals from window focus patterns and history. Suggests actions based on repeated patterns.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "context": {
                        "type": "STRING",
                        "description": "JSON string of current context",
                    },
                    "recent_actions": {
                        "type": "STRING",
                        "description": "JSON string of recent actions",
                    },
                    "memory_patterns": {
                        "type": "STRING",
                        "description": "JSON string of detected memory patterns",
                    },
                },
                "required": ["context"],
            },
        },
        # User Interaction
        {
            "name": "analyze_dropped_file",
            "description": "Analyze a file that was dropped on the mascot or chat window. Supports code, images, PDFs, and other file types.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "file_path": {
                        "type": "STRING",
                        "description": "Path to the dropped file",
                    },
                    "file_type": {
                        "type": "STRING",
                        "description": "Type of file (e.g., 'image', 'code', 'pdf', 'text')",
                    },
                    "question": {
                        "type": "STRING",
                        "description": "Optional question about what to analyze in the file",
                    },
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "process_voice_command",
            "description": "Process a voice command from the user. Converts speech to text and processes the command.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "audio_data": {
                        "type": "STRING",
                        "description": "Base64 encoded audio data (optional if using live input)",
                    },
                    "language": {
                        "type": "STRING",
                        "description": "Language code (default: 'en')",
                    },
                },
            },
        },
        # Intelligent Automation
        {
            "name": "schedule_task",
            "description": "Schedule a task to be executed at a specific time or on a recurring basis.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "task_description": {
                        "type": "STRING",
                        "description": "Description of the task to schedule",
                    },
                    "time": {
                        "type": "STRING",
                        "description": "Time to execute (ISO format or relative like 'in 1 hour')",
                    },
                    "recurrence": {
                        "type": "STRING",
                        "description": "Optional recurrence pattern (e.g., 'daily', 'weekly', 'hourly')",
                    },
                },
                "required": ["task_description", "time"],
            },
        },
        {
            "name": "set_reminder",
            "description": "Set a reminder for the user at a specific time.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "message": {
                        "type": "STRING",
                        "description": "Reminder message",
                    },
                    "time": {
                        "type": "STRING",
                        "description": "Time for reminder (ISO format or relative)",
                    },
                },
                "required": ["message", "time"],
            },
        },
        {
            "name": "auto_fix_issue",
            "description": "Automatically fix common system issues detected in logs (e.g., kill zombie processes, clear temp files).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "issue_type": {
                        "type": "STRING",
                        "enum": ["zombie", "temp_files", "log_rotation", "disk_cleanup"],
                        "description": "Type of issue to fix",
                    },
                    "log_entry": {
                        "type": "STRING",
                        "description": "Log entry that indicates the issue",
                    },
                    "suggested_fix": {
                        "type": "STRING",
                        "description": "Suggested fix command or action",
                    },
                },
                "required": ["issue_type"],
            },
        },
        # System Integration
        {
            "name": "send_dbus_notification",
            "description": "Send a desktop notification via DBus (GNOME/KDE integration).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "title": {
                        "type": "STRING",
                        "description": "Notification title",
                    },
                    "message": {
                        "type": "STRING",
                        "description": "Notification message",
                    },
                    "urgency": {
                        "type": "STRING",
                        "enum": ["low", "normal", "critical"],
                        "description": "Urgency level",
                    },
                },
                "required": ["title", "message"],
            },
        },
        {
            "name": "detect_app_context",
            "description": "Detect the current application context and suggest app-specific tools.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "summarize_web_page",
            "description": "Summarize the content of the currently focused web page (browser context).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url": {
                        "type": "STRING",
                        "description": "Optional URL (if not provided, uses current page)",
                    },
                },
            },
        },
        {
            "name": "analyze_code_context",
            "description": "Analyze code in the currently focused IDE or editor.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "question": {
                        "type": "STRING",
                        "description": "Optional question about the code",
                    },
                },
            },
        },
        # Learning/Adaptation
        {
            "name": "record_feedback",
            "description": "Record user feedback on an action to learn preferences.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": "Action that was taken",
                    },
                    "user_response": {
                        "type": "STRING",
                        "description": "User response ('positive', 'negative', 'neutral', or specific feedback)",
                    },
                    "context": {
                        "type": "STRING",
                        "description": "Optional JSON string of context",
                    },
                },
                "required": ["action", "user_response"],
            },
        },
        {
            "name": "detect_patterns",
            "description": "Detect patterns in user behavior (habits, routines, app usage).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "time_range": {
                        "type": "STRING",
                        "description": "Time range to analyze (e.g., '7 days', '30 days')",
                    },
                    "pattern_type": {
                        "type": "STRING",
                        "enum": ["app_usage", "time_based", "sequence"],
                        "description": "Type of pattern to detect",
                    },
                },
                "required": ["pattern_type"],
            },
        },
        # Multi-Modal
        {
            "name": "detect_ambient_sound",
            "description": "Detect ambient sounds (notifications, error beeps, etc.) for awareness.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "duration_seconds": {
                        "type": "INTEGER",
                        "description": "Duration to monitor (default: 5)",
                    },
                    "sensitivity": {
                        "type": "NUMBER",
                        "description": "Sensitivity threshold 0.0-1.0 (default: 0.5)",
                    },
                },
            },
        },
        # Memory
        {
            "name": "semantic_memory_search",
            "description": "Perform semantic search on episodic memory using vector embeddings for better recall.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "Search query",
                    },
                    "limit": {
                        "type": "INTEGER",
                        "description": "Maximum number of results (default: 5)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "mine_patterns",
            "description": "Mine insights from user behavior patterns (productivity trends, usage patterns).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "time_range_days": {
                        "type": "INTEGER",
                        "description": "Number of days to analyze (default: 30)",
                    },
                },
            },
        },
        # Collaboration
        {
            "name": "spawn_agent",
            "description": "Spawn a sub-agent to handle a specific task (research, execution, analysis, monitoring).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "agent_type": {
                        "type": "STRING",
                        "enum": ["research", "execution", "analysis", "monitoring"],
                        "description": "Type of agent to spawn",
                    },
                    "task_description": {
                        "type": "STRING",
                        "description": "Description of the task for the agent",
                    },
                },
                "required": ["agent_type", "task_description"],
            },
        },
        {
            "name": "share_knowledge",
            "description": "Share knowledge with other Shimeji instances via HTTP (multi-device sync).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "knowledge_type": {
                        "type": "STRING",
                        "enum": ["memory", "preferences", "patterns"],
                        "description": "Type of knowledge to share",
                    },
                    "data": {
                        "type": "STRING",
                        "description": "JSON string of data to share",
                    },
                },
                "required": ["knowledge_type", "data"],
            },
        },
        # Security
        {
            "name": "request_permission",
            "description": "Request user permission before executing a sensitive tool or action.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "tool_name": {
                        "type": "STRING",
                        "description": "Name of the tool requesting permission",
                    },
                    "reason": {
                        "type": "STRING",
                        "description": "Reason for the permission request",
                    },
                },
                "required": ["tool_name", "reason"],
            },
        },
    ]
    
    # Add plugin function declarations
    for plugin in PLUGINS:
        try:
            plugin_declarations = plugin.get_function_declarations()
            base_declarations.extend(plugin_declarations)
            LOGGER.debug("Added %d function declarations from plugin %s", len(plugin_declarations), plugin.__class__.__name__)
        except Exception as exc:
            LOGGER.warning("Failed to get function declarations from plugin %s: %s", plugin.__class__.__name__, exc)
    
    return base_declarations
