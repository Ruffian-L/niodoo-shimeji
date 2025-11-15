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
        {
            "name": "read_clipboard",
            "description": "Read the current clipboard content to see what the user copied.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "execute_bash",
            "description": "Execute a bash command and return the output. Use for system tasks.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "command": {
                        "type": "STRING",
                        "description": "The bash command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
        {
            "name": "take_screenshot",
            "description": "Capture a screenshot of the user's screen to see what they're working on.",
            "parameters": {
                "type": "OBJECT",
                "properties": {},
            },
        },
        {
            "name": "analyze_screenshot",
            "description": "Capture a screenshot and analyze it with vision AI to see what the user is working on, debug code, or understand their screen context.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "question": {
                        "type": "STRING",
                        "description": "Optional question about what to look for in the screenshot (e.g., 'What code is on screen?', 'What error do you see?').",
                    }
                },
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
