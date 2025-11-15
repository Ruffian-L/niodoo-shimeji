"""Multi-agent coordination system."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

LOGGER = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of agents that can be spawned."""
    RESEARCH = "research"
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    MONITORING = "monitoring"


@dataclass
class AgentTask:
    """Represents a task for an agent."""
    agent_type: AgentType
    task_description: str
    context: Dict[str, Any]
    callback: Optional[Callable[[Any], None]] = None


class MultiAgentCoordinator:
    """Coordinates multiple sub-agents for complex tasks."""
    
    def __init__(self, event_bus: Any, main_agent: Any) -> None:
        """Initialize multi-agent coordinator.
        
        Args:
            event_bus: EventBus instance for communication
            main_agent: Main DualModeAgent instance
        """
        self.event_bus = event_bus
        self.main_agent = main_agent
        self._active_agents: Dict[str, asyncio.Task] = {}
        self._agent_results: Dict[str, Any] = {}
    
    async def spawn_agent(
        self,
        agent_type: AgentType,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Spawn a sub-agent to handle a task.
        
        Args:
            agent_type: Type of agent to spawn
            task_description: Description of the task
            context: Optional context dictionary
        
        Returns:
            Agent ID
        """
        import uuid
        agent_id = str(uuid.uuid4())
        
        context = context or {}
        task = AgentTask(
            agent_type=agent_type,
            task_description=task_description,
            context=context,
        )
        
        # Create agent task
        agent_task = asyncio.create_task(self._run_agent(agent_id, task))
        self._active_agents[agent_id] = agent_task
        
        # Publish event
        from modules.event_bus import EventType
        self.event_bus.publish(EventType.AGENT_SPAWNED, {
            "agent_id": agent_id,
            "agent_type": agent_type.value,
            "task": task_description,
        })
        
        LOGGER.info("Spawned %s agent: %s", agent_type.value, agent_id)
        return agent_id
    
    async def _run_agent(self, agent_id: str, task: AgentTask) -> None:
        """Run an agent task.
        
        Args:
            agent_id: Unique agent ID
            task: Agent task
        """
        try:
            if task.agent_type == AgentType.RESEARCH:
                result = await self._research_agent(task)
            elif task.agent_type == AgentType.EXECUTION:
                result = await self._execution_agent(task)
            elif task.agent_type == AgentType.ANALYSIS:
                result = await self._analysis_agent(task)
            elif task.agent_type == AgentType.MONITORING:
                result = await self._monitoring_agent(task)
            else:
                result = {"error": f"Unknown agent type: {task.agent_type}"}
            
            self._agent_results[agent_id] = result
            
            # Call callback if provided
            if task.callback:
                try:
                    task.callback(result)
                except Exception as exc:
                    LOGGER.error("Agent callback failed: %s", exc)
            
        except Exception as exc:
            LOGGER.error("Agent %s failed: %s", agent_id, exc)
            self._agent_results[agent_id] = {"error": str(exc)}
        finally:
            # Remove from active agents
            if agent_id in self._active_agents:
                del self._active_agents[agent_id]
    
    async def _research_agent(self, task: AgentTask) -> Dict[str, Any]:
        """Research agent - gathers information."""
        # Use memory to search for relevant information
        memory = self.main_agent.memory
        context = task.context
        
        # Search episodic memory
        relevant_facts = await memory.recall_relevant_async(context, limit=10)
        
        # Could also use Gemini to research
        # For now, return memory results
        return {
            "type": "research",
            "task": task.task_description,
            "results": relevant_facts,
        }
    
    async def _execution_agent(self, task: AgentTask) -> Dict[str, Any]:
        """Execution agent - executes commands."""
        # Use productivity tools to execute
        from modules.productivity_tools import ProductivityTools
        
        # Parse task description for commands
        # This is simplified - in reality, would use Gemini to parse
        command = task.task_description
        
        result = ProductivityTools.execute_bash_command(command)
        
        return {
            "type": "execution",
            "task": task.task_description,
            "result": result,
        }
    
    async def _analysis_agent(self, task: AgentTask) -> Dict[str, Any]:
        """Analysis agent - analyzes data."""
        # Use Gemini to analyze
        # For now, return placeholder
        return {
            "type": "analysis",
            "task": task.task_description,
            "result": "Analysis completed",
        }
    
    async def _monitoring_agent(self, task: AgentTask) -> Dict[str, Any]:
        """Monitoring agent - monitors system."""
        # Use system monitor
        if hasattr(self.main_agent, '_monitoring_manager'):
            monitor = self.main_agent._monitoring_manager
            # Get current metrics
            return {
                "type": "monitoring",
                "task": task.task_description,
                "status": "monitoring",
            }
        
        return {
            "type": "monitoring",
            "task": task.task_description,
            "error": "Monitoring not available",
        }
    
    def get_agent_result(self, agent_id: str) -> Optional[Any]:
        """Get result from an agent.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Agent result or None
        """
        return self._agent_results.get(agent_id)
    
    def is_agent_active(self, agent_id: str) -> bool:
        """Check if an agent is still active.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            True if agent is active
        """
        return agent_id in self._active_agents
    
    async def wait_for_agent(self, agent_id: str, timeout: float = 30.0) -> Optional[Any]:
        """Wait for an agent to complete.
        
        Args:
            agent_id: Agent ID
            timeout: Timeout in seconds
        
        Returns:
            Agent result or None if timeout
        """
        if agent_id not in self._active_agents:
            return self.get_agent_result(agent_id)
        
        try:
            await asyncio.wait_for(self._active_agents[agent_id], timeout=timeout)
            return self.get_agent_result(agent_id)
        except asyncio.TimeoutError:
            LOGGER.warning("Agent %s timed out", agent_id)
            return None
    
    def list_active_agents(self) -> List[str]:
        """List all active agent IDs.
        
        Returns:
            List of agent IDs
        """
        return list(self._active_agents.keys())


