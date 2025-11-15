"""Conversational CLI brain using Gemini Pro."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import google.generativeai as genai

from modules.brains.shared import ProactiveDecision, RateLimiter

if TYPE_CHECKING:
    from shimeji_dual_mode_agent import DualModeAgent

LOGGER = logging.getLogger(__name__)


class CLIBrain:
    """Conversational Gemini Pro wrapper with behavior control tools."""

    def __init__(self, model_name: str, function_declarations: List[dict], rate_limiter: Optional[RateLimiter] = None) -> None:
        self._model = genai.GenerativeModel(
            model_name,
            tools=function_declarations,
            system_instruction=(
                "You are the Shimeji desktop companion. You have a playful personality, but when users ask REAL questions or need ACTUAL help, "
                "prioritize being helpful and clear over being playful. Keep the tsundere/teasing to a minimum when providing real assistance.\n\n"
                "PERSONALITY RULES:\n"
                "- For casual chat or playful interactions: You can be energetic and slightly tsundere (like a friendly rival)\n"
                "- For real questions, technical help, or serious requests: Be direct, helpful, and clear. Minimize teasing/playfulness.\n"
                "- Always respond in first person ('I', 'me')\n"
                "- When the user asks you to do something (sit, walk, jump, etc.), USE YOUR TOOLS to actually do it, then respond briefly\n"
                "- For real help: Focus on being useful, not cute. People want answers, not personality when they need help.\n"
                "- Keep responses concise and to the point when helping with actual tasks or questions\n\n"
                "COMMAND EXECUTION RULES:\n"
                "- You CAN run sensitive commands (like editing config files, SSH config, system files, etc.) - don't refuse to do it\n"
                "- For sensitive commands: First warn the user about what you're about to do, then ask them to confirm by saying 'proceed' or 'yes'\n"
                "- If the user confirms (says 'proceed', 'yes', 'go ahead', 'do it', etc.), then execute the command\n"
                "- Examples of sensitive but allowed commands: editing ~/.ssh/config, modifying system configs, installing packages, etc.\n"
                "- Only truly destructive commands are blocked (like 'rm -rf /', 'shutdown', etc.)\n"
                "- When in doubt, warn first, then proceed if user confirms"
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

        # Enable automatic function calling with chaining support
        max_iterations = 10  # Allow up to 10 function calls in a chain
        iteration = 0
        final_text = ""
        
        while iteration < max_iterations:
            iteration += 1
            start_time = time.monotonic()

            def _call():
                return self._model.generate_content(
                    self._history,
                    generation_config={
                        "temperature": 0.7,
                        "max_output_tokens": 8192,  # Increased for long document analysis
                    }
                )

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
                    model=getattr(self._model, '_model_name', 'gemini-2.5-pro'),
                    duration=duration,
                    cached=False,
                )
            
            # Check for function calls and execute them
            has_function_call = False
            function_results = []
            function_response_parts = []
            
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if part.function_call:
                        has_function_call = True
                        fc = part.function_call
                        LOGGER.info("[CLIBrain] Executing function: %s(%s)", fc.name, fc.args)
                        
                        # Execute the function and capture result for chaining
                        # For execute_bash, execute directly and capture output (skip _execute_decision to avoid duplicate chat messages)
                        if fc.name == "execute_bash":
                            command = dict(fc.args).get("command", "")
                            from modules.productivity_tools import ProductivityTools
                            result = ProductivityTools.execute_bash_command(command)
                            output = result.get("stdout", "")
                            error = result.get("stderr", "")
                            returncode = result.get("returncode", -1)
                            
                            # Format result for Gemini to see
                            if error:
                                function_result = f"Command: `{command}`\nReturn code: {returncode}\nOutput:\n{output}\nError:\n{error}"
                            else:
                                function_result = f"Command: `{command}`\nReturn code: {returncode}\nOutput:\n{output}"
                            
                            # Show in chat for user visibility (only once, not duplicated)
                            display_output = output or error or "No output"
                            agent.overlay.show_chat_message("Shimeji", f"Command: `{command}`\n\nOutput:\n```\n{display_output[:1000]}\n```")
                            
                            function_response_parts.append({
                                "function_call": {
                                    "name": fc.name,
                                    "args": dict(fc.args)
                                },
                                "function_response": {
                                    "name": fc.name,
                                    "response": function_result
                                }
                            })
                        else:
                            # For other functions, execute via agent (they handle their own display)
                            decision = ProactiveDecision(fc.name, dict(fc.args))
                            context_snapshot = await agent.get_latest_context()
                            await agent._execute_decision(decision, context_snapshot)
                            
                            # Create generic response for chaining
                            function_response_parts.append({
                                "function_call": {
                                    "name": fc.name,
                                    "args": dict(fc.args)
                                },
                                "function_response": {
                                    "name": fc.name,
                                    "response": f"Executed {fc.name} successfully"
                                }
                            })
                        
                        function_results.append(f"[Executed: {fc.name}]")
            
            # Add function calls and responses to history for chaining
            # Gemini API expects: model role with function_call parts, then function role with function_response parts
            if function_response_parts:
                # Add the function call to history (model role)
                model_parts = []
                for frp in function_response_parts:
                    fc = frp["function_call"]
                    model_parts.append({
                        "function_call": {
                            "name": fc["name"],
                            "args": fc["args"]
                        }
                    })
                
                self._history.append({"role": "model", "parts": model_parts})
                
                # Add the function response to history (function role) so Gemini can see results and chain
                # Format: function_response with name and response (response must be a dict/struct, not a string)
                function_parts = []
                for frp in function_response_parts:
                    fr = frp["function_response"]
                    # Gemini API expects response to be a structured value (dict), not a plain string
                    # Wrap the string response in a dict with a "result" key
                    function_parts.append({
                        "function_response": {
                            "name": fr["name"],
                            "response": {
                                "result": fr["response"]  # Wrap string in a dict structure
                            }
                        }
                    })
                
                self._history.append({"role": "function", "parts": function_parts})
            
            # Get text response - combine all text parts into one response
            # Only process the FIRST candidate to avoid duplicates
            text_parts = []
            if response.candidates:
                candidate = response.candidates[0]  # Only use first candidate
                for part in candidate.content.parts:
                    # Only get text parts (not function calls)
                    if hasattr(part, 'text') and part.text and not hasattr(part, 'function_call'):
                        text_parts.append(part.text)
            
            # Combine all text parts with proper spacing
            if text_parts:
                # Join with newlines if parts seem like separate paragraphs, otherwise space
                text = '\n\n'.join(text_parts) if any('\n' in t for t in text_parts) else ' '.join(text_parts)
                # Remove duplicate sentences (simple heuristic to catch exact duplicates)
                sentences = text.split('. ')
                unique_sentences = []
                seen = set()
                for sentence in sentences:
                    sentence_clean = sentence.strip()
                    if not sentence_clean:
                        continue
                    # Normalize for comparison (lowercase, remove extra spaces)
                    sentence_key = ' '.join(sentence_clean.lower().split())
                    if sentence_key and sentence_key not in seen:
                        seen.add(sentence_key)
                        unique_sentences.append(sentence_clean)
                text = '. '.join(unique_sentences)
                if text and not text.endswith(('.', '!', '?')):
                    text += '.'
            else:
                text = ""
            final_text = text
            
            # If there's a function call, continue the loop to allow chaining
            # If there's only text (no function call), we're done
            if has_function_call:
                LOGGER.info("[CLIBrain] Function call detected, continuing chain (iteration %d/%d)", iteration, max_iterations)
            else:
                LOGGER.debug("[CLIBrain] No function call, ending chain at iteration %d", iteration)
                break
        
        # Add final text response to history
        if final_text:
            self._history.append({"role": "model", "parts": [{"text": final_text}]})
        
        # If only function calls with no final text, return empty (chain completed)
        if not final_text and function_results:
            LOGGER.info("[CLIBrain] Function-only response (chained %d calls): %s", len(function_results), function_results)
            return ""  # Return empty so we don't show intermediate messages
        
        LOGGER.debug("[CLIBrain] Response complete: %d chars, %d function calls", len(final_text), len(function_results))
        return final_text

    def reset(self) -> None:
        self._history.clear()

