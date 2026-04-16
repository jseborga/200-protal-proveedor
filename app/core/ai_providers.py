"""Presets de proveedores de IA para extraccion de documentos.

Cada proveedor tiene su URL, modelo default, y formato de llamada.
Google AI Studio es el default por su capa gratuita.
"""

AI_PROVIDERS: dict[str, dict] = {
    "google_ai_studio": {
        "key": "google_ai_studio",
        "label": "Google AI Studio (Gratis)",
        "api_format": "openai",  # usa formato OpenAI-compatible
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
        "models": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        "help_url": "https://aistudio.google.com/apikey",
        "help_text": "Obtener key gratis en aistudio.google.com",
        "free_tier": True,
    },
    "openrouter": {
        "key": "openrouter",
        "label": "OpenRouter (Multi-modelo)",
        "api_format": "openrouter",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemini-2.0-flash-exp:free",
        "models": [
            "google/gemini-2.0-flash-exp:free",
            "google/gemini-2.0-flash-001",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
        ],
        "help_url": "https://openrouter.ai/keys",
        "help_text": "Una key, acceso a todos los modelos",
        "free_tier": False,
    },
    "anthropic": {
        "key": "anthropic",
        "label": "Anthropic (Claude)",
        "api_format": "anthropic",
        "base_url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-sonnet-4-20250514",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
        ],
        "help_url": "https://console.anthropic.com/settings/keys",
        "help_text": "API key de Anthropic Console",
        "free_tier": False,
    },
    "openai": {
        "key": "openai",
        "label": "OpenAI (GPT)",
        "api_format": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
        ],
        "help_url": "https://platform.openai.com/api-keys",
        "help_text": "API key de OpenAI Platform",
        "free_tier": False,
    },
}

# Default provider for new installations
DEFAULT_PROVIDER = "google_ai_studio"


def get_provider_info(provider_key: str) -> dict | None:
    """Obtener info de un proveedor por su key."""
    return AI_PROVIDERS.get(provider_key)


def get_all_providers() -> list[dict]:
    """Lista todos los proveedores disponibles."""
    return list(AI_PROVIDERS.values())
