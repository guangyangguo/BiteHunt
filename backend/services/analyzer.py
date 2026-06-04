# -*- coding: utf-8 -*-
"""
探店地图 - AI视频内容分析服务
将B站视频的内容（字幕/语音转文字+标题+描述+标签）送入LLM，提取结构化店铺数据
"""

import json
import re
import requests
import sys
import os
import tempfile
import traceback

# 确保可以导入 database
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import add_store, update_video_status, add_analysis_log, delete_stores_by_video
from config import get
try:
    from services.bilibili import get_video_detail, fetch_video_subtitle, fetch_video_audio
except ImportError:
    get_video_detail = fetch_video_subtitle = fetch_video_audio = None
try:
    from services.transcriber import transcribe_audio
except ImportError:
    transcribe_audio = None


def _log(msg):
    """简单日志输出，带时间戳"""
    from datetime import datetime
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)


# ==================== 分析提示词 ====================

SYSTEM_PROMPT = """你是一个专业的美食探店数据分析助手。你的任务是从B站美食探店视频的标题、描述、标签和视频文本内容（字幕或语音转写）中，提取出该视频中探访过的美食店铺信息。

如果提供了【视频文本内容】，这是视频中博主实际说话的内容（通过字幕或语音识别获得），是分析店铺信息的最重要依据，请仔细阅读。

请仔细分析所有提供的内容，识别其中提到的店铺，并以JSON格式输出。

输出格式必须严格遵守以下JSON Schema：
```json
{
  "stores": [
    {
      "name": "店铺全名",
      "category": "品类（火锅/川菜/小吃/面馆/烧烤/甜品饮品/创意料理/轻食简餐/日料/西餐/其他）",
      "city": "所在城市",
      "district": "所在区/商圈",
      "address": "尽可能完整的地址",
      "avg_price": 人均价格（数字,单位元,无法判断填0）,
      "rating": 1-5星评分，根据博主评价语气判断（"太好吃了"填5，"不错"填4，"中规中矩"填3，"一般"填2，"翻车"填1，无法判断填0）,
      "recommend_dishes": ["推荐菜1", "推荐菜2"],
      "tags": ["标签1", "标签2"],
      "note": "探店分析总结（用一段话概括博主对该店的整体评价,含口味、环境、性价比,不超过120字",
      "confidence": 你对这条数据准确度的信心(0-1之间的数字)
    }
  ],
  "summary": "该视频探店内容的一句话概括"
}
```

注意事项：
1. 如果视频中没有提到具体的店铺名，stores返回空数组[]
2. 如果提到了多家店，每条分别列出
3. **地址提取非常重要**：仔细听博主说的话，他可能提到街道名、路口、地标建筑、商圈名称等。即使没有门牌号，也要把听到的所有位置信息拼成完整地址（如"春熙路太古里对面"、"建设路第五大道2楼"）。如果博主说"打车到XX"或"导航搜XX"，这个XX往往就是地址
4. 品类根据菜品特征判断（提到火锅/串串->火锅，提到川菜->川菜，提到面/粉->面馆）
5. tags提取视频中的关键词（如"排队王"、"苍蝇馆子"、"成都必吃"等）
6. 坐标（经纬度）不需要你填，后续会通过地址做地理编码
7. confidence：描述越详细、店名越明确，信心值越高
8. 视频文本内容可能包含一些语音识别的错误或无关闲聊，请提取其中与美食探店相关的核心信息
9. city字段填写城市名（如"成都"、"香港"），district填写区或商圈（如"锦江区"、"春熙路"）"""



def _get_llm_config():
    """获取LLM配置"""
    api_url = get('llm_api_url') or 'https://api.deepseek.com/v1/chat/completions'
    api_key = get('llm_api_key') or ''
    model = get('llm_model') or 'deepseek-chat'
    return api_url, api_key, model


def call_llm(messages, model=None, temperature=0.3):
    """调用 LLM API"""
    api_url, api_key, model_name = _get_llm_config()
    if model:
        model_name = model

    _log(f"LLM调用: url={api_url}, model={model_name}, key={'***' if api_key else 'MISSING'}")

    if not api_key:
        return {'error': '请先配置LLM API Key（编辑 backend/.env 文件中的 LLM_API_KEY）'}

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    payload = {
        'model': model_name,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': 4096,
    }

    try:
        _log(f"发送请求, user_msg长度={len(messages[-1]['content']) if messages else 0}字符")
        resp = requests.post(api_url, json=payload, headers=headers, timeout=120)
        _log(f"HTTP状态: {resp.status_code}")

        if resp.status_code != 200:
            err_msg = f'API调用失败: HTTP {resp.status_code} - {resp.text[:300]}'
            _log(f"ERROR: {err_msg}")
            return {'error': err_msg}

        data = resp.json()
        content = data['choices'][0]['message']['content']
        usage = data.get('usage', {})
        _log(f"LLM返回成功: content长度={len(content)}, tokens=prompt:{usage.get('prompt_tokens')}/completion:{usage.get('completion_tokens')}")

        return {
            'content': content,
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'model': data.get('model', model_name),
        }
    except requests.exceptions.Timeout:
        _log("ERROR: API超时")
        return {'error': 'API调用超时（120秒），请检查网络或API服务状态'}
    except requests.exceptions.ConnectionError as e:
        _log(f"ERROR: 连接失败 - {e}")
        return {'error': f'无法连接到LLM API: {str(e)[:200]}'}
    except Exception as e:
        _log(f"ERROR: 异常 - {traceback.format_exc()}")
        return {'error': f'LLM调用异常: {str(e)}'}


def parse_llm_response(content):
    """从LLM响应中解析JSON"""
    if not content:
        _log("parse_llm_response: 内容为空")
        return None

    # 尝试直接解析
    try:
        result = json.loads(content)
        _log(f"parse_llm_response: 直接解析成功, stores={len(result.get('stores', []))}")
        return result
    except json.JSONDecodeError as e:
        _log(f"parse_llm_response: 直接解析失败 - {e}")

    # 尝试提取 ```json ... ``` 代码块
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if json_match:
        try:
            result = json.loads(json_match.group(1))
            _log(f"parse_llm_response: 代码块解析成功, stores={len(result.get('stores', []))}")
            return result
        except json.JSONDecodeError as e:
            _log(f"parse_llm_response: 代码块解析失败 - {e}")

    # 尝试找到 { 到 } 的范围
    try:
        start = content.index('{')
        end = content.rindex('}') + 1
        result = json.loads(content[start:end])
        _log(f"parse_llm_response: 范围提取解析成功, stores={len(result.get('stores', []))}")
        return result
    except (ValueError, json.JSONDecodeError) as e:
        _log(f"parse_llm_response: 范围提取失败 - {e}")

    _log(f"parse_llm_response: 全部解析方式失败, 原始内容前200字符: {content[:200]}")
    return None


def geocode_address(address, city='成都', store_name=''):
    """
    对地址进行地理编码
    返回 (lat, lng, discovered_address) — discovered_address 是 POI 搜索发现的更准确地址
    """
    if not address or address == '未知':
        return 0, 0, ''

    full_addr = address
    if city and city not in address:
        full_addr = f'{city}{address}'

    amap_key = get('amap_api_key')

    # 策略1: POI搜索 — 用店铺名直接搜（最精准）
    if amap_key and store_name:
        lat, lng, poi_addr = _search_amap_poi(store_name, city, amap_key)
        if lat != 0:
            return lat, lng, poi_addr

    # 策略2: 城市 + 详细地址
    if amap_key:
        lat, lng = _geocode_amap(full_addr, amap_key)
        if lat != 0:
            _log(f"地理编码(高德-地址): {full_addr} -> ({lat},{lng})")
            return lat, lng, ''

    # 策略3: Nominatim
    lat, lng = _geocode_nominatim(full_addr)
    if lat != 0:
        _log(f"地理编码(Nominatim): {full_addr} -> ({lat},{lng})")
        return lat, lng, ''

    if amap_key and store_name:
        # 策略4: 全国范围搜店名
        lat, lng, poi_addr = _search_amap_poi(store_name, '', amap_key)
        if lat != 0:
            return lat, lng, poi_addr

    # 策略5: 只搜城市名
    if city and city != full_addr:
        if amap_key:
            lat, lng = _geocode_amap(city, amap_key)
            if lat != 0:
                _log(f"地理编码(高德-城市): {city} -> ({lat},{lng})")
                return lat, lng, ''
        lat, lng = _geocode_nominatim(city)
        if lat != 0:
            _log(f"地理编码(Nominatim-城市): {city} -> ({lat},{lng})")
            return lat, lng, ''

    _log(f"地理编码全部失败: address={address}, store={store_name}")
    return 0, 0, ''


def _geocode_amap(address, key):
    try:
        resp = requests.get(
            'https://restapi.amap.com/v3/geocode/geo',
            params={'key': key, 'address': address, 'output': 'JSON'},
            timeout=10,
        )
        data = resp.json()
        if data.get('status') == '1' and data.get('geocodes'):
            location = data['geocodes'][0]['location']
            lng, lat = location.split(',')
            return float(lat), float(lng)
    except Exception:
        pass
    return 0, 0


def _geocode_nominatim(address):
    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': address, 'format': 'json', 'limit': 1, 'accept-language': 'zh'},
            headers={'User-Agent': 'TandianMap/1.0'},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                return float(results[0]['lat']), float(results[0]['lon'])
    except Exception:
        pass
    return 0, 0


def _search_amap_poi(keyword, city, amap_key):
    """高德POI搜索 — 按店铺名搜索真实位置，返回 (lat, lng, address)"""
    try:
        resp = requests.get(
            'https://restapi.amap.com/v3/place/text',
            params={
                'key': amap_key,
                'keywords': keyword,
                'city': city,
                'output': 'JSON',
                'offset': 1,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get('status') == '1' and data.get('pois'):
            poi = data['pois'][0]
            location = poi['location']
            lng, lat = location.split(',')
            poi_addr = poi.get('address', '')
            poi_name = poi.get('name', '')
            _log(f"POI搜索命中: {keyword} -> {poi_name} ({poi_addr}) -> ({lat},{lng})")
            return float(lat), float(lng), poi_addr
    except Exception as e:
        _log(f"POI搜索异常: {e}")
    return 0, 0, ''


def _get_video_text_content(platform_video_id):
    """
    获取视频的文本内容（字幕或语音转写）
    优先级: B站字幕 > 音频下载+语音转文字
    返回: (text_content, source_info) 或 ('', '')
    """
    if not platform_video_id:
        _log("获取文本内容: platform_video_id为空, 跳过")
        return '', ''

    # 方案1: 尝试获取B站字幕
    _log(f"获取文本内容: 尝试B站字幕 bvid={platform_video_id}")
    if fetch_video_subtitle:
        try:
            subtitle = fetch_video_subtitle(platform_video_id)
            if subtitle and len(subtitle.strip()) > 50:
                _log(f"获取文本内容: 字幕成功, {len(subtitle)}字符")
                return subtitle, 'B站字幕'
            else:
                _log(f"获取文本内容: 字幕为空或太短 (长度={len(subtitle) if subtitle else 0})")
        except Exception as e:
            _log(f"获取文本内容: 字幕异常 - {e}")
    else:
        _log("获取文本内容: fetch_video_subtitle 不可用")

    # 方案2: 下载音频并语音转文字
    _log(f"获取文本内容: 尝试音频下载+转写 bvid={platform_video_id}")
    if not fetch_video_audio:
        _log("获取文本内容: fetch_video_audio 不可用")
        return '', ''
    if not transcribe_audio:
        _log("获取文本内容: transcribe_audio 不可用")
        return '', ''

    audio_path = None
    try:
        fd, audio_path = tempfile.mkstemp(suffix='.m4a', prefix='tandian_audio_')
        os.close(fd)
        _log(f"获取文本内容: 临时音频文件={audio_path}")

        success, size = fetch_video_audio(platform_video_id, audio_path)
        if not success or size == 0:
            _log(f"获取文本内容: 音频下载失败 success={success} size={size}")
            return '', ''
        _log(f"获取文本内容: 音频下载成功 {size} bytes")

        transcript = transcribe_audio(audio_path)
        if transcript and len(transcript.strip()) > 50:
            _log(f"获取文本内容: 转写成功 {len(transcript)}字符")
            return transcript, '语音转写'
        else:
            _log(f"获取文本内容: 转写结果太短或空 (长度={len(transcript) if transcript else 0})")
            return '', ''

    except Exception as e:
        _log(f"获取文本内容: 异常 - {traceback.format_exc()}")
        return '', ''
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                _log(f"获取文本内容: 已清理临时文件 {audio_path}")
            except Exception:
                pass


def analyze_video(video_id, data_provider=None):
    """
    分析单个视频，提取店铺信息
    """
    _log(f"{'='*50}")
    _log(f"开始分析视频 video_id={video_id}")
    _log(f"{'='*50}")

    # Step 1: 获取视频信息
    if data_provider:
        video = data_provider
        _log(f"Step1: 使用 data_provider, title={video.get('title', '?')[:50]}")
    else:
        from database import get_video
        video = get_video(video_id)
        _log(f"Step1: 数据库查询 video_id={video_id}, 结果={'找到' if video else '不存在'}")

    if not video:
        _log("Step1: 视频不存在, 返回失败")
        return {'success': False, 'error': '视频不存在'}

    _log(f"Step1: 视频信息 - title={video.get('title','')[:60]}, bvid={video.get('platform_video_id','')}, blogger_id={video.get('blogger_id','')}")

    # Step 2: 构建分析内容
    content_parts = [f"【视频标题】{video['title']}"]

    desc = video.get('description', '')
    if desc:
        content_parts.append(f"【视频描述】{desc}")
        _log(f"Step2: 描述长度={len(desc)}")
    else:
        _log("Step2: 无描述")

    tags = video.get('tags', '')
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    if tags:
        content_parts.append(f"【视频标签】{', '.join(tags)}")
        _log(f"Step2: 标签={tags}")

    # Step 3: 获取视频文本内容
    bvid = video.get('platform_video_id', '')
    _log(f"Step3: 开始获取视频文本内容 bvid={bvid}")
    text_content, text_source = _get_video_text_content(bvid)
    if text_content:
        content_parts.append(f"【视频文本内容（{text_source}）】\n{text_content}")
        _log(f"Step3: 成功获取文本内容, 来源={text_source}, 长度={len(text_content)}")
    else:
        _log("Step3: 未能获取文本内容, 仅使用元数据分析")

    user_content = '\n\n'.join(content_parts)
    _log(f"Step4: 最终分析内容总长度={len(user_content)}字符")

    # Step 5: 调用 LLM
    _log("Step5: 调用LLM分析...")
    result = call_llm([
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_content},
    ])

    if 'error' in result:
        _log(f"Step5: LLM返回错误 - {result['error']}")
        if not data_provider:
            add_analysis_log(
                video_id=video_id, model_name='', raw_response='',
                extracted_data={}, store_ids=[], success=False,
                error_message=result['error'],
            )
        return {'success': False, 'error': result['error']}

    _log(f"Step5: LLM返回成功, 响应长度={len(result['content'])}")

    # Step 6: 解析JSON
    _log("Step6: 解析LLM响应...")
    parsed = parse_llm_response(result['content'])
    if not parsed:
        _log("Step6: JSON解析失败")
        if not data_provider:
            add_analysis_log(
                video_id=video_id,
                model_name=result.get('model', ''),
                raw_response=result['content'],
                extracted_data={}, store_ids=[], success=False,
                error_message='无法解析LLM返回的JSON',
                prompt_tokens=result.get('prompt_tokens', 0),
                completion_tokens=result.get('completion_tokens', 0),
            )
        return {
            'success': False,
            'error': '无法解析LLM返回的JSON',
            'raw_response': result['content'],
        }

    # Step 7: 去重 — 先清理该视频之前提取的店铺
    if not data_provider:
        delete_stores_by_video(video_id)
        _log("Step7: 已清理该视频之前提取的店铺")

    # Step 8: 提取店铺
    stores_data = parsed.get('stores', [])
    summary = parsed.get('summary', '')
    _log(f"Step8: 提取到 {len(stores_data)} 家店铺, summary={summary[:50] if summary else '无'}")

    store_ids = []
    for i, store in enumerate(stores_data):
        store_name = store.get('name', '')
        if not store_name:
            _log(f"Step8: 店铺[{i}] 无名称, 跳过")
            continue

        _log(f"Step8: 处理店铺[{i}]: {store_name}")

        city = store.get('city', '成都')
        district = store.get('district', '')
        address = store.get('address', '')

        # 构建完整地址：优先用 address，其次 city+district，最后只用 city
        if address:
            full_address = f"{city}{district}{address}".strip()
        elif district:
            full_address = f"{city}{district}"
        else:
            full_address = city

        # 地理编码（传入店铺名提升精度）
        lat, lng, poi_addr = 0, 0, ''
        _log(f"Step8: 尝试地理编码: address={full_address}, store={store_name}")
        lat, lng, poi_addr = geocode_address(full_address, city, store_name)
        _log(f"Step8: 地理编码结果: ({lat}, {lng})")

        # 优先用 POI 搜索到的地址
        final_address = poi_addr if poi_addr else full_address

        store_data = {
            'name': store_name,
            'category': store.get('category', '其他'),
            'lat': lat, 'lng': lng,
            'address': final_address,
            'avg_price': store.get('avg_price', 0),
            'rating': store.get('rating', 0),
            'recommend_dishes': store.get('recommend_dishes', []),
            'tags': store.get('tags', []),
            'note': store.get('note', ''),
            'source_video_id': video_id if not data_provider else video.get('id'),
            'source_blogger_id': video.get('blogger_id') if not data_provider else video.get('blogger_id'),
            'confidence': store.get('confidence', 0.5),
        }

        if not data_provider:
            sid = add_store(store_data)
            store_ids.append(sid)
            _log(f"Step8: 店铺已保存 store_id={sid}")
        else:
            store_ids.append(store_data)

    # Step 9: 记录日志和更新状态
    if not data_provider:
        _log("Step9: 记录分析日志...")
        add_analysis_log(
            video_id=video_id,
            model_name=result.get('model', ''),
            raw_response=result['content'],
            extracted_data=parsed,
            store_ids=store_ids,
            success=True,
            error_message='',
            prompt_tokens=result.get('prompt_tokens', 0),
            completion_tokens=result.get('completion_tokens', 0),
        )

        new_status = 'analyzed' if store_ids else 'no_store'
        update_video_status(video_id, new_status)
        _log(f"Step8: 视频状态更新为 {new_status}")

    _log(f"分析完成: success=True, stores={len(store_ids)}, summary={summary[:30] if summary else '无'}")
    _log(f"{'='*50}")

    return {
        'success': True,
        'stores': stores_data,
        'summary': summary,
        'store_ids': store_ids,
    }


def batch_analyze(video_ids):
    """批量分析视频"""
    results = []
    for vid in video_ids:
        try:
            result = analyze_video(vid)
            results.append({'video_id': vid, **result})
        except Exception as e:
            _log(f"batch_analyze: video_id={vid} 异常 - {traceback.format_exc()}")
            results.append({'video_id': vid, 'success': False, 'error': str(e)})
    return results


def test_llm_connection():
    """测试LLM连接"""
    api_key = get('llm_api_key')
    if not api_key:
        return False, '未配置API Key（编辑 backend/.env 中的 LLM_API_KEY）'

    result = call_llm([
        {'role': 'user', 'content': '请回复"连接成功"两个字'},
    ], temperature=0)
    if 'error' in result:
        return False, result['error']
    return True, result.get('content', '').strip()
