"""Hybrid AI privacy filter using local LLM for on-device scanning."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from enum import Enum
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)


class PrivacyFilterResult(Enum):
    """Result of privacy filter scan."""
    SAFE = "SAFE"
    BLOCK = "BLOCK"
    ANONYMIZE = "ANONYMIZE"


class HybridPrivacyFilter:
    """Two-way privacy filter using local LLM for on-device scanning."""
    
    def __init__(self, process_pool: Optional[Any] = None) -> None:
        """Initialize hybrid privacy filter.
        
        Args:
            process_pool: ProcessPoolExecutor for running local LLM (from P1.1)
        """
        self._process_pool = process_pool
        self._provider = os.getenv("LOCAL_LLM_PROVIDER", "ollama").lower()
        self._model = os.getenv("LOCAL_LLM_MODEL", "gemma:2b")
        self._available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if local LLM is available.
        
        Returns:
            True if local LLM provider is available
        """
        if self._provider == "ollama":
            try:
                result = subprocess.run(
                    ["ollama", "list"],
                    capture_output=True,
                    timeout=2,
                    check=False
                )
                return result.returncode == 0
            except (FileNotFoundError, TimeoutError):
                LOGGER.debug("Ollama not available")
                return False
        elif self._provider == "gpt4all":
            # Check for GPT4All
            try:
                import gpt4all
                return True
            except ImportError:
                LOGGER.debug("GPT4All not available")
                return False
        return False
    
    def is_available(self) -> bool:
        """Check if filter is available.
        
        Returns:
            True if local LLM is available
        """
        return self._available
    
    async def scan_outgoing_data(
        self,
        data: str,
        data_type: str = "text"
    ) -> tuple[PrivacyFilterResult, Optional[Dict[str, str]]]:
        """Scan outgoing data before sending to cloud API.
        
        Args:
            data: Data to scan (text, clipboard content, screenshot OCR, etc.)
            data_type: Type of data ("text", "clipboard", "screenshot", etc.)
            
        Returns:
            Tuple of (result, anonymization_map) where result is SAFE/BLOCK/ANONYMIZE
            and anonymization_map is a dict of replacements if ANONYMIZE
        """
        if not self._available:
            # If local LLM not available, default to SAFE (no filtering)
            LOGGER.debug("Local LLM not available; skipping privacy filter")
            return PrivacyFilterResult.SAFE, None
        
        if not data or len(data.strip()) == 0:
            return PrivacyFilterResult.SAFE, None
        
        # Truncate very long data for scanning
        scan_data = data[:5000] if len(data) > 5000 else data
        
        prompt = (
            f"You are a PII/secret scanner. Analyze this {data_type}:\n\n"
            f"{scan_data}\n\n"
            "Does it contain any sensitive data (passwords, API keys, names, emails, credit cards, SSN)? "
            "Respond ONLY with 'SAFE', 'BLOCK', or 'ANONYMIZE: {{'key': 'value'}}' where the JSON map contains "
            "replacements (e.g., {{'API_KEY_123': '${API_KEY_1}'}})."
        )
        
        try:
            response = await self._query_local_llm(prompt)
            response = response.strip().upper()
            
            if response == "SAFE":
                return PrivacyFilterResult.SAFE, None
            elif response == "BLOCK":
                LOGGER.warning("Privacy filter blocked outgoing data")
                return PrivacyFilterResult.BLOCK, None
            elif response.startswith("ANONYMIZE:"):
                # Parse anonymization map
                try:
                    json_str = response.replace("ANONYMIZE:", "").strip()
                    anonymization_map = json.loads(json_str)
                    return PrivacyFilterResult.ANONYMIZE, anonymization_map
                except json.JSONDecodeError:
                    LOGGER.warning("Failed to parse anonymization map; blocking instead")
                    return PrivacyFilterResult.BLOCK, None
            else:
                # Unknown response - default to SAFE
                LOGGER.warning("Unknown privacy filter response: %s", response)
                return PrivacyFilterResult.SAFE, None
                
        except Exception as exc:
            LOGGER.error("Privacy filter scan failed: %s", exc)
            # On error, default to SAFE (don't block user)
            return PrivacyFilterResult.SAFE, None
    
    async def scan_incoming_action(
        self,
        tool_name: str,
        command: str
    ) -> PrivacyFilterResult:
        """Scan incoming tool call/action before execution.
        
        Args:
            tool_name: Name of the tool being called
            command: Command or action being executed
            
        Returns:
            PrivacyFilterResult indicating if action is SAFE or DANGEROUS
        """
        if not self._available:
            return PrivacyFilterResult.SAFE
        
        if tool_name == "execute_bash":
            prompt = (
                "You are a bash command safety filter. Is this command destructive or dangerous "
                "(e.g., rm -rf, sudo, curl | bash, dd, mkfs)?\n\n"
                f"{command}\n\n"
                "Respond ONLY with 'SAFE' or 'DANGEROUS'."
            )
        else:
            # For other tools, use generic check
            prompt = (
                "Is this action potentially dangerous or destructive?\n\n"
                f"Tool: {tool_name}\n"
                f"Action: {command}\n\n"
                "Respond ONLY with 'SAFE' or 'DANGEROUS'."
            )
        
        try:
            response = await self._query_local_llm(prompt)
            response = response.strip().upper()
            
            if response == "SAFE":
                return PrivacyFilterResult.SAFE
            elif response == "DANGEROUS" or "DANGEROUS" in response:
                LOGGER.warning("Privacy filter blocked dangerous action: %s", command)
                return PrivacyFilterResult.BLOCK
            else:
                # Unknown response - default to SAFE (let permission system handle it)
                return PrivacyFilterResult.SAFE
                
        except Exception as exc:
            LOGGER.error("Action safety scan failed: %s", exc)
            return PrivacyFilterResult.SAFE
    
    async def _query_local_llm(self, prompt: str) -> str:
        """Query local LLM with prompt.
        
        Args:
            prompt: Prompt to send to local LLM
            
        Returns:
            Response text from local LLM
        """
        if self._provider == "ollama":
            return await self._query_ollama(prompt)
        elif self._provider == "gpt4all":
            return await self._query_gpt4all(prompt)
        else:
            raise ValueError(f"Unknown local LLM provider: {self._provider}")
    
    async def _query_ollama(self, prompt: str) -> str:
        """Query Ollama local LLM.
        
        Args:
            prompt: Prompt to send
            
        Returns:
            Response text
        """
        import asyncio
        
        # Run ollama in process pool to avoid blocking
        loop = asyncio.get_running_loop()
        executor = self._process_pool if self._process_pool else None
        
        def _run_ollama() -> str:
            try:
                result = subprocess.run(
                    ["ollama", "run", self._model, prompt],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    LOGGER.warning("Ollama returned error: %s", result.stderr)
                    return "SAFE"  # Default to safe on error
            except Exception as exc:
                LOGGER.error("Ollama query failed: %s", exc)
                return "SAFE"
        
        if executor:
            return await loop.run_in_executor(executor, _run_ollama)
        else:
            return _run_ollama()
    
    async def _query_gpt4all(self, prompt: str) -> str:
        """Query GPT4All local LLM.
        
        Args:
            prompt: Prompt to send
            
        Returns:
            Response text
        """
        import asyncio
        
        loop = asyncio.get_running_loop()
        executor = self._process_pool if self._process_pool else None
        
        def _run_gpt4all() -> str:
            try:
                from gpt4all import GPT4All
                model = GPT4All(self._model)
                response = model.generate(prompt, max_tokens=50, temp=0.1)
                return response.strip()
            except Exception as exc:
                LOGGER.error("GPT4All query failed: %s", exc)
                return "SAFE"
        
        if executor:
            return await loop.run_in_executor(executor, _run_gpt4all)
        else:
            return _run_gpt4all()
    
    def anonymize_data(self, data: str, anonymization_map: Dict[str, str]) -> str:
        """Apply anonymization map to data.
        
        Args:
            data: Original data
            anonymization_map: Map of sensitive values to replacements
            
        Returns:
            Anonymized data
        """
        result = data
        for original, replacement in anonymization_map.items():
            result = result.replace(original, replacement)
        return result

