"""Base class for extensible tool plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ToolPlugin(ABC):
    """Base class for extensible tool plugins."""
    
    @abstractmethod
    def get_function_declarations(self) -> List[Dict[str, Any]]:
        """Return Gemini function declarations for this plugin.
        
        Returns:
            List of function declaration dictionaries compatible with Gemini API
        """
        pass
    
    @abstractmethod
    async def execute(self, action: str, args: Dict[str, Any]) -> Any:
        """Execute a tool action.
        
        Args:
            action: The action name (function name from declaration)
            args: The arguments dictionary
            
        Returns:
            Result of the action execution (can be None)
        """
        pass

