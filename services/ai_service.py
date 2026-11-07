import asyncio
import re
from functools import partial

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, GROQ_API_KEY, GROQ_MODEL
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _is_anthropic_billing_or_unavailable(exc: Exception) -> bool:
    """Возвращает True если ошибка связана с балансом или недоступностью Anthropic"""
    if isinstance(exc, anthropic.APIStatusError):
        # 402 Payment Required, 429 Rate Limit, 529 Overloaded
        if exc.status_code in (402, 429, 529):
            return True
        # Billing-related messages
        msg = str(exc).lower()
        if any(kw in msg for kw in ("credit", "balance", "billing", "quota", "overload", "capacity")):
            return True
    return isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError))


class AIService:
    """Сервис для работы с Anthropic Claude (основной) и Groq (fallback)"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model_name = CLAUDE_MODEL

        self._groq_client = None
        if GROQ_API_KEY:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=GROQ_API_KEY)
                logger.info(f"Groq fallback enabled: {GROQ_MODEL}")
            except ImportError:
                logger.warning("groq package not installed — fallback disabled")

        logger.info("AIService initialized")
        logger.info(f"Primary model: {self.model_name}")

    def _call_groq(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        logger.info(f"Falling back to Groq model: {GROQ_MODEL}")
        response = self._groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        result = response.choices[0].message.content.strip()
        if not result:
            raise RuntimeError(f"Empty response from Groq model: {GROQ_MODEL}")
        logger.info(f"Groq success | response length={len(result)}")
        return result

    def _call_ai(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 1024
    ) -> str:
        logger.info(f"Calling model: {self.model_name}")

        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            result = response.content[0].text.strip()

            if not result:
                raise RuntimeError(f"Empty response from model: {self.model_name}")

            logger.info(f"Model success: {self.model_name} | response length={len(result)}")
            return result

        except Exception as e:
            if self._groq_client and _is_anthropic_billing_or_unavailable(e):
                logger.warning(f"Anthropic unavailable ({type(e).__name__}: {e}), switching to Groq")
                return self._call_groq(system_prompt, user_message, temperature, max_tokens)
            raise

    async def _call_ai_async(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 1024
    ) -> str:
        """
        Асинхронная обёртка над _call_ai — уводит блокирующий вызов Anthropic/Groq SDK
        в отдельный поток, чтобы не замораживать event loop сервера на время генерации ответа.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self._call_ai, system_prompt, user_message, temperature, max_tokens)
        )

    def _extract_json_block(self, text: str) -> str:
        """
        Пытается вытащить JSON даже если модель вернула лишний текст
        """
        if not text:
            return text

        text = text.strip()

        fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            return obj_match.group(0).strip()

        arr_match = re.search(r"\[.*\]", text, re.DOTALL)
        if arr_match:
            return arr_match.group(0).strip()

        return text


# ── Module-level singleton and helper ────────────────────────────────
# call_model() is a thin convenience wrapper used by simple one-off YES/NO
# validation prompts (see consultation_agent.validate_symptoms and
# bot/handlers/profile.py's allergy/disease validation). It was previously
# imported but never defined, causing every call site to silently fall back
# to "always valid" via a caught ImportError.
_default_ai_service: "AIService | None" = None


def _get_default_ai_service() -> "AIService":
    global _default_ai_service
    if _default_ai_service is None:
        _default_ai_service = AIService()
    return _default_ai_service


async def call_model_async(prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
    """Async version — runs the blocking SDK call in a thread executor."""
    service = _get_default_ai_service()
    return await service._call_ai_async(system_prompt="", user_message=prompt,
                                         temperature=temperature, max_tokens=max_tokens)
