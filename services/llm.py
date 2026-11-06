import requests

DEFAULT_MODELS = {
    "openrouter": [
        {"id": "deepseek/deepseek-v4.1-flash", "name": "DeepSeek v4.1 Flash (Recommended)"},
        {"id": "anthropic/claude-3.7-sonnet", "name": "Claude 3.7 Sonnet"},
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct"},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o (Recommended)"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
    ],
    "fireworks": [
        {"id": "accounts/fireworks/models/deepseek-v3", "name": "DeepSeek v3 (Recommended)"},
        {"id": "accounts/fireworks/models/deepseek-r1", "name": "DeepSeek R1"},
        {"id": "accounts/fireworks/models/llama-v3p3-70b-instruct", "name": "Llama 3.3 70B Instruct"},
        {"id": "accounts/fireworks/models/qwen2p5-72b-instruct", "name": "Qwen 2.5 72B Instruct"},
    ],
    "custom": [
        {"id": "custom-model", "name": "Custom Model (specify ID)"},
    ],
}


def _resolve_endpoint(provider, base_url=None):
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1/chat/completions"
    elif provider == "openai":
        return "https://api.openai.com/v1/chat/completions"
    elif provider == "fireworks":
        return "https://api.fireworks.ai/inference/v1/chat/completions"
    elif provider == "custom":
        if not base_url:
            raise ValueError("Custom provider requires a Base URL.")
        clean_url = base_url.rstrip("/")
        if not clean_url.endswith("/chat/completions"):
            clean_url += "/chat/completions"
        return clean_url
    else:
        raise ValueError(f"Unknown provider '{provider}'")


def call_llm(messages, api_key, model, provider="openrouter", base_url=None, temperature=0.3, max_tokens=4000, **kwargs):
    if not api_key and provider in ["openrouter", "openai", "fireworks"]:
        raise ValueError(f"API key is required for provider '{provider}'.")
    if not model:
        raise ValueError("Model is required.")

    endpoint = _resolve_endpoint(provider, base_url)
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://persona-cloner.local"
        headers["X-Title"] = "Persona Cloner Web"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    payload.update(kwargs)

    try:
        r = requests.post(endpoint, headers=headers, json=payload, timeout=120)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Connection error to {endpoint}: {str(e)}")

    if r.status_code != 200:
        err_msg = r.text[:400]
        try:
            err_json = r.json()
            if "error" in err_json:
                err_msg = err_json["error"].get("message", err_msg)
        except Exception:
            pass
        raise RuntimeError(f"{provider.capitalize()} API error ({r.status_code}): {err_msg}")

    try:
        data = r.json()
        choice = data["choices"][0]["message"]
        return choice.get("content") or ""
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Unexpected response format from {provider}: {str(e)}")


def test_connection(api_key, model, provider="openrouter", base_url=None):
    messages = [
        {"role": "user", "content": "Hello! Reply with 'OK' only."},
    ]
    try:
        content = call_llm(
            messages=messages,
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
            temperature=0.1,
            max_tokens=10,
        )
        return True, f"Success! Model responded: {content.strip()}"
    except Exception as e:
        return False, str(e)
