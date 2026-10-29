"""Generate candidate chunks; AI only groups source paragraphs and cannot invent rule text."""
import json
import re
from fastapi import HTTPException
from app.config.settings import settings
from app.providers.ai import _post, ai_headers, ProviderError


def paragraphs_for(content: str) -> list[str]:
    return [part.strip() for part in re.split(r'\n\s*\n', content) if part.strip()]


def suggest_chunks(content: str, strategy: str, target_chars: int = 800,
                   instruction: str | None = None,
                   overlap_chars: int = 100) -> list[dict]:
    if strategy == 'length':
        if not 200 <= target_chars <= 4000 or not 0 <= overlap_chars < target_chars // 2:
            raise HTTPException(422, '切片长度应为 200–4000 字符，重叠须小于长度的一半')
        result, start = [], 0
        while start < len(content):
            end = min(start + target_chars, len(content))
            text = content[start:end].strip()
            if text:
                preceding = content[:start].splitlines()
                section = preceding[-1].strip()[:80] if preceding else ''
                result.append({'section': section or text.splitlines()[0][:80],
                               'content': text, 'tags': {}})
            if len(result) > 200:
                raise HTTPException(422, '切片超过 200 条，请增加长度或按业务段落分组')
            if end == len(content):
                break
            start = end - overlap_chars
        return result
    if strategy == 'semantic':
        lines = content.splitlines()
        result, current, section = [], [], ''
        heading = re.compile(r'^\s*(?:#{1,4}\s+|第[一二三四五六七八九十\d]+[章节条]|\d+[.、]\s*|【[^】]{1,40}】)')
        for line in lines:
            if heading.match(line) and current:
                result.append({'section': section or current[0][:80],
                               'content': '\n'.join(current).strip(), 'tags': {}})
                current = []
            if heading.match(line):
                section = line.strip()[:80]
            current.append(line)
        if current and '\n'.join(current).strip():
            result.append({'section': section or current[0][:80],
                           'content': '\n'.join(current).strip(), 'tags': {}})
        return result or suggest_chunks(content, 'length', target_chars, overlap_chars=overlap_chars)
    if strategy != 'ai':
        raise HTTPException(422, '不支持的切片方式')
    parts = paragraphs_for(content)
    if not parts or len(parts) > 40 or len(content) > 12000:
        raise HTTPException(422, 'AI 分析限 40 个段落、1.2 万字符；可先用业务段落或手动切片')
    numbered = '\n\n'.join(f'[{i}] {part}' for i, part in enumerate(parts, 1))
    if not instruction or not instruction.strip():
        raise HTTPException(409, 'AI 切片提示词未配置')
    try:
        configured = settings()
        base_url = configured.llm_base_url or configured.ai_base_url
        api_key = configured.llm_api_key or configured.ai_api_key
        if configured.llm_mode == 'mock' or not base_url or not api_key or not configured.llm_model:
            raise ProviderError('AI slicing unavailable', 'not_configured')
        data = _post(base_url.rstrip('/') + '/chat/completions', ai_headers(api_key), {
            'model': configured.llm_model, 'temperature': 0, 'max_tokens': 3500,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': numbered}]}, 45)
        raw = data['choices'][0]['message']['content']
        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.I)
        groups = json.loads(cleaned)['groups']
        if not isinstance(groups, list) or not groups:
            raise ValueError('empty groups')
        result, seen = [], []
        for group in groups:
            ids = group['paragraph_ids']
            if not isinstance(ids, list) or not ids or any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
                raise ValueError('invalid paragraph ids')
            seen.extend(ids)
            tags = group.get('tags') or {}
            if not isinstance(tags, dict):
                raise ValueError('invalid tags')
            result.append({'section': str(group.get('section') or parts[ids[0]-1][:80])[:80],
                           'content': '\n\n'.join(parts[i-1] for i in ids),
                           'tags': {str(k)[:32]: str(v)[:100] for k, v in tags.items()}})
        if seen != list(range(1, len(parts) + 1)):
            raise ValueError('paragraphs omitted, reordered or duplicated')
        return result
    except (ProviderError, KeyError, TypeError, ValueError, IndexError) as exc:
        raise HTTPException(502, 'AI 切片建议无效，请改用业务段落切片或手动编辑') from exc
