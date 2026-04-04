# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
LLM client abstraction layer.

Supports OpenAI (GPT-4o-mini, GPT-4o, etc.) with a pluggable design
for adding other providers (Anthropic, Google, local models).
"""
import logging
import json

logger = logging.getLogger('nepalkings.ai.llm')


class LLMClient:
    """Provider-agnostic LLM client. Easy to swap models/providers."""

    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._openai_client = None

    def choose_action(self, system_prompt: str, user_prompt: str) -> str:
        """
        Ask the LLM to choose an action given game context.
        Returns the raw text response from the LLM.
        """
        if self.provider == 'openai':
            return self._call_openai(system_prompt, user_prompt)
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

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI Chat Completions API."""
        client = self._get_openai_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            content = response.choices[0].message.content.strip()
            logger.debug(f"LLM response ({self.model}): {content[:200]}")
            return content
        except Exception as e:
            logger.error(f"LLM call failed ({self.provider}/{self.model}): {e}")
            raise


def parse_action_response(response_text: str) -> dict:
    """
    Parse the LLM's action response into a structured dict.
    Expected format: JSON object with 'action' key and action-specific parameters.
    Falls back to extracting action number if JSON parse fails.
    """
    # Try JSON parse first
    try:
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1] if '\n' in text else text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            if text.startswith('json'):
                text = text[4:].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        pass

    # Fallback: look for action number pattern like "Action: 1" or just "1"
    import re
    match = re.search(r'(?:action\s*[:=]\s*)?(\d+)', response_text, re.IGNORECASE)
    if match:
        return {"action": int(match.group(1))}

    logger.warning(f"Could not parse LLM response: {response_text[:200]}")
    return {"action": 1}  # Default to first action
