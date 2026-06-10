# -*- coding: utf-8 -*-
"""
AI 向导推荐服务。

第一版保持可控：用规则解析用户意图，用真实店铺数据排序，再生成解释。
这样即使没有 LLM API Key，也能给出稳定、不会编造的推荐。
"""

import json
import math
import re


CATEGORY_KEYWORDS = {
    '火锅': ['火锅', '串串', '冒菜'],
    '川菜': ['川菜', '江湖菜', '家常菜', '辣'],
    '小吃': ['小吃', '夜市', '街边', '早餐', '宵夜'],
    '面馆': ['面', '粉', '米线', '抄手'],
    '烧烤': ['烧烤', '烤肉', '烤串'],
    '甜品饮品': ['甜品', '奶茶', '咖啡', '饮品', '蛋糕'],
    '日料': ['日料', '寿司', '刺身', '拉面'],
    '西餐': ['西餐', '牛排', '披萨', '汉堡']
}

CITY_KEYWORDS = [
    '成都', '武汉', '重庆', '上海', '北京', '广州', '深圳', '杭州', '南京', '长沙',
    '西安', '苏州', '香港', '澳门', '天津', '厦门', '青岛'
]

INTENT_KEYWORDS = {
    'nearby': ['附近', '周边', '离我近', '近一点', '当前位置'],
    'safe': ['不踩雷', '靠谱', '稳', '别翻车', '少踩雷'],
    'value': ['性价比', '便宜', '划算', '预算', '人均', '以内'],
    'tourist': ['外地游客', '游客', '第一次来', '本地特色', '必吃'],
    'strong': ['强推', '强烈推荐', '最好吃', '高分'],
    'route': ['路线', '半天', '一天', '安排', '逛']
}


def recommend_for_query(stores, query, user_location=None, limit=5):
    intent = parse_intent(query)
    return recommend_for_intent(stores, intent, user_location=user_location, limit=limit)


def recommend_for_intent(stores, intent, user_location=None, limit=5):
    intent = normalize_intent(intent)
    prepared = [normalize_store(store) for store in stores]
    scored = []
    for store in prepared:
        score, reasons = score_store(store, intent, user_location=user_location)
        if score <= 0:
            continue
        scored.append((score, store, reasons))

    scored.sort(key=lambda item: item[0], reverse=True)
    recommendations = [
        format_recommendation(store, score, reasons)
        for score, store, reasons in scored[:limit]
    ]

    return {
        'intent': intent,
        'summary': build_summary(intent, recommendations),
        'follow_up': build_follow_up(intent, recommendations),
        'recommendations': recommendations,
    }


def normalize_intent(intent):
    intent = dict(intent or {})
    flags = intent.get('flags') or {}
    preferences = intent.get('preferences') or []
    if isinstance(preferences, str):
        preferences = [preferences]
    flag_text = ' '.join(str(item) for item in preferences)
    merged_flags = {
        key: bool(flags.get(key))
        for key in INTENT_KEYWORDS
    }
    for key, keywords in INTENT_KEYWORDS.items():
        if any(keyword in flag_text for keyword in keywords):
            merged_flags[key] = True
    if intent.get('nearby'):
        merged_flags['nearby'] = True

    try:
        budget = int(float(intent.get('budget') or 0))
    except Exception:
        budget = 0

    return {
        'raw': str(intent.get('raw') or intent.get('query') or ''),
        'category': str(intent.get('category') or ''),
        'city': str(intent.get('city') or ''),
        'budget': budget,
        'blogger': str(intent.get('blogger') or ''),
        'flags': merged_flags,
        'keywords': intent.get('keywords') if isinstance(intent.get('keywords'), list) else [],
        'preferences': preferences,
    }


def parse_intent(query):
    text = str(query or '').strip()
    lowered = text.lower()
    category = ''
    for name, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            category = name
            break

    city = ''
    for item in CITY_KEYWORDS:
        if item in text:
            city = item
            break

    budget = parse_budget(text)
    blogger = parse_blogger(text)
    flags = {
        key: any(keyword in text for keyword in keywords)
        for key, keywords in INTENT_KEYWORDS.items()
    }
    if 'near me' in lowered or 'nearby' in lowered:
        flags['nearby'] = True

    keywords = [
        word for word in re.split(r'[\s,，。.!！?？、]+', text)
        if len(word) >= 2 and word not in CATEGORY_KEYWORDS and word not in CITY_KEYWORDS
    ]

    return {
        'raw': text,
        'category': category,
        'city': city,
        'budget': budget,
        'blogger': blogger,
        'flags': flags,
        'keywords': keywords[:8],
    }


def parse_budget(text):
    patterns = [
        r'人均\s*(\d{2,4})',
        r'(\d{2,4})\s*元?\s*以内',
        r'预算\s*(\d{2,4})',
        r'(\d{2,4})\s*左右',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return 0


def parse_blogger(text):
    match = re.search(r'(?:博主|up主|UP主)\s*([^\s,，。.!！?？、]{2,12})', text)
    return match.group(1) if match else ''


def score_store(store, intent, user_location=None):
    score = 0.0
    reasons = []

    rating = float(store.get('rating') or 0)
    confidence = float(store.get('confidence') or 0)
    avg_price = int(store.get('avg_price') or 0)

    if rating:
        score += rating * 14
        if rating >= 4.5:
            reasons.append('AI 评分很高')
        elif rating >= 4:
            reasons.append('评分稳定')
    if confidence:
        score += min(confidence, 1) * 10

    if intent['category']:
        if store.get('category') == intent['category']:
            score += 28
            reasons.append(f"匹配{intent['category']}")
        else:
            return 0, []

    if intent['city']:
        city_text = get_store_text(store)
        if intent['city'] in city_text:
            score += 22
            reasons.append(f"在{intent['city']}")
        else:
            return 0, []

    if intent['blogger']:
        blogger_name = store.get('blogger_name') or ''
        if intent['blogger'] in blogger_name:
            score += 22
            reasons.append(f"{blogger_name}探访")
        else:
            return 0, []

    if intent['budget']:
        if avg_price:
            gap = abs(avg_price - intent['budget'])
            if avg_price <= intent['budget']:
                score += 18
                reasons.append(f"人均约{avg_price}元，符合预算")
            elif gap <= max(20, intent['budget'] * 0.25):
                score += 8
                reasons.append(f"人均约{avg_price}元，接近预算")
            else:
                score -= 18
        else:
            score += 2

    text = get_store_text(store)
    keyword_hits = [kw for kw in intent['keywords'] if kw and kw in text]
    if keyword_hits:
        score += min(len(keyword_hits), 3) * 6
        reasons.append('匹配关键词：' + '、'.join(keyword_hits[:3]))

    flags = intent['flags']
    if flags.get('safe') and rating >= 4:
        score += 12
        reasons.append('更适合不踩雷')
    if flags.get('strong') and rating >= 4.5:
        score += 14
        reasons.append('属于高推荐候选')
    if flags.get('value') and avg_price and avg_price <= (intent['budget'] or 100):
        score += 10
        reasons.append('性价比更合适')
    if flags.get('tourist') and any(word in text for word in ['必吃', '特色', '老店', '本地']):
        score += 9
        reasons.append('有本地特色标签')

    distance_km = None
    if user_location and store.get('lat') and store.get('lng'):
        distance_km = calc_distance_km(
            user_location.get('lat'),
            user_location.get('lng'),
            store.get('lat'),
            store.get('lng'),
        )
        if distance_km is not None:
            if flags.get('nearby'):
                score += max(0, 24 - distance_km * 3)
                if distance_km <= 3:
                    reasons.append(f"距离约{distance_km:.1f}km")
            else:
                score += max(0, 8 - distance_km)

    if not reasons:
        reasons.append('综合评分和视频分析结果更靠前')
    return score, reasons[:4]


def normalize_store(store):
    item = dict(store)
    for field in ['recommend_dishes', 'tags']:
        value = item.get(field)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                item[field] = parsed if isinstance(parsed, list) else []
            except Exception:
                item[field] = []
        elif not isinstance(value, list):
            item[field] = []
    for field in ['lat', 'lng', 'rating', 'confidence']:
        try:
            item[field] = float(item.get(field) or 0)
        except Exception:
            item[field] = 0
    try:
        item['avg_price'] = int(float(item.get('avg_price') or 0))
    except Exception:
        item['avg_price'] = 0
    return item


def format_recommendation(store, score, reasons):
    return {
        'id': store.get('id'),
        'name': store.get('name', ''),
        'category': store.get('category', ''),
        'address': store.get('address', ''),
        'avg_price': store.get('avg_price') or 0,
        'rating': store.get('rating') or 0,
        'blogger_name': store.get('blogger_name', ''),
        'source_video_title': store.get('source_video_title', ''),
        'source_video_url': store.get('source_video_url', ''),
        'recommend_dishes': store.get('recommend_dishes', [])[:4],
        'tags': store.get('tags', [])[:5],
        'note': store.get('note', ''),
        'score': round(score, 1),
        'reason': '；'.join(reasons),
        'lat': store.get('lat') or 0,
        'lng': store.get('lng') or 0,
    }


def build_summary(intent, recommendations):
    if not recommendations:
        return '我没在当前店铺库里找到足够匹配的结果，可以换个菜系、预算或城市再试。'
    parts = []
    if intent['city']:
        parts.append(intent['city'])
    if intent['category']:
        parts.append(intent['category'])
    if intent['budget']:
        parts.append(f"人均{intent['budget']}元左右")
    prefix = '、'.join(parts) if parts else '你的需求'
    return f"我按{prefix}筛选，并优先考虑评分、预算匹配、博主来源和视频分析置信度，给你挑了 {len(recommendations)} 家。"


def build_follow_up(intent, recommendations):
    if recommendations:
        return ''
    if not intent['city']:
        return '可以补充城市或直接说“附近”，我会更容易缩小范围。'
    if not intent['category']:
        return '可以补充想吃的品类，比如火锅、小吃、面馆或甜品。'
    return '可以放宽预算或换一个相近品类试试。'


def get_store_text(store):
    values = [
        store.get('name'),
        store.get('category'),
        store.get('address'),
        store.get('blogger_name'),
        store.get('source_video_title'),
        store.get('note'),
        *(store.get('recommend_dishes') or []),
        *(store.get('tags') or []),
    ]
    return ' '.join(str(value) for value in values if value)


def calc_distance_km(lat1, lng1, lat2, lng2):
    try:
        lat1, lng1, lat2, lng2 = map(float, [lat1, lng1, lat2, lng2])
    except Exception:
        return None
    if not lat1 or not lng1 or not lat2 or not lng2:
        return None

    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
