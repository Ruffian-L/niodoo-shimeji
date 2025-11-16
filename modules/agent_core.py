"""Core cognitive helpers extracted from the dual-mode agent.

The goal of this module is to decouple heavyweight cognitive/workflow
logic from the UI/process orchestration that lives in
``shimeji_dual_mode_agent.py``.  Functions here operate purely on injected
collaborators (brains, overlays, process pools) so they can be re-used by
future FastAPI services or alternative presentation layers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import Executor
from typing import Any, Optional, TYPE_CHECKING

import google.generativeai as genai
from google.generativeai import types as genai_types

from modules.constants import DEFAULT_PRO_MODEL
from modules.genai_utils import get_cached_model
from modules.presentation_api import UIEvent

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from modules.brains import CLIBrain
    from modules.presentation_api import AvatarClient, UIEventSink
    from shimeji_dual_mode_agent import DualModeAgent


class AgentCore:
    """Container for reusable agent behaviours and helpers."""

    def __init__(
        self,
        *,
        cli_brain: "CLIBrain",
        avatar_client: "AvatarClient",
        ui_event_sink: "UIEventSink",
        process_pool: Optional[Executor],
    ) -> None:
        self._cli_brain = cli_brain
        self._avatar_client = avatar_client
        self._ui_event_sink = ui_event_sink
        self._process_pool = process_pool

    async def process_cli_prompt(self, agent: "DualModeAgent", prompt: str) -> None:
        """Process a CLI prompt, including vision and chat updates."""

        # Image analysis shortcut: "[IMAGE_ANALYZE:/path] question"
        if prompt.startswith("[IMAGE_ANALYZE:"):
            match = re.match(r"\[IMAGE_ANALYZE:(.+?)\]\s*(.*)", prompt)
            if match:
                image_path = match.group(1)
                question = match.group(2) or "What do you see in this image? Describe it in detail."
                self._show_typing_indicator()
                try:
                    analysis = await self._analyze_image_with_vision(image_path, question)
                    self._hide_typing_indicator()
                    if analysis:
                        self._emit_chat("Shimeji", f"Image Analysis:\n{analysis}")
                    else:
                        self._emit_chat("Shimeji", "Couldn't analyze image.")
                except Exception as exc:  # pragma: no cover - runtime dependent
                    LOGGER.exception("Image analysis failed: %s", exc)
                    self._hide_typing_indicator()
                    self._emit_chat("Shimeji", f"Failed to analyze image: {exc}")
                return

        self._show_typing_indicator()

        try:
            response = await self._cli_brain.respond(prompt, agent)
            self._hide_typing_indicator()

            if response:
                response = self.add_emojis(response)
                self._emit_chat("Shimeji", response)
                if len(response.split()) <= 30:
                    self._emit_bubble("Shimeji", response, duration=8)
                else:
                    short_response = " ".join(response.split()[:15]) + "..."
                    self._emit_bubble("Shimeji", short_response, duration=5)
        except (genai_types.BlockedPromptException, genai_types.StopCandidateException) as exc:
            LOGGER.warning("Gemini API error: %s", exc)
            self._hide_typing_indicator()
            self._emit_chat(
                "Shimeji",
                "Sorry, I can't process that request right now. Please try again.",
            )
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.exception("Unexpected error in CLI prompt: %s", exc)
            self._hide_typing_indicator()
            self._emit_chat("Shimeji", f"Oops! Something went wrong: {exc}")

    def _emit_chat(self, author: str, text: str) -> None:
        if not text or not self._ui_event_sink:
            return
        self._ui_event_sink.emit(UIEvent("chat_message", {"author": author, "text": text}))

    def _emit_bubble(self, author: str, text: str, *, duration: int) -> None:
        if not text or not self._ui_event_sink:
            return
        payload = {"author": author, "text": text, "duration": int(max(1, duration))}
        self._ui_event_sink.emit(UIEvent("bubble_message", payload))

    def _show_typing_indicator(self) -> None:
        if self._ui_event_sink:
            self._ui_event_sink.emit(UIEvent("chat_typing", {"state": "show"}))

    def _hide_typing_indicator(self) -> None:
        if self._ui_event_sink:
            self._ui_event_sink.emit(UIEvent("chat_typing", {"state": "hide"}))

    async def _analyze_image_with_vision(self, image_path: str, question: str) -> Optional[str]:
        if not os.path.exists(image_path):
            return None

        loop = asyncio.get_running_loop()
        vision_model = get_cached_model(DEFAULT_PRO_MODEL)
        executor = self._process_pool
        try:
            response = await loop.run_in_executor(
                executor,
                lambda: vision_model.generate_content([image_path, question]),
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.debug("Direct file path failed, trying PIL: %s", exc)
            return await self._analyze_with_pil_fallback(image_path, question, vision_model, loop)

    async def _analyze_with_pil_fallback(
        self,
        image_path: str,
        question: str,
        model: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> Optional[str]:
        try:
            import PIL.Image

            def _generate_content(img_path: str, q: str, mdl) -> Any:
                img = PIL.Image.open(img_path)
                return mdl.generate_content([img, q])

            response = await loop.run_in_executor(
                self._process_pool,
                _generate_content,
                image_path,
                question,
                model,
            )
            return self._extract_text_from_response(response)
        except ImportError:
            return await self._analyze_with_upload_fallback(image_path, question, model, loop)
        except Exception as exc:
            LOGGER.error("PIL fallback failed: %s", exc)
            return None

    async def _analyze_with_upload_fallback(
        self,
        image_path: str,
        question: str,
        model: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> Optional[str]:
        uploaded_file = None
        try:
            def _upload_file(path: str) -> Any:
                return genai.upload_file(path=path)

            def _generate_with_upload(uf, q: str, mdl) -> Any:
                return mdl.generate_content([uf, q])

            executor = self._process_pool
            uploaded_file = await loop.run_in_executor(executor, _upload_file, image_path)
            response = await loop.run_in_executor(
                executor,
                _generate_with_upload,
                uploaded_file,
                question,
                model,
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.error("Upload fallback failed: %s", exc)
            return None
        finally:
            if uploaded_file is not None:
                try:
                    def _delete_file(name: str) -> None:
                        genai.delete_file(name)

                    await loop.run_in_executor(self._process_pool, _delete_file, uploaded_file.name)
                except Exception as cleanup_exc:
                    LOGGER.warning("Failed to cleanup uploaded file: %s", cleanup_exc)

    @staticmethod
    def _extract_text_from_response(response) -> Optional[str]:
        text_parts = []
        for candidate in getattr(response, "candidates", []):
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            for part in getattr(content, "parts", []):
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(text)
        return " ".join(text_parts) if text_parts else None

    @staticmethod
    def add_emojis(text: str) -> str:
        if text.endswith("!"):
            return text[:-1] + "! 😎"
        if text.endswith("?"):
            return text[:-1] + "? 🤔"
        return text

    @staticmethod
    def get_random_fact(topic: Optional[str] = None) -> str:
        try:
            import wikipediaapi
        except ImportError:
            return "Did you know? The universe is expanding faster than expected!"

        wiki = wikipediaapi.Wikipedia("en")
        if topic:
            page = wiki.page(topic)
            if page.exists():
                summaries = page.summary.split('. ')
                return summaries[0].strip() + '.' if summaries else page.summary
        return "Did you know? The universe is expanding faster than expected!"
