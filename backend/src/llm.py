"""LLM client using GitHub Copilot Bridge."""

import time
from typing import Dict, Any, Optional
import requests


class CopilotBridgeClient:
    """Client for GitHub Copilot Bridge API."""

    def __init__(
        self,
        base_url: str = "http://localhost:1287",
        model_id: str = "gpt-5-mini",
        timeout: int = 60000,
        max_tokens: int = 8000,
    ):
        """
        Initialize the Copilot Bridge client.

        Args:
            base_url: Copilot Bridge server URL
            model_id: Model ID to use
            timeout: Request timeout in milliseconds
            max_tokens: Maximum tokens in response
        """
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout = timeout
        self.max_tokens = max_tokens

    def health_check(self) -> bool:
        """Check if the server is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def get_models(self) -> list:
        """Get available models."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10)
            data = response.json()
            return data.get("models", [])
        except Exception:
            return []

    def chat(
        self,
        prompt: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request to Copilot Bridge.

        Args:
            prompt: The question/prompt
            context: Optional context (document excerpts)
            session_id: Optional session ID for multi-turn

        Returns:
            Dict with 'success', 'response', 'usage', 'error'
        """
        payload = {
            "prompt": prompt,
            "model_id": self.model_id,
            "maxToken": self.max_tokens,
            "timeout": self.timeout,
        }

        if context:
            payload["context"] = context

        if session_id:
            payload["sessionId"] = session_id

        try:
            response = requests.post(
                f"{self.base_url}/chat",
                json=payload,
                timeout=self.timeout / 1000 + 10,  # Add buffer
                headers={"Content-Type": "application/json"},
            )

            data = response.json()

            return {
                "success": data.get("success", False),
                "response": data.get("response", ""),
                "usage": data.get("usage", {}),
                "error": data.get("error"),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "response": "",
                "error": "Copilot Bridge not running. Start it in VS Code: Cmd+Shift+P → 'Start Copilot Bridge Server'",
            }
        except Exception as e:
            return {
                "success": False,
                "response": "",
                "error": str(e),
            }

    def chat_timed(
        self,
        prompt: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> tuple[Dict[str, Any], float]:
        """
        Chat with timing.

        Returns:
            Tuple of (result, time_ms)
        """
        start = time.time()
        result = self.chat(prompt, context, session_id)
        elapsed_ms = (time.time() - start) * 1000
        return result, elapsed_ms
