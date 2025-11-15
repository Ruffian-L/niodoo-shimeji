"""App-specific context detection and behavior."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)


class AppContext:
    """Detects and handles app-specific contexts."""
    
    # App categories and their characteristics
    APP_CATEGORIES = {
        "browser": {
            "keywords": ["firefox", "chrome", "chromium", "brave", "edge", "safari", "opera"],
            "tools": ["summarize_web_page", "extract_links", "read_page_content"],
        },
        "ide": {
            "keywords": ["code", "vscode", "idea", "pycharm", "vim", "emacs", "sublime", "atom"],
            "tools": ["analyze_code", "suggest_refactor", "explain_code"],
        },
        "terminal": {
            "keywords": ["terminal", "gnome-terminal", "konsole", "xterm", "alacritty", "kitty"],
            "tools": ["execute_command", "monitor_output", "suggest_commands"],
        },
        "editor": {
            "keywords": ["gedit", "kate", "nano", "notepad"],
            "tools": ["read_file", "edit_file", "format_text"],
        },
        "office": {
            "keywords": ["libreoffice", "writer", "calc", "impress", "word", "excel"],
            "tools": ["summarize_document", "extract_text"],
        },
        "media": {
            "keywords": ["vlc", "mpv", "gimp", "inkscape", "audacity"],
            "tools": ["analyze_media", "extract_metadata"],
        },
    }
    
    def __init__(self) -> None:
        """Initialize app context detector."""
        pass
    
    def detect_app_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Detect app-specific context from window context.
        
        Args:
            context: Window context dictionary with 'application' and 'title' keys
        
        Returns:
            Dictionary with app category and available tools
        """
        app_name = context.get("application", "").lower()
        title = context.get("title", "").lower()
        
        detected_category = None
        available_tools = []
        
        # Check each category
        for category, config in self.APP_CATEGORIES.items():
            keywords = config["keywords"]
            for keyword in keywords:
                if keyword in app_name or keyword in title:
                    detected_category = category
                    available_tools = config["tools"]
                    break
            if detected_category:
                break
        
        return {
            "category": detected_category or "unknown",
            "app_name": context.get("application", "Unknown"),
            "title": context.get("title", ""),
            "available_tools": available_tools,
        }
    
    def get_app_specific_suggestion(
        self,
        app_context: Dict[str, Any],
        user_activity: Optional[str] = None,
    ) -> Optional[str]:
        """Get app-specific suggestion based on context.
        
        Args:
            app_context: App context dictionary from detect_app_context
            user_activity: Optional description of current user activity
        
        Returns:
            Suggestion string or None
        """
        category = app_context.get("category")
        
        if category == "browser":
            return "I can summarize web pages or extract links. Just ask!"
        elif category == "ide":
            return "I can analyze your code or suggest improvements. Need help?"
        elif category == "terminal":
            return "I can help with commands or monitor output. What do you need?"
        elif category == "editor":
            return "I can read or format text files. Want me to help?"
        elif category == "office":
            return "I can summarize documents or extract text. Need assistance?"
        elif category == "media":
            return "I can analyze media files or extract metadata. How can I help?"
        
        return None
    
    def should_offer_tool(self, app_context: Dict[str, Any], tool_name: str) -> bool:
        """Check if a tool should be offered for this app context.
        
        Args:
            app_context: App context dictionary
            tool_name: Name of the tool
        
        Returns:
            True if tool should be offered
        """
        available_tools = app_context.get("available_tools", [])
        return tool_name in available_tools
    
    def get_contextual_behavior(self, app_context: Dict[str, Any]) -> Optional[str]:
        """Get contextual behavior suggestion for mascot.
        
        Args:
            app_context: App context dictionary
        
        Returns:
            Behavior name or None
        """
        category = app_context.get("category")
        
        # Map categories to behaviors
        behavior_map = {
            "browser": "SitAndLookAtMouse",
            "ide": "SitAndFaceMouse",
            "terminal": "Sit",
            "editor": "Sit",
            "office": "Sit",
            "media": "SitAndLookAtMouse",
        }
        
        return behavior_map.get(category)


