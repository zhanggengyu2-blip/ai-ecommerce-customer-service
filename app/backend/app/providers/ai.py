import json
import logging
import math
import re
import time
from typing import Callable
import httpx
from app.config.settings import settings
from app.services.tracing import step, safe_url
log = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Safe provider failure code; never retains headers, URLs, or response bodies."""

    def __init__(self, message: str, code: str = "provider_error", status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _post(url: str, headers: dict, payload: dict, timeout: float = 25) -> dict:
    for attempt in range(2):
        try:
            role = 'ai.embed' if 'input' in payload else 'ai.rerank' if 'documents' in payload else 'llm.route' if 'response_format' in payload else 'llm.generate'
            with step(role, {'ai.embed': '问题向量 Embedding', 'ai.rerank': '候选重排 Rerank',
                'llm.route': 'LLM 意图分类', 'llm.generate': 'LLM 生成回复'}[role], 'remote_ai',
                input={'method': 'POST', 'url': safe_url(url), 'headers': headers, 'body': payload, 'timeout_seconds': timeout},
                model=payload.get('model', ''), attempt=attempt+1) as node, httpx.Client(timeout=httpx.Timeout(timeout, connect=4)) as client:
                response = client.post(url, headers=headers, json=payload)
                node.output({'status_code': response.status_code, 'body': response.text}, 'raw_response')
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Provider returned a non-object response")
                node.output(data)
                node.usage = data.get('usage') or {}
                return data
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == 0:
                time.sleep(0.25)
                continue
            raise ProviderError("Provider network error", "network_error") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise ProviderError(f"Provider HTTP {status}", f"http_{status}", status) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Invalid provider response", "invalid_response") from exc
    raise ProviderError("Provider unavailable")


def ai_headers(api_key: str):
    return {"Authorization": f"Bearer {api_key}"}


def embed(texts: list[str], config: dict | None = None) -> list[list[float]]:
    s = settings()
    config = config or {}
    model = config.get("embedding_model") or s.embedding_model
    dimension = int(config.get("embedding_dim") or s.embedding_dim)
    base_url = s.embedding_base_url or s.ai_base_url
    api_key = s.embedding_api_key or s.ai_api_key
    if not base_url or not api_key or not model:
        raise ProviderError("Embedding provider not configured")
    vectors = []
    for start in range(0, len(texts), 10):
        batch = texts[start:start + 10]
        data = _post(base_url.rstrip("/") + "/embeddings", ai_headers(api_key),
                     {"model": model, "input": batch, "dimensions": dimension})
        try:
            items = sorted(data["data"], key=lambda x: x["index"])
            batch_vectors = [item["embedding"] for item in items]
            valid = ([item["index"] for item in items] == list(range(len(batch)))
                     and all(isinstance(v, list) and len(v) == dimension
                             and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)
                             for v in batch_vectors))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Invalid embedding response", "invalid_response") from exc
        if not valid:
            raise ProviderError("Embedding dimension, index, or value mismatch", "invalid_response")
        vectors.extend(batch_vectors)
    return vectors


def rerank(query: str, documents: list[str], config: dict | None = None) -> list[int]:
    s = settings()
    model = (config or {}).get("rerank_model") or s.rerank_model
    if not s.rerank_url or not model:
        raise ProviderError("Reranker not configured")
    data = _post(s.rerank_url, {"Authorization": f"Bearer {s.rerank_api_key}"},
                 {"model": model, "query": query, "documents": documents}, 12)
    try:
        rows = data["results"]
        indices = [r["index"] for r in sorted(rows, key=lambda x: x["relevance_score"], reverse=True)]
        if (not indices or len(indices) != len(set(indices)) or
                any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(documents) for i in indices)):
            raise ValueError("Invalid ranking indices")
        return indices
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("Invalid reranker response") from exc


def chat(system: str, user: str, model: str | None = None, on_delta: Callable[[str], None] | None = None) -> str:
    s = settings()
    if s.llm_mode == "mock":
        source = user.split("用户问题：", 1)[0]
        match = re.search(r"答[：:]\s*([^\n]+)", source)
        response = match.group(1).strip() if match else next((line.strip("[1] ") for line in source.splitlines()
                                                                if line.startswith("[1] ")), "【知识不足】")
        response = response[:500]
        if on_delta and response:
            on_delta(response)
        with step('local.mock_generate', '本地演示知识回复', input={'system': system, 'user': user}) as node:
            node.output({'content': response})
        return response
    selected_model = model or s.llm_model
    base_url = s.llm_base_url or s.ai_base_url
    api_key = s.llm_api_key or s.ai_api_key
    if not base_url or not api_key or not selected_model:
        raise ProviderError("LLM provider not configured")
    payload = {"model": selected_model, "temperature": 0, "max_tokens": 800,
               "messages": [{"role": "system", "content": system},
                                                                          {"role": "user", "content": user}]}
    url = base_url.rstrip("/") + "/chat/completions"
    if on_delta is not None:
        parts = []
        raw_events = []
        completed = False
        node_context = step('llm.generate', 'LLM 流式生成回复', 'remote_ai', input={
            'method': 'POST', 'url': safe_url(url), 'headers': ai_headers(api_key),
            'body': {**payload, 'stream': True}, 'timeout_seconds': 45}, model=selected_model)
        node = node_context.__enter__()
        stream_error = None
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=4)) as client:
                with client.stream("POST", url, headers=ai_headers(api_key), json={**payload, "stream": True}) as response:
                    response.raise_for_status()
                    node.summary = {'http_status': response.status_code, 'stream': True}
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            raw_events.append('[DONE]')
                            completed = True
                            break
                        event = json.loads(data)
                        raw_events.append(event)
                        if event.get('usage'):
                            node.usage = event['usage']
                        if event.get("error"):
                            raise ProviderError("LLM stream reported an error", "stream_error")
                        choices = event.get("choices") or []
                        delta = choices[0].get("delta", {}).get("content") if choices else ""
                        if delta:
                            if not isinstance(delta, str):
                                raise ProviderError("Invalid LLM stream content", "invalid_response")
                            parts.append(delta)
                            on_delta(delta)
            if not completed or not parts:
                raise ProviderError("Incomplete or empty LLM stream", "incomplete_stream")
            node.output({'content': ''.join(parts).strip(), 'completed': completed})
            return "".join(parts).strip()
        except httpx.HTTPStatusError as exc:
            stream_error = exc
            node.output({'status_code': exc.response.status_code}, 'error')
            status = exc.response.status_code
            raise ProviderError(f"LLM stream HTTP {status}", f"http_{status}", status) from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            stream_error = exc
            raise ProviderError("LLM stream unavailable", "stream_unavailable") from exc
        except Exception as exc:
            stream_error = exc
            raise
        finally:
            node.output({'events': raw_events, 'partial_content': ''.join(parts), 'completed': completed}, 'raw_response')
            node_context.__exit__(type(stream_error) if stream_error else None, stream_error, None)
    data = _post(url, ai_headers(api_key), payload, 35)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError("Invalid LLM response") from exc



