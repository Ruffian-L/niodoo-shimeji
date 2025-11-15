"""Qt state machine for mascot animation based on agent internal state."""

from __future__ import annotations

import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)


class MascotStateMachine:
    """QObject-based state machine that drives mascot animations from agent events."""
    
    def __init__(self) -> None:
        """Initialize the state machine."""
        try:
            from PySide6.QtCore import QObject, QState, QStateMachine, Signal
            from PySide6.QtWidgets import QApplication
        except ImportError:
            LOGGER.warning("PySide6 not available; mascot state machine disabled")
            self._available = False
            return
        
        self._available = True
        self._qobject: Optional[QObject] = None
        self._state_machine: Optional[QStateMachine] = None
        self._states: dict[str, QState] = {}
        self._current_state: Optional[str] = None
        
        # Create QObject for signal/slot communication
        class StateMachineQObject(QObject):
            state_changed = Signal(str)  # Emitted when state changes
            
            def transition_to(self, state_name: str) -> None:
                """Public method to transition state (called via QMetaObject.invokeMethod)."""
                if self._parent:
                    self._parent.transition_to(state_name)
        
        self._qobject = StateMachineQObject()
        self._qobject._parent = self  # Store reference to parent
        self._state_machine = QStateMachine()
        self._initialize_states()
    
    def _initialize_states(self) -> None:
        """Initialize all state machine states."""
        if not self._available or not self._state_machine:
            return
        
        from PySide6.QtCore import QState
        
        # Define states
        states = {
            "Idle": "The mascot is idle, waiting for activity",
            "Walking": "The mascot is walking around",
            "Pondering": "The agent is thinking/reasoning (Gemini Pro busy)",
            "Alert": "Critical system alert detected",
            "Interacting": "User chat is active",
            "ExecutingTask": "Tool execution in progress",
            "Sleeping": "System is idle, mascot is resting",
        }
        
        for state_name, description in states.items():
            state = QState()
            state.setObjectName(state_name)
            self._states[state_name] = state
            self._state_machine.addState(state)
        
        # Set initial state
        if "Idle" in self._states:
            self._state_machine.setInitialState(self._states["Idle"])
            self._current_state = "Idle"
        
        # Start the state machine
        self._state_machine.start()
        LOGGER.info("Mascot state machine initialized")
    
    def transition_to(self, state_name: str) -> None:
        """Transition to a named state.
        
        Args:
            state_name: Name of the state to transition to
        """
        if not self._available or not self._state_machine:
            return
        
        if state_name not in self._states:
            LOGGER.warning("Unknown state: %s", state_name)
            return
        
        if self._current_state == state_name:
            return  # Already in this state
        
        target_state = self._states[state_name]
        if self._current_state:
            source_state = self._states[self._current_state]
            # Create transition
            from PySide6.QtCore import QSignalTransition
            # For now, use simple transition
            self._state_machine.setInitialState(target_state)
        else:
            self._state_machine.setInitialState(target_state)
        
        self._current_state = state_name
        if self._qobject:
            self._qobject.state_changed.emit(state_name)
        
        LOGGER.debug("State transition: %s -> %s", self._current_state, state_name)
    
    def get_current_state(self) -> Optional[str]:
        """Get the current state name.
        
        Returns:
            Current state name or None if not available
        """
        return self._current_state
    
    def is_available(self) -> bool:
        """Check if state machine is available.
        
        Returns:
            True if PySide6 is available and state machine is initialized
        """
        return self._available and self._state_machine is not None

