"""Presets de proveedores de IA.

Cada proveedor tiene su URL, modelos sugeridos, y formato de llamada.
Todos permiten modelo custom — la lista de modelos es solo sugerencia.
Google AI Studio es el default por su capa gratuita.
"""

AI_PROVIDERS: dict[str, dict] = {
    "google_ai_studio": {
        "key": "google_ai_studio",
        "label": "Google AI Studio (Gratis)",
        "api_format": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.5-flash-preview-05-20",
        "models": [
            "gemini-2.5-pro-preview-06-05",
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.5-flash-lite-preview-06-17",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemma-4-27b-it",
            "gemma-4-12b-it",
            "gemma-3-27b-it",
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
        "default_model": "google/gemini-2.5-flash-preview-05-20",
        "models": [
            "google/gemini-2.5-pro-preview-06-05",
            "google/gemini-2.5-flash-preview-05-20",
            "google/gemma-4-27b-it",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-opus-4",
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "meta-llama/llama-4-maverick",
            "meta-llama/llama-4-scout",
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
            "claude-opus-4-20250514",
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
        "default_model": "gpt-4.1-mini",
        "models": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o3",
            "o3-mini",
            "o4-mini",
        ],
        "help_url": "https://platform.openai.com/api-keys",
        "help_text": "API key de OpenAI Platform",
        "free_tier": False,
    },
    "ollama": {
        "key": "ollama",
        "label": "Ollama (Local)",
        "api_format": "openai",
        "base_url": "http://localhost:11434/v1",
        "default_model": "gemma3:27b",
        "models": [
            "gemma3:27b",
            "gemma3:12b",
            "llama4:scout",
            "llama3.3:70b",
            "qwen3:32b",
            "qwen3:8b",
            "deepseek-r1:32b",
            "mistral:latest",
        ],
        "help_url": "https://ollama.com/download",
        "help_text": "Modelos locales, sin costo, requiere GPU",
        "free_tier": True,
    },
}

# Default provider for new installations
DEFAULT_PROVIDER = "google_ai_studio"

# Agent types available in the system
AGENT_TYPES = {
    "searcher": {
        "key": "searcher",
        "label": "Buscador",
        "description": "Busca productos, precios y proveedores en el catalogo y fuentes externas",
        "icon": "search",
        "color": "#1e40af",
        "bg": "#dbeafe",
        "default_prompt": "Eres un agente buscador especializado en materiales de construccion en Bolivia. Tu trabajo es buscar productos, comparar precios entre proveedores, y encontrar las mejores opciones. Responde siempre en espanol con datos concretos.",
    },
    "updater": {
        "key": "updater",
        "label": "Actualizador",
        "description": "Actualiza precios, normaliza nombres de productos y mantiene el catalogo limpio",
        "icon": "trending-up",
        "color": "#065f46",
        "bg": "#d1fae5",
        "default_prompt": "Eres un agente actualizador de catalogo de materiales de construccion. Tu trabajo es actualizar precios, normalizar nombres de productos, corregir unidades de medida y mantener la base de datos limpia y actualizada.",
    },
    "matcher": {
        "key": "matcher",
        "label": "Coincidencias",
        "description": "Detecta duplicados, agrupa variantes y vincula productos equivalentes",
        "icon": "layers",
        "color": "#92400e",
        "bg": "#fef3c7",
        "default_prompt": "Eres un agente de matching de productos de construccion. Tu trabajo es detectar productos duplicados, identificar variantes del mismo producto (ej: diferentes marcas de cemento), y sugerir agrupaciones logicas.",
    },
    "orchestrator": {
        "key": "orchestrator",
        "label": "Orquestador",
        "description": "Coordina los demas agentes, asigna tareas y supervisa flujos de trabajo",
        "icon": "settings",
        "color": "#6d28d9",
        "bg": "#ede9fe",
        "default_prompt": "Eres el agente orquestador del sistema APU Marketplace. Tu trabajo es coordinar a los demas agentes (buscador, actualizador, matcher, comunicador), decidir que tareas asignar, priorizar el trabajo y reportar el estado general del sistema.",
    },
    "communicator": {
        "key": "communicator",
        "label": "Comunicador",
        "description": "Se comunica con proveedores via WhatsApp, Telegram y redes sociales",
        "icon": "whatsapp",
        "color": "#16a34a",
        "bg": "#dcfce7",
        "default_prompt": "Eres un agente comunicador del sistema APU Marketplace. Tu trabajo es interactuar con proveedores y clientes a traves de WhatsApp, Telegram y redes sociales. Solicitas cotizaciones, respondes consultas de precios, y mantienes una comunicacion profesional y cordial en espanol.",
    },
    "claude_code": {
        "key": "claude_code",
        "label": "Claude Code",
        "description": "Conecta con Claude Code para ejecutar skills avanzados y modificar la plataforma",
        "icon": "code",
        "color": "#dc2626",
        "bg": "#fee2e2",
        "default_prompt": "Eres un agente conectado a Claude Code con acceso a skills avanzados. Puedes ejecutar tareas de desarrollo, generar reportes complejos, analizar datos a profundidad, y extender las capacidades de la plataforma APU Marketplace.",
    },
}


def get_provider_info(provider_key: str) -> dict | None:
    """Obtener info de un proveedor por su key."""
    return AI_PROVIDERS.get(provider_key)


def get_all_providers() -> list[dict]:
    """Lista todos los proveedores disponibles."""
    return list(AI_PROVIDERS.values())


def get_all_agent_types() -> list[dict]:
    """Lista todos los tipos de agente disponibles."""
    return list(AGENT_TYPES.values())


def get_agent_type(key: str) -> dict | None:
    """Obtener info de un tipo de agente."""
    return AGENT_TYPES.get(key)
