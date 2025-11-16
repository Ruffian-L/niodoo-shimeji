"""Simple TCP JSON server for CLI invocation."""

import asyncio
import errno
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from modules.input_sanitizer import InputSanitizer

LOGGER = logging.getLogger(__name__)


class InvocationServer:
    """Simple TCP JSON server for CLI invocation."""

    def __init__(self, agent: "DualModeAgent", host: str, port: int):
        self._agent = agent
        self._host = host
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        if self._server is not None:
            return

        port = self._port
        attempts = int(os.getenv("CLI_PORT_ATTEMPTS", "10"))
        last_exc: Optional[Exception] = None

        for _ in range(max(1, attempts)):
            try:
                self._server = await asyncio.start_server(
                    self._handle_connection, self._host, port
                )
                self._port = port
                break
            except OSError as exc:
                last_exc = exc
                if exc.errno == errno.EADDRINUSE:
                    port += 1
                    continue
                raise
        else:
            raise last_exc  # type: ignore[misc]

        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        LOGGER.info("CLI invocation server listening on %s", addrs)

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            request_text = data.decode("utf-8").strip()

            # Check if this is a health check request
            if request_text == "HEALTH" or request_text.startswith("GET /health"):
                health_response = await self._handle_health_check()
                writer.write(json.dumps(health_response).encode("utf-8"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # Otherwise, treat as CLI request
            if not InputSanitizer.validate_json_input(request_text):
                response = {"error": "invalid input format"}
            else:
                request = json.loads(request_text)
                raw_prompt = request.get("prompt", "").strip()
                if not raw_prompt:
                    LOGGER.warning("Received CLI invocation without prompt")
                    response = {"error": "prompt required"}
                else:
                    # Sanitize the prompt
                    core = getattr(self._agent, "core", None)
                    if core:
                        prompt = core.sanitize_cli_prompt(raw_prompt)
                    else:
                        prompt = InputSanitizer.sanitize_prompt(raw_prompt)
                    if not prompt:
                        response = {"error": "prompt is empty after sanitization"}
                    else:
                        response_text = await self._agent.handle_cli_request(prompt)
                        response = {"response": response_text}
        except json.JSONDecodeError:
            response = {"error": "invalid JSON"}
        except Exception as exc:  # pragma: no cover - network runtime
            LOGGER.exception("Error handling CLI invocation: %s", exc)
            response = {"error": str(exc)}

        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _handle_health_check(self) -> Dict[str, Any]:
        """Handle health check requests."""
        agent = self._agent
        start_time = getattr(agent, '_start_time', None)
        uptime = time.monotonic() - start_time if start_time else 0

        try:
            mascots = agent.desktop_controller.list_mascots()
            mascot_available = len(mascots) > 0
        except Exception:
            mascot_available = False

        try:
            memory_episodes = len(agent.memory.episodic.recent(limit=1000))
        except Exception:
            memory_episodes = 0

        health = {
            "status": "healthy" if agent._running else "stopped",
            "mode": agent.mode.name,
            "mascot_available": mascot_available,
            "memory_episodes": memory_episodes,
            "uptime_seconds": round(uptime, 2),
        }

        # Add metrics if available
        if hasattr(agent, 'get_metrics'):
            try:
                metrics = agent.get_metrics()
                health["metrics"] = metrics
            except Exception:
                pass

        return health

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None