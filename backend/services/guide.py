# -*- coding: utf-8 -*-
"""
对话式 AI 向导。

模型负责理解多轮上下文和生成回复；店铺检索仍由后端完成，避免编造不存在的店。
"""

import json
import re
import requests

from config import get
from services.recommender import parse_intent, recommend_for_intent, recommend_for_query


GUIDE_SYSTEM_PROMPT = """你是一个探店 AI 向导，帮助用户基于真实店铺库找餐厅。

你必须遵守：
1. 不要编造店铺、地址、价格、博主或视频来源。
2. 如果用户需求不清楚，可以追问 1 个最关键问题。
3. 如果需求已经足够明确，输出结构化检索条件。
4. 输出必须是 JSON，不要输出 Markdown。

JSON Schema:
{
  "need_clarification": false,
  "clarifying_question": "",
  "intent": {
    "city": "",
    "category": "",
    "budget": 0,
    "blogger": "",
    "nearby": false,
    "preferences": [],
    "keywords": []
  }
}

category 只能从以下值中选择：火锅、川菜、小吃、面馆、烧烤、甜品饮品、日料、西餐、其他。无法判断填空字符串。
budget 是人均预算，数字，无法判断填 0。
nearby 表示用户明确要求附近、周边、离我近、当前位置。
"""


ANSWER_SYSTEM_PROMPT = """你是一个探店 AI 向导，正在根据后端真实检索结果回复用户。

你必须遵守：
1. 只能基于候选店铺回答，不允许编造候选之外的店。
2. 可以解释为什么推荐，但理由必须来自候选店铺字段。
3. 如果候选为空，简短说明没有找到，并建议用户放宽条件或补充城市/菜系/预算。
4. 回复自然、简洁，适合微信小程序聊天界面。
"""


def guide_chat(stores, messages, user_location=None, limit=5, llm_func=None):
    safe_messages = normalize_messages(messages)
    latest_text = get_latest_user_text(safe_messages)
    if not latest_text:
        return {
            'reply': '你可以告诉我城市、预算、菜系，或者直接说“附近有什么不踩雷的店”。',
            'follow_up': '',
            'recommendations': [],
            'intent': {},
            'mode': 'empty',
        }

    llm_func = llm_func or call_guide_llm
    parsed = parse_dialog_intent(safe_messages, llm_func=llm_func)
    if parsed.get('need_clarification') and parsed.get('clarifying_question'):
        return {
            'reply': parsed['clarifying_question'],
            'follow_up': '',
            'recommendations': [],
            'intent': parsed.get('intent') or {},
            'mode': 'clarify',
        }

    intent = parsed.get('intent') or parse_intent(latest_text)
    if not intent.get('raw'):
        intent['raw'] = latest_text
    result = recommend_for_intent(stores, intent, user_location=user_location, limit=limit)
    if not result['recommendations'] and parsed.get('mode') == 'fallback':
        result = recommend_for_query(stores, latest_text, user_location=user_location, limit=limit)

    reply = build_model_reply(
        safe_messages,
        result['intent'],
        result['recommendations'],
        result['summary'],
        result.get('follow_up', ''),
        llm_func=llm_func,
    )
    return {
        'reply': reply,
        'follow_up': result.get('follow_up', ''),
        'recommendations': result['recommendations'],
        'intent': result['intent'],
        'mode': parsed.get('mode', 'llm'),
    }


def guide_chat_events(stores, messages, user_location=None, limit=5):
    """生成对话事件：meta/delta/done/error。用于小程序 chunk 流式输出。"""
    safe_messages = normalize_messages(messages)
    latest_text = get_latest_user_text(safe_messages)
    if not latest_text:
        text = '你可以告诉我城市、预算、菜系，或者直接说“附近有什么不踩雷的店”。'
        yield {'type': 'delta', 'content': text}
        yield {'type': 'done'}
        return

    parsed = parse_dialog_intent(safe_messages)
    if parsed.get('need_clarification') and parsed.get('clarifying_question'):
        yield {'type': 'meta', 'recommendations': [], 'intent': parsed.get('intent') or {}, 'follow_up': ''}
        for chunk in chunk_text(parsed['clarifying_question']):
            yield {'type': 'delta', 'content': chunk}
        yield {'type': 'done'}
        return

    intent = parsed.get('intent') or parse_intent(latest_text)
    if not intent.get('raw'):
        intent['raw'] = latest_text
    result = recommend_for_intent(stores, intent, user_location=user_location, limit=limit)
    if not result['recommendations'] and parsed.get('mode') == 'fallback':
        result = recommend_for_query(stores, latest_text, user_location=user_location, limit=limit)

    yield {
        'type': 'meta',
        'recommendations': result['recommendations'],
        'intent': result['intent'],
        'follow_up': result.get('follow_up', ''),
    }

    if not result['recommendations']:
        for chunk in chunk_text(result['summary']):
            yield {'type': 'delta', 'content': chunk}
        yield {'type': 'done'}
        return

    prompt_messages = build_answer_prompt(
        safe_messages,
        result['intent'],
        result['recommendations'],
        result['summary'],
        result.get('follow_up', ''),
    )
    streamed = False
    for chunk in call_guide_llm_stream(prompt_messages, temperature=0.4, max_tokens=1200):
        streamed = True
        yield {'type': 'delta', 'content': chunk}

    if not streamed:
        for chunk in chunk_text(result['summary']):
            yield {'type': 'delta', 'content': chunk}
    yield {'type': 'done'}


def parse_dialog_intent(messages, llm_func=None):
    llm_func = llm_func or call_guide_llm
    prompt_messages = [
        {'role': 'system', 'content': GUIDE_SYSTEM_PROMPT},
        *messages[-8:],
    ]
    result = llm_func(prompt_messages, temperature=0.1, max_tokens=1200)
    content = result.get('content') if isinstance(result, dict) else ''
    parsed = extract_json_object(content)
    if not parsed:
        latest = get_latest_user_text(messages)
        return {'need_clarification': False, 'intent': parse_intent(latest), 'mode': 'fallback'}

    intent = parsed.get('intent') if isinstance(parsed.get('intent'), dict) else {}
    return {
        'need_clarification': bool(parsed.get('need_clarification')),
        'clarifying_question': str(parsed.get('clarifying_question') or ''),
        'intent': intent,
        'mode': 'llm',
    }


def build_model_reply(messages, intent, recommendations, fallback_summary, follow_up, llm_func=None):
    if not recommendations:
        return fallback_summary

    llm_func = llm_func or call_guide_llm
    prompt_messages = build_answer_prompt(messages, intent, recommendations, fallback_summary, follow_up)
    result = llm_func(prompt_messages, temperature=0.4, max_tokens=1200)
    content = (result.get('content') if isinstance(result, dict) else '') or ''
    content = strip_markdown_fence(content).strip()
    return content or fallback_summary


def build_answer_prompt(messages, intent, recommendations, fallback_summary, follow_up):
    compact_candidates = [
        {
            'name': item.get('name'),
            'category': item.get('category'),
            'avg_price': item.get('avg_price'),
            'rating': item.get('rating'),
            'blogger_name': item.get('blogger_name'),
            'reason': item.get('reason'),
            'recommend_dishes': item.get('recommend_dishes', []),
            'tags': item.get('tags', []),
            'note': item.get('note', ''),
        }
        for item in recommendations
    ]
    user_context = {
        'intent': intent,
        'candidates': compact_candidates,
        'fallback_summary': fallback_summary,
        'follow_up': follow_up,
    }
    return [
        {'role': 'system', 'content': ANSWER_SYSTEM_PROMPT},
        *messages[-6:],
        {'role': 'user', 'content': '请基于下面候选店铺给出对话式推荐回复：' + json.dumps(user_context, ensure_ascii=False)}
    ]


def call_guide_llm(messages, temperature=0.2, max_tokens=1600):
    api_url, api_key, model = get_guide_llm_config()
    if not api_key:
        return {'error': 'GUIDE_LLM_API_KEY/LLM_API_KEY 未配置'}

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=45)
        if resp.status_code != 200:
            return {'error': f'AI向导模型调用失败: HTTP {resp.status_code} - {resp.text[:200]}'}
        data = resp.json()
        return {
            'content': data['choices'][0]['message']['content'],
            'model': data.get('model', model),
            'usage': data.get('usage', {}),
        }
    except Exception as e:
        return {'error': f'AI向导模型调用异常: {str(e)[:200]}'}


def call_guide_llm_stream(messages, temperature=0.2, max_tokens=1600):
    api_url, api_key, model = get_guide_llm_config()
    if not api_key:
        return

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': True,
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    try:
        with requests.post(api_url, json=payload, headers=headers, timeout=60, stream=True) as resp:
            if resp.status_code != 200:
                return
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith('data:'):
                    line = line[5:].strip()
                if line == '[DONE]':
                    break
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                choice = (data.get('choices') or [{}])[0]
                delta = choice.get('delta') or {}
                content = delta.get('content') or choice.get('message', {}).get('content') or ''
                if content:
                    yield content
    except Exception:
        return


def get_guide_llm_config():
    api_url = get('guide_llm_api_url') or get('llm_api_url') or 'https://api.deepseek.com/v1/chat/completions'
    api_key = get('guide_llm_api_key') or get('llm_api_key') or ''
    model = get('guide_llm_model') or get('llm_model') or 'deepseek-chat'
    return api_url, api_key, model


def normalize_messages(messages):
    safe = []
    if not isinstance(messages, list):
        return safe
    for item in messages[-12:]:
        role = item.get('role') if isinstance(item, dict) else ''
        content = item.get('content') if isinstance(item, dict) else ''
        if role not in ('user', 'assistant') or not content:
            continue
        safe.append({'role': role, 'content': str(content)[:1000]})
    return safe


def get_latest_user_text(messages):
    for item in reversed(messages or []):
        if item.get('role') == 'user':
            return str(item.get('content') or '').strip()
    return ''


def extract_json_object(content):
    text = strip_markdown_fence(content or '').strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def strip_markdown_fence(text):
    text = str(text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text


def chunk_text(text, size=6):
    text = str(text or '')
    for index in range(0, len(text), size):
        yield text[index:index + size]
