"""ZhipuAI LLM client for Chinese/English/French support."""

import os
import time
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Try to import zhipuai SDK
try:
    from zhipuai import ZhipuAI

    ZHIPUAI_SDK_AVAILABLE = True
except ImportError:
    ZHIPUAI_SDK_AVAILABLE = False

load_dotenv()


def _get_default_model() -> str:
    """Get default model from environment variable.

    Returns uppercase model ID for ZhipuAI API.
    Available models: GLM-4.5, GLM-4.5-AIR, GLM-4.6, GLM-4.7, GLM-5
    """
    model = os.getenv("AI_MODEL")
    if not model:
        raise ValueError("AI_MODEL is required in .env file")

    # Normalize to uppercase for API compatibility
    model_upper = model.upper().replace("_", "-")

    # Handle GLM models - use uppercase format
    if "GLM" in model_upper:
        # Specific model mappings
        if "GLM-4.7" in model_upper or "GLM47" in model_upper:
            return "GLM-4.7"
        elif "GLM-4-FLASH" in model_upper or "GLMFLASH" in model_upper:
            return "GLM-4-FLASH"
        elif "GLM-4-PLUS" in model_upper or "GLMPLUS" in model_upper:
            return "GLM-4-PLUS"
        elif "GLM-4.5" in model_upper or "GLM45" in model_upper:
            # GLM-4.5 models
            if "AIR" in model_upper:
                return "GLM-4.5-AIR"
            else:
                return "GLM-4.5"
        elif "GLM-4.6" in model_upper or "GLM46" in model_upper:
            return "GLM-4.6"
        elif "GLM-5" in model_upper or "GLM5" in model_upper:
            return "GLM-5"
        # For other GLM models, ensure uppercase format
        return model_upper

    # For non-GLM models, return as-is
    return model


class ZhipuAIClient:
    """Client for ZhipuAI API (GLM models)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        max_tokens: int = 8000,
    ):
        """
        Initialize the ZhipuAI client.

        Args:
            api_key: ZhipuAI API key (format: id.secret). If None, reads from AI_API_KEY env var.
            base_url: Custom base URL for API requests. If None, reads from AI_BASE_URL env var.
            model: Model to use (glm-4-flash, glm-4-plus, GLM-4.7, etc.). If None, reads from AI_MODEL env var.
            timeout: Request timeout in seconds
            max_tokens: Maximum tokens in response
        """
        # Read from environment variables if not provided
        self.api_key = api_key or os.getenv("AI_API_KEY")
        self.base_url = (
            (base_url or os.getenv("AI_BASE_URL")).rstrip("/")
            if base_url or os.getenv("AI_BASE_URL")
            else None
        )
        self.model = model or _get_default_model()
        self.timeout = timeout
        self.max_tokens = max_tokens

        # Validate required configuration
        if not self.api_key:
            raise ValueError(
                "AI_API_KEY is required in .env file or pass api_key parameter"
            )

        if not self.base_url:
            raise ValueError(
                "AI_BASE_URL is required in .env file or pass base_url parameter"
            )

        if "." not in self.api_key:
            raise ValueError(
                "Invalid API key format. Expected: id.secret (e.g., 1234.abcd...)"
            )

        # Try to use SDK first, fall back to REST API
        self._use_sdk = ZHIPUAI_SDK_AVAILABLE
        if self._use_sdk:
            try:
                # Use custom base_url for the coding endpoint
                self.client = ZhipuAI(api_key=self.api_key, base_url=self.base_url)
            except Exception:
                self._use_sdk = False

    def health_check(self) -> bool:
        """Check if the API is accessible."""
        if self._use_sdk:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=10,
                )
                return True
            except Exception:
                return False
        else:
            # REST API health check
            try:
                headers = self._get_headers()
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 10,
                    },
                    timeout=5,
                )
                return response.status_code == 200
            except Exception:
                return False

    def _get_headers(self) -> Dict[str, str]:
        """Generate headers for REST API.

        ZhipuAI API uses the API key directly as Bearer token.
        No JWT encoding required.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _call_sdk(
        self,
        messages: list,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Call using ZhipuAI SDK."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=temperature,
            )

            return {
                "success": True,
                "response": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "response": "",
                "usage": {},
                "error": str(e),
            }

    def _call_rest_api(
        self,
        messages: list,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Call using REST API."""
        try:
            headers = self._get_headers()
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": temperature,
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )

            data = response.json()

            if response.status_code == 200 and "choices" in data:
                return {
                    "success": True,
                    "response": data["choices"][0]["message"]["content"],
                    "usage": data.get("usage", {}),
                    "error": None,
                }
            else:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                return {
                    "success": False,
                    "response": "",
                    "usage": {},
                    "error": f"API error: {error_msg}",
                }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "response": "",
                "usage": {},
                "error": f"Request timeout after {self.timeout}s",
            }
        except Exception as e:
            return {
                "success": False,
                "response": "",
                "usage": {},
                "error": str(e),
            }

    def chat(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Send a chat request to ZhipuAI.

        Args:
            prompt: The user question/prompt
            context: Optional context (document excerpts)
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)

        Returns:
            Dict with 'success', 'response', 'usage', 'error'
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            messages.append({"role": "system", "content": f"Context:\n\n{context}"})

        messages.append({"role": "user", "content": prompt})

        # Try SDK first, fall back to REST API
        if self._use_sdk:
            result = self._call_sdk(messages, temperature)
            if result["success"]:
                return result
            # SDK failed, try REST API
            return self._call_rest_api(messages, temperature)
        else:
            return self._call_rest_api(messages, temperature)

    def chat_timed(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> tuple[Dict[str, Any], float]:
        """
        Chat with timing.

        Returns:
            Tuple of (result, time_ms)
        """
        start = time.time()
        result = self.chat(prompt, context, system_prompt, temperature)
        elapsed_ms = (time.time() - start) * 1000
        return result, elapsed_ms
