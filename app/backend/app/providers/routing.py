import json
from app.config.settings import settings
from app.providers.ai import ProviderError, _post, ai_headers
from app.schemas.routing import RoutingDecision

def classify(context: dict, model: str | None = None, instruction: str | None = None) -> RoutingDecision:
    s = settings()
    base_url, api_key = s.llm_base_url or s.ai_base_url, s.llm_api_key or s.ai_api_key
    if not base_url or not api_key:
        raise ProviderError("Routing provider not configured", "routing_unavailable")
    if not instruction or not instruction.strip():
        raise ProviderError("Routing prompt not configured", "routing_prompt_missing")
    result = _post(base_url.rstrip("/") + "/chat/completions", ai_headers(api_key), {
        "model": model or s.llm_model, "temperature": 0, "max_tokens": 1024,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": instruction},
                     {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
    }, s.routing_timeout_seconds)
    try:
        choice = result["choices"][0]
        raw = choice["message"]["content"]
        if raw == "" and choice.get("finish_reason") == "length":
            raise ProviderError("Routing output budget exhausted", "routing_output_exhausted")
        if not isinstance(raw, str) or len(raw) > 6000:
            raise ValueError("Invalid routing output")
        return RoutingDecision.model_validate_json(raw)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("Invalid routing output", "routing_invalid") from exc
