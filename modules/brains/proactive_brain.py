"""Proactive decision-making brain using Gemini Flash."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

import google.generativeai as genai
from google.generativeai import types as genai_types

from modules.brains.shared import ProactiveDecision, RateLimiter
from modules.constants import DEFAULT_PROACTIVE_INTERVAL_SECONDS

LOGGER = logging.getLogger(__name__)


class ProactiveBrain:
    """Thin wrapper over Gemini Flash for autonomous decisions."""

    def __init__(
        self,
        model_name: str,
        system_prompt: str,
        function_declarations: List[dict],
        enable_cache: bool = True,
        cache_model: Optional[str] = None,
        cache_ttl: int = 3600,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.model_name = model_name
        self.system_prompt = system_prompt
        self._model = genai.GenerativeModel(
            model_name,
            tools=function_declarations,
            system_instruction=system_prompt,
        )
        self._cache_name: Optional[str] = None
        self._rate_limiter = rate_limiter
        if enable_cache:
            self._prepare_cache(function_declarations, cache_model, cache_ttl)

    def _prepare_cache(
        self,
        function_declarations: List[dict],
        cache_model: Optional[str],
        cache_ttl: int,
    ) -> None:
        model_id = cache_model or f"models/{self.model_name}" if not self.model_name.startswith("models/") else self.model_name
        ttl_seconds = max(60, cache_ttl)
        try:
            # Check if caches API is available
            if not hasattr(genai, 'caches'):
                LOGGER.debug("Gemini caches API not available; continuing without caching")
                self._cache_name = None
                return
            cache = genai.caches.create(
                model=model_id,
                config=genai_types.CreateCachedContentConfig(
                    system_instruction=self.system_prompt,
                    ttl=f"{ttl_seconds}s",
                ),
            )
            self._cache_name = cache.name
            LOGGER.info("Gemini cache ready: %s (TTL=%ss)", cache.name, ttl_seconds)
        except Exception as exc:
            LOGGER.debug("Context cache unavailable (%s); continuing without caching", exc)
            self._cache_name = None

    async def decide(
        self,
        context: Dict[str, Any],
        action_history: Deque[str],
        working_summary: List[str],
        episodic_facts: List[str],
        emotional_state: Dict[str, float],
    ) -> ProactiveDecision:
        loop = asyncio.get_running_loop()
        history_text = ", ".join(action_history) if action_history else "None"
        working_text = "\n".join(f"- {item}" for item in working_summary) if working_summary else "None"
        episodic_text = "\n".join(f"- {item}" for item in episodic_facts) if episodic_facts else "None"
        payload = (
            "You will receive sanitized desktop context. Choose exactly ONE tool.\n"
            f"Latest context JSON:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"Recent actions: {history_text}\n\n"
            f"Working memory:\n{working_text}\n\n"
            f"Episodic memory:\n{episodic_text}\n\n"
            f"Emotional state: {json.dumps(emotional_state)}"
        )

        LOGGER.debug("[ProactiveBrain] Prompt payload: %s", payload)

        # Apply rate limiting if configured
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        start_time = time.monotonic()
        cached = self._cache_name is not None

        def _call():
            if self._cache_name:
                return self._model.generate_content(
                    payload,
                    config=genai_types.GenerateContentConfig(cached_content=self._cache_name),
                )
            return self._model.generate_content(payload)

        try:
            response = await loop.run_in_executor(None, _call)
            duration = time.monotonic() - start_time

            # Record success for circuit breaker
            if self._rate_limiter:
                self._rate_limiter.record_success()
        except Exception as exc:
            duration = time.monotonic() - start_time

            # Record failure for circuit breaker
            if self._rate_limiter:
                self._rate_limiter.record_failure(exc)

            raise
        
        # Record metrics if agent available
        if hasattr(self, '_agent') and self._agent and hasattr(self._agent, '_metrics'):
            self._agent._metrics.record_api_call(duration)
        
        # Log API call if structured logger available
        if hasattr(self, '_structured_logger') and self._structured_logger:
            self._structured_logger.log_api_call(
                model=self.model_name,
                duration=duration,
                cached=cached,
            )
        function_call = None
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.function_call:
                    function_call = part.function_call
                    break
            if function_call:
                break

        if not function_call:
            LOGGER.warning("Gemini returned no function call; defaulting to observe_and_wait")
            return ProactiveDecision(
                "observe_and_wait",
                {"duration_seconds": DEFAULT_PROACTIVE_INTERVAL_SECONDS},
            )

        decision = ProactiveDecision(function_call.name, dict(function_call.args))
        
        # Log decision if structured logger available
        if hasattr(self, '_structured_logger') and self._structured_logger:
            self._structured_logger.log_decision(
                decision_action=decision.action,
                decision_args=decision.arguments,
            )
        
        LOGGER.info("[ProactiveBrain] Decision: %s(%s)", function_call.name, function_call.args)
        return decision

