# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
LLM client abstraction layer.

Supports OpenAI (GPT-4o-mini, GPT-4o, etc.) with a pluggable design
for adding other providers (Anthropic, Google, local models).
"""
import logging
import json
import time

import server_settings as settings

logger = logging.getLogger('nepalkings.ai.llm')


class LLMClient:
    """Provider-agnostic LLM client. Easy to swap models/providers."""

    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._openai_client = None

    def choose_action(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        """
        Ask the LLM to choose an action given game context.
        Returns the raw text response from the LLM.
        """
        if self.provider == 'openai':
            return self._call_openai(system_prompt, user_prompt, temperature, max_tokens=800)
        raise ValueError(f"Unknown LLM provider: {self.provider}")

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 140,
    ) -> str:
        """Generate free-form text (non-JSON) for flavor outputs like AI chat."""
        if self.provider == 'openai':
            return self._call_openai(system_prompt, user_prompt, temperature, max_tokens=max_tokens)
        raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _get_openai_client(self):
        """Lazy-initialize OpenAI client."""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._openai_client

    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 800,
    ) -> str:
        """Call OpenAI Chat Completions API."""
        client = self._get_openai_client()
        timeout_seconds = max(float(settings.AI_LLM_TIMEOUT_SECONDS), 1.0)
        max_retries = max(int(settings.AI_LLM_MAX_RETRIES), 0)
        backoff_seconds = max(float(settings.AI_LLM_RETRY_BACKOFF_SECONDS), 0.0)
        token_cap = max(16, int(max_tokens))

        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=token_cap,
                    timeout=timeout_seconds,
                )
                content = response.choices[0].message.content.strip()
                logger.debug(f"LLM response ({self.model}, t={temperature}): {content[:200]}")
                return content
            except Exception as e:
                if attempt >= max_retries:
                    logger.error(
                        f"LLM call failed ({self.provider}/{self.model}) "
                        f"after {max_retries + 1} attempt(s): {e}"
                    )
                    raise

                sleep_seconds = backoff_seconds * (2 ** attempt)
                logger.warning(
                    f"LLM call attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {sleep_seconds:.1f}s"
                )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)


def parse_action_response(response_text: str) -> dict:
    """
    Parse the LLM's action response into a structured dict.
    Handles chain-of-thought: reasoning text followed by JSON.
    Falls back to extracting action number if JSON parse fails.
    """
    import re
    text = response_text.strip()

    # Strip markdown code fences if present
    code_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except (json.JSONDecodeError, IndexError):
            pass

    # Try direct JSON parse (response is pure JSON)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        pass

    # Find JSON objects in the text (chain-of-thought reasoning may precede it)
    json_matches = list(re.finditer(r'\{[^{}]*\}', text))
    for match in reversed(json_matches):  # Try last match first
        try:
            parsed = json.loads(match.group())
            if 'action' in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback: look for action number pattern like "Action: 1" or just "1"
    match = re.search(r'(?:action\s*[:=]\s*)?(\d+)', response_text, re.IGNORECASE)
    if match:
        return {"action": int(match.group(1))}

    logger.warning(f"Could not parse LLM response: {response_text[:200]}")
    return {"action": 1}  # Default to first action
