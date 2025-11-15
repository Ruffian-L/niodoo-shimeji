"""Conversational CLI brain using Gemini Pro."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from modules.brains.shared import ProactiveDecision, RateLimiter

LOGGER = logging.getLogger(__name__)


class CLIBrain:
    """Conversational Gemini Pro wrapper with behavior control tools."""

    def __init__(self, model_name: str, function_declarations: List[dict], rate_limiter: Optional[RateLimiter] = None) -> None:
        self._model = genai.GenerativeModel(
            model_name,
            tools=function_declarations,
            system_instruction=(
                "You are the Shimeji desktop companion in cute arch-nemesis best friend Shonen Jump style - energetic tsundere rival who's your loyal buddy. "
                "Respond in first person ('I', 'me') with fiery spirit and playful challenges. Stay in character! "
                "When the user asks you to do something (sit, walk, jump, etc.), USE YOUR TOOLS to actually do it, then respond. "
                "Channel Bakugo/Vegeta: boast, tease, but support with heart. Short, punchy lines with energy!"
            ),
        )
        self._history: List[Dict[str, Any]] = []
        self._function_declarations = function_declarations
        self._rate_limiter = rate_limiter

    def _sanitize_prompt(self, prompt: str) -> str:
        """Sanitize user input before sending to API."""
        # Remove control characters (keep newlines and tabs)
        sanitized = ''.join(c for c in prompt if ord(c) >= 32 or c in '\n\t')
        # Limit length
        MAX_PROMPT_LENGTH = 10000
        if len(sanitized) > MAX_PROMPT_LENGTH:
            sanitized = sanitized[:MAX_PROMPT_LENGTH] + "... [truncated]"
            LOGGER.warning("Prompt truncated from %d to %d characters", len(prompt), MAX_PROMPT_LENGTH)
        return sanitized

    async def respond(self, prompt: str, agent: "DualModeAgent") -> str:
        # Sanitize input
        sanitized_prompt = self._sanitize_prompt(prompt)
        
        loop = asyncio.get_running_loop()
        self._history.append({"role": "user", "parts": [{"text": sanitized_prompt}]})

        # Apply rate limiting if configured
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        start_time = time.monotonic()
        
        def _call():
            return self._model.generate_content(self._history)

        response = await loop.run_in_executor(None, _call)
        duration = time.monotonic() - start_time
        
        # Record metrics if agent available
        if hasattr(self, '_agent') and self._agent and hasattr(self._agent, '_metrics'):
            self._agent._metrics.record_api_call(duration)
        
        # Log API call if structured logger available
        if hasattr(self, '_structured_logger') and self._structured_logger:
            self._structured_logger.log_api_call(
                model=getattr(self._model, '_model_name', 'gemini-2.5-pro'),
                duration=duration,
                cached=False,
            )
        
        # Check for function calls and execute them
        has_function_call = False
        function_results = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    LOGGER.info("[CLIBrain] Executing function: %s(%s)", fc.name, fc.args)
                    # Execute the function via agent
                    decision = ProactiveDecision(fc.name, dict(fc.args))
                    await agent._execute_decision(decision, agent._latest_context)
                    function_results.append(f"[Executed: {fc.name}]")
        
        # Get text response
        text_parts = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
        
        text = ' '.join(text_parts) if text_parts else ""
        
        # If only function call with no text, just log it (don't spam "Got it!")
        if not text and has_function_call:
            LOGGER.info("Function-only response: %s", function_results)
            text = ""  # Return empty so we don't show anything
        
        if text:  # Only add to history if there's actual text
            self._history.append({"role": "model", "parts": [{"text": text}]})
        return text

    def reset(self) -> None:
        self._history.clear()

