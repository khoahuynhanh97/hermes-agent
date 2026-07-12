"""
core/ai_router.py — Multi-Provider AI Router (9router-style)

Supports: Google Gemini, Groq, Cerebras, Mistral, OpenRouter, Together AI, Ollama (local)
Auto-fallback, rate limit tracking, task-based model selection.
"""
import os
import sys
import json
import time
import logging
import requests
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider Definitions
# ---------------------------------------------------------------------------
PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "type": "gemini",
        "models": {
            "default": "gemini-2.5-flash",
            "vision": "gemini-2.5-flash",
            "fast": "gemini-2.0-flash-lite",
        },
        "rpm_limit": 15,
        "supports_vision": True,
    },
    "groq": {
        "name": "Groq",
        "env_key": "GROQ_API_KEY",
        "type": "openai_compat",
        "base_url": "https://api.groq.com/openai/v1",
        "models": {
            "default": "llama-3.3-70b-versatile",
            "fast": "llama-3.1-8b-instant",
            "vision": "llama-3.2-11b-vision-preview",
        },
        "rpm_limit": 30,
        "supports_vision": False,
    },
    "cerebras": {
        "name": "Cerebras",
        "env_key": "CEREBRAS_API_KEY",
        "type": "openai_compat",
        "base_url": "https://api.cerebras.ai/v1",
        "models": {
            "default": "llama-3.3-70b",
            "fast": "llama-3.1-8b",
        },
        "rpm_limit": 30,
        "supports_vision": False,
    },
    "mistral": {
        "name": "Mistral AI",
        "env_key": "MISTRAL_API_KEY",
        "type": "openai_compat",
        "base_url": "https://api.mistral.ai/v1",
        "models": {
            "default": "mistral-small-latest",
            "fast": "mistral-small-latest",
        },
        "rpm_limit": 30,
        "supports_vision": False,
    },
    "openrouter": {
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "type": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
        "models": {
            "default": "meta-llama/llama-3.3-70b-instruct:free",
            "fast": "microsoft/phi-3-mini-128k-instruct:free",
            "vision": "google/gemini-2.0-flash-exp:free",
        },
        "rpm_limit": 20,
        "supports_vision": True,
    },
    "together": {
        "name": "Together AI",
        "env_key": "TOGETHER_API_KEY",
        "type": "openai_compat",
        "base_url": "https://api.together.xyz/v1",
        "models": {
            "default": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            "fast": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        },
        "rpm_limit": 60,
        "supports_vision": False,
    },
    "ollama": {
        "name": "Ollama (Local)",
        "env_key": None,
        "type": "ollama",
        "base_url": None,  # Loaded from config
        "models": {
            "default": None,  # Loaded from config
        },
        "rpm_limit": 9999,
        "supports_vision": False,
    },
}

# Task → preferred provider order
TASK_ROUTING = {
    "vision":       ["gemini", "openrouter", "groq"],           # Must support images
    "script":       ["cerebras", "groq", "gemini", "mistral"],  # Speed priority
    "translation":  ["gemini", "groq", "mistral"],              # Quality priority
    "ideas":        ["groq", "cerebras", "gemini"],             # Creative, speed
    "analysis":     ["gemini", "groq", "openrouter"],           # Nuanced reasoning
    "default":      ["gemini", "groq", "cerebras", "mistral", "openrouter", "together", "ollama"],
}


class ProviderState:
    """Track rate limit state for a single provider."""
    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self.request_times = []
        self.error_count = 0
        self.last_error = None
        self.disabled_until = 0.0  # Unix timestamp

    def is_available(self) -> bool:
        now = time.time()
        if now < self.disabled_until:
            return False
        # Clean old request times (older than 60s)
        self.request_times = [t for t in self.request_times if now - t < 60]
        rpm = PROVIDERS.get(self.provider_id, {}).get("rpm_limit", 15)
        return len(self.request_times) < rpm

    def record_request(self):
        self.request_times.append(time.time())

    def record_error(self, error: str, backoff_seconds: float = 60.0):
        self.error_count += 1
        self.last_error = error
        self.disabled_until = time.time() + backoff_seconds
        logger.warning(f"[AIRouter] Provider {self.provider_id} disabled for {backoff_seconds}s: {error[:80]}")

    def get_status(self) -> dict:
        now = time.time()
        if now < self.disabled_until:
            return {"status": "rate_limited", "retry_in": int(self.disabled_until - now)}
        rpm = PROVIDERS.get(self.provider_id, {}).get("rpm_limit", 15)
        recent = len([t for t in self.request_times if now - t < 60])
        return {
            "status": "active" if recent < rpm else "busy",
            "requests_last_60s": recent,
            "rpm_limit": rpm,
            "error_count": self.error_count,
        }


class AIRouter:
    """
    Multi-provider AI router with automatic fallback and rate limit tracking.
    Supports Gemini, Groq, Cerebras, Mistral, OpenRouter, Together AI, Ollama.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.states: dict[str, ProviderState] = {
            pid: ProviderState(pid) for pid in PROVIDERS
        }
        self.strategy = os.environ.get("AI_ROUTER_STRATEGY", "balanced")
        logger.info(f"[AIRouter] Initialized. Strategy: {self.strategy}")

    def _get_api_key(self, provider_id: str) -> Optional[str]:
        pdef = PROVIDERS[provider_id]
        env_key = pdef.get("env_key")
        if not env_key:
            return None  # Ollama doesn't need a key
        return os.environ.get(env_key, "") or getattr(config, env_key, "")

    def _get_available_providers(self, task_type: str = "default") -> list[str]:
        """Return ordered list of available providers for a task."""
        preferred = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])
        result = []
        for pid in preferred:
            if pid not in PROVIDERS:
                continue
            key = self._get_api_key(pid)
            # Ollama doesn't need a key
            if pid != "ollama" and not key:
                continue
            if self.states[pid].is_available():
                result.append(pid)
        # Append any remaining available providers not in preferred list
        for pid in TASK_ROUTING["default"]:
            if pid not in result:
                key = self._get_api_key(pid)
                if pid != "ollama" and not key:
                    continue
                if self.states[pid].is_available():
                    result.append(pid)
        return result

    def _call_gemini(self, api_key: str, model: str, prompt: str, system: str = "") -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        parts = []
        if system:
            parts.append({"text": f"[System]: {system}\n\n[User]: {prompt}"})
        else:
            parts.append({"text": prompt})
        payload = {"contents": [{"parts": parts}]}
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 429:
            raise RateLimitError(f"Gemini 429: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_openai_compat(self, provider_id: str, api_key: str, model: str,
                            prompt: str, system: str = "") -> str:
        pdef = PROVIDERS[provider_id]
        base_url = pdef["base_url"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter needs extra headers
        if provider_id == "openrouter":
            headers["HTTP-Referer"] = "https://hermes-video-factory"
            headers["X-Title"] = "Hermes Video Factory"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model, "messages": messages, "temperature": 0.7}
        resp = requests.post(f"{base_url}/chat/completions", headers=headers,
                             json=payload, timeout=60)
        if resp.status_code == 429:
            raise RateLimitError(f"{provider_id} 429: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_ollama(self, model: str, prompt: str, system: str = "") -> str:
        ollama_url = getattr(config, "OLLAMA_API_URL", "http://localhost:11434")
        model = model or getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def chat(self, prompt: str, system: str = "", task_type: str = "default",
             max_tokens: int = 4096) -> str:
        """
        Send a prompt and get a response. Auto-selects best available provider.
        task_type: 'vision', 'script', 'translation', 'ideas', 'analysis', 'default'
        """
        providers = self._get_available_providers(task_type)
        if not providers:
            raise RuntimeError("[AIRouter] No providers available. Configure at least one API key.")

        last_error = None
        for pid in providers:
            pdef = PROVIDERS[pid]
            ptype = pdef["type"]
            model_key = "default"
            if task_type == "vision" and pdef.get("supports_vision"):
                model_key = "vision"
            elif task_type in ("script", "ideas"):
                model_key = "fast" if "fast" in pdef["models"] else "default"

            model = pdef["models"].get(model_key) or pdef["models"].get("default")
            api_key = self._get_api_key(pid)

            try:
                self.states[pid].record_request()
                logger.info(f"[AIRouter] Using {pdef['name']} ({model}) for task={task_type}")

                if ptype == "gemini":
                    result = self._call_gemini(api_key, model, prompt, system)
                elif ptype == "openai_compat":
                    result = self._call_openai_compat(pid, api_key, model, prompt, system)
                elif ptype == "ollama":
                    result = self._call_ollama(model, prompt, system)
                else:
                    continue

                return result

            except RateLimitError as e:
                self.states[pid].record_error(str(e), backoff_seconds=65.0)
                last_error = e
                logger.warning(f"[AIRouter] Rate limited on {pid}, trying next...")
                continue
            except Exception as e:
                self.states[pid].record_error(str(e), backoff_seconds=30.0)
                last_error = e
                logger.warning(f"[AIRouter] Error on {pid}: {e}, trying next...")
                continue

        raise RuntimeError(f"[AIRouter] All providers failed. Last error: {last_error}")

    def get_status(self) -> dict:
        """Return status of all providers (for GUI display)."""
        result = {}
        for pid, pdef in PROVIDERS.items():
            key = self._get_api_key(pid)
            has_key = bool(key) or pid == "ollama"
            status = self.states[pid].get_status() if has_key else {"status": "no_key"}
            result[pid] = {
                "name": pdef["name"],
                "has_key": has_key,
                **status,
            }
        return result


class RateLimitError(Exception):
    pass


# Singleton instance
_router = None

def get_router() -> AIRouter:
    """Get or create the global AIRouter singleton."""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router


def chat(prompt: str, system: str = "", task_type: str = "default") -> str:
    """Convenience function — calls the global router."""
    return get_router().chat(prompt, system=system, task_type=task_type)
