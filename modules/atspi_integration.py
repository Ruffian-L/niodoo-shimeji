"""AT-SPI integration for application-level context and automation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependency
PYATSPI_AVAILABLE = False
try:
    import pyatspi
    PYATSPI_AVAILABLE = True
except ImportError:
    LOGGER.debug("pyatspi2 not available; AT-SPI integration disabled")


class ATSPIContextReader:
    """Reads application context using AT-SPI accessibility interface."""
    
    def __init__(self) -> None:
        """Initialize AT-SPI context reader."""
        self._available = PYATSPI_AVAILABLE
        if not self._available:
            LOGGER.warning("AT-SPI not available; context reading disabled")
    
    def is_available(self) -> bool:
        """Check if AT-SPI is available.
        
        Returns:
            True if AT-SPI is available
        """
        return self._available
    
    def read_focused_text(self) -> Optional[str]:
        """Read text from currently focused element.
        
        Returns:
            Text content or None if unavailable
        """
        if not self._available:
            return None
        
        try:
            import pyatspi
            
            desktop = pyatspi.Registry.getDesktop(0)
            
            # Find focused application
            for app in desktop:
                try:
                    # Get focused component
                    focused = app.getFocus()
                    if focused:
                        # Check if it implements Text interface
                        if focused.queryText():
                            text_iface = focused.queryText()
                            content = text_iface.getText(0, -1)
                            if content:
                                return content
                except Exception:
                    continue
            
            return None
            
        except Exception as exc:
            LOGGER.debug("AT-SPI read failed: %s", exc)
            return None
    
    def read_app_context(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Read context from a specific application.
        
        Args:
            app_name: Name of application (e.g., 'gedit', 'code')
            
        Returns:
            Dictionary with app context or None
        """
        if not self._available:
            return None
        
        try:
            import pyatspi
            
            desktop = pyatspi.Registry.getDesktop(0)
            
            for app in desktop:
                if app.name == app_name:
                    # Find text view
                    text_content = self._find_text_content(app)
                    return {
                        "app": app_name,
                        "text": text_content,
                    }
            
            return None
            
        except Exception as exc:
            LOGGER.debug("AT-SPI app context read failed: %s", exc)
            return None
    
    def _find_text_content(self, app: Any) -> Optional[str]:
        """Find text content in application accessibility tree.
        
        Args:
            app: AT-SPI application object
            
        Returns:
            Text content or None
        """
        try:
            import pyatspi
            
            def traverse(node: Any, depth: int = 0) -> Optional[str]:
                if depth > 10:  # Limit depth
                    return None
                
                try:
                    # Check if node has text
                    if node.queryText():
                        text_iface = node.queryText()
                        content = text_iface.getText(0, -1)
                        if content and len(content) > 10:  # Only return substantial content
                            return content
                except Exception:
                    pass
                
                # Traverse children
                try:
                    for child in node:
                        result = traverse(child, depth + 1)
                        if result:
                            return result
                except Exception:
                    pass
                
                return None
            
            return traverse(app)
            
        except Exception as exc:
            LOGGER.debug("Text content traversal failed: %s", exc)
            return None
    
    def click_button(self, app_name: str, button_name: str) -> bool:
        """Click a button in an application (P3.3 automation).
        
        Args:
            app_name: Name of application
            button_name: Name or label of button
            
        Returns:
            True if successful
        """
        if not self._available:
            return False
        
        try:
            import pyatspi
            
            desktop = pyatspi.Registry.getDesktop(0)
            
            for app in desktop:
                if app.name == app_name:
                    # Find button
                    button = self._find_button(app, button_name)
                    if button:
                        # Click it
                        actions = button.queryAction()
                        if actions and actions.nActions > 0:
                            actions.doAction(0)  # Click first action
                            return True
            
            return False
            
        except Exception as exc:
            LOGGER.error("AT-SPI button click failed: %s", exc)
            return False
    
    def _find_button(self, app: Any, button_name: str) -> Optional[Any]:
        """Find button in accessibility tree.
        
        Args:
            app: AT-SPI application object
            button_name: Name or label of button
            
        Returns:
            Button object or None
        """
        try:
            import pyatspi
            
            def traverse(node: Any, depth: int = 0) -> Optional[Any]:
                if depth > 10:
                    return None
                
                try:
                    # Check if this is a button
                    role = node.getRole()
                    if role == pyatspi.ROLE_PUSH_BUTTON:
                        name = node.name
                        if button_name.lower() in name.lower():
                            return node
                except Exception:
                    pass
                
                # Traverse children
                try:
                    for child in node:
                        result = traverse(child, depth + 1)
                        if result:
                            return result
                except Exception:
                    pass
                
                return None
            
            return traverse(app)
            
        except Exception as exc:
            LOGGER.debug("Button search failed: %s", exc)
            return None

