"""
探店地图 - Flask 后端服务
提供 REST API + 管理后台
"""

import json
import os
import sys
import io
import re
import time
import uuid

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    # 确保 ffmpeg 在 PATH 中（Whisper 语音转文字需要）
    ffmpeg_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ffmpeg')
    if os.path.isdir(ffmpeg_path) and ffmpeg_path not in os.environ.get('PATH', ''):
        os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ.get('PATH', '')

from flask import Flask, request, jsonify, send_from_directory, make_response, Response

import queue
import threading

# 确保可以导入 backend 内部模块
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)

from database import (
    init_db, get_db,
    add_blogger, get_all_bloggers, get_blogger, delete_blogger,
    get_videos, get_video, update_video_status,
    count_videos,
    add_videos_batch, delete_video,
    delete_videos_batch,
    get_all_stores, get_store, delete_store, delete_stores_batch,
    get_analysis_logs, get_analysis_steps,
    get_stats,
)
from services.bilibili import (
    get_user_info, search_user, get_video_detail, fetch_video_by_url,
    fetch_user_recent_videos, resolve_user_input, BilibiliRiskControlError
)
from services.analyzer import analyze_video, batch_analyze
from services.guide import guide_chat, guide_chat_events
from services.recommender import recommend_for_query

app = Flask(__name__, static_folder=os.path.join(project_dir, 'frontend'))
app.config['JSON_AS_ASCII'] = False
# 开发环境禁用静态文件缓存
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

FRONTEND_DIR = os.path.join(project_dir, 'frontend')

analysis_jobs = {}
analysis_jobs_lock = threading.Lock()


# ==================== 静态文件 ====================

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIR, path)
    # SPA fallback
    return send_from_directory(FRONTEND_DIR, 'index.html')


# ==================== CORS ====================

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response


# ==================== API: 统计 ====================

@app.route('/api/stats')
def api_stats():
    try:
        stats = get_stats()
        stores = get_all_stores()
        categories = set(s['category'] for s in stores if s['category'])
        stats['categories_list'] = list(categories)
        return jsonify({'code': 0, 'data': stats})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== API: 用户占位 ====================

def _placeholder_user_profile():
    return {
        'is_logged_in': False,
        'nickname': '未登录用户',
        'avatar': '',
        'stats': {
            'favorites': 0,
            'visited': 0,
            'guides': 0,
        },
        'features': {
            'favorites': False,
            'history': False,
            'preferences': False,
        },
    }


@app.route('/api/user/profile')
def api_user_profile():
    return jsonify({'code': 0, 'data': _placeholder_user_profile()})


@app.route('/api/user/login', methods=['POST'])
def api_user_login():
    profile = _placeholder_user_profile()
    profile['login_provider'] = (request.get_json(silent=True) or {}).get('provider', 'placeholder')
    return jsonify({'code': 0, 'data': profile, 'message': '用户登录接口已预留'})


@app.route('/api/user/logout', methods=['POST'])
def api_user_logout():
    return jsonify({'code': 0, 'data': _placeholder_user_profile(), 'message': '已退出占位登录态'})


# ==================== API: 店铺 ====================

@app.route('/api/stores')
def api_stores():
    try:
        category = request.args.get('category')
        stores = get_all_stores(category=category)

        # 处理 JSON 字段
        for s in stores:
            for field in ['recommend_dishes', 'tags']:
                if isinstance(s.get(field), str):
                    try:
                        s[field] = json.loads(s[field])
                    except (json.JSONDecodeError, TypeError):
                        s[field] = []

        return jsonify({'code': 0, 'data': stores})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/stores/<int:store_id>')
def api_store_detail(store_id):
    try:
        store = get_store(store_id)
        if not store:
            return jsonify({'code': -1, 'error': '店铺不存在'}), 404

        for field in ['recommend_dishes', 'tags']:
            if isinstance(store.get(field), str):
                try:
                    store[field] = json.loads(store[field])
                except (json.JSONDecodeError, TypeError):
                    store[field] = []

        return jsonify({'code': 0, 'data': store})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/stores/<int:store_id>', methods=['DELETE'])
def api_delete_store(store_id):
    try:
        result = delete_store(store_id)
        message = '已删除'
        if result.get('source_video_id') and result.get('active_store_count') == 0:
            message = '店铺已删除；来源视频已标记为未识别到店铺，可重新分析'
        return jsonify({'code': 0, 'data': result, 'message': message})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/stores/batch-delete', methods=['POST'])
def api_delete_stores_batch():
    try:
        data = request.get_json() or {}
        store_ids = data.get('store_ids') or []
        if not isinstance(store_ids, list) or not store_ids:
            return jsonify({'code': -1, 'error': '请选择要删除的店铺'}), 400
        result = delete_stores_batch(store_ids)
        return jsonify({
            'code': 0,
            'data': result,
            'message': f"已删除 {result.get('deleted', 0)} 家店铺",
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== API: AI 向导 ====================

@app.route('/api/guide/recommend', methods=['POST'])
def api_guide_recommend():
    try:
        data = request.get_json() or {}
        query = str(data.get('query', '')).strip()
        if not query:
            return jsonify({'code': -1, 'error': '请输入你的探店需求'}), 400

        user_location = data.get('location') or None
        stores = get_all_stores()
        result = recommend_for_query(stores, query, user_location=user_location, limit=5)
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/guide/chat', methods=['POST'])
def api_guide_chat():
    try:
        data = request.get_json() or {}
        messages = data.get('messages') or []
        if not isinstance(messages, list):
            return jsonify({'code': -1, 'error': 'messages 必须是数组'}), 400

        user_location = data.get('location') or None
        stores = get_all_stores()
        result = guide_chat(stores, messages, user_location=user_location, limit=5)
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/guide/chat/stream', methods=['POST'])
def api_guide_chat_stream():
    try:
        data = request.get_json() or {}
        messages = data.get('messages') or []
        if not isinstance(messages, list):
            return jsonify({'code': -1, 'error': 'messages 必须是数组'}), 400

        user_location = data.get('location') or None
        stores = get_all_stores()

        def generate():
            try:
                for event in guide_chat_events(stores, messages, user_location=user_location, limit=5):
                    yield json.dumps(event, ensure_ascii=False) + '\n'
            except GeneratorExit:
                return
            except Exception as e:
                yield json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False) + '\n'

        return Response(generate(), mimetype='application/x-ndjson')
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/stores/<int:store_id>', methods=['PUT'])
def api_update_store(store_id):
    """更新店铺信息（手动修改坐标、地址等）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'error': '请求数据为空'}), 400

        conn = get_db()
        updates = []
        params = []

        allowed_fields = [
            'name', 'category', 'lat', 'lng', 'address',
            'avg_price', 'rating', 'recommend_dishes', 'tags', 'note', 'confidence'
        ]
        for field in allowed_fields:
            if field in data:
                updates.append(f'{field}=?')
                value = data[field]
                if field in ['recommend_dishes', 'tags'] and isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                params.append(value)

        if not updates:
            return jsonify({'code': -1, 'error': '没有要更新的字段'}), 400

        params.append(store_id)
        conn.execute(
            f"UPDATE stores SET {', '.join(updates)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            params
        )
        conn.commit()
        conn.close()

        return jsonify({'code': 0, 'message': '店铺信息已更新'})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/stores/<int:store_id>/regeocode', methods=['POST'])
def api_regeocode_store(store_id):
    """重新对店铺地址进行地理编码"""
    try:
        from services.analyzer import geocode_address
        store = get_store(store_id)
        if not store:
            return jsonify({'code': -1, 'error': '店铺不存在'}), 404

        if not store.get('address'):
            return jsonify({'code': -1, 'error': '店铺没有地址信息'}), 400

        city = _infer_store_city(store)
        lat, lng, discovered_address = geocode_address(
            store['address'],
            city=city if city != '未分组' else '',
            store_name=store.get('name', ''),
        )
        if lat == 0 and lng == 0:
            return jsonify({'code': -1, 'error': '地理编码失败，请检查地址或配置高德API Key'}), 400

        conn = get_db()
        if discovered_address:
            conn.execute(
                "UPDATE stores SET lat=?, lng=?, address=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (lat, lng, discovered_address, store_id)
            )
        else:
            conn.execute(
                "UPDATE stores SET lat=?, lng=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (lat, lng, store_id)
            )
        conn.commit()
        conn.close()

        return jsonify({
            'code': 0,
            'data': {'lat': lat, 'lng': lng, 'city': city, 'address': discovered_address or store['address']},
            'message': f'坐标已更新: ({lat}, {lng})',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


def _infer_store_city(store):
    """从来源视频标题或地址中尽量推断城市，用于管理页分组和重新编码。"""
    title = store.get('source_video_title') or ''
    match = re.match(r'\s*([^.\s。．-]{2,12})[.。．-]', title)
    if match:
        return match.group(1).strip()

    address = store.get('address') or ''
    city_keywords = [
        '北京', '上海', '广州', '深圳', '成都', '重庆', '杭州', '南京', '苏州', '武汉',
        '西安', '天津', '长沙', '郑州', '青岛', '厦门', '福州', '宁波', '无锡', '合肥',
        '洛阳', '晋城', '香港', '澳门', '台北',
    ]
    for city in city_keywords:
        if city in address:
            return city
    return '未分组'


# ==================== API: 博主管理 ====================

@app.route('/api/bloggers')
def api_bloggers():
    try:
        bloggers = get_all_bloggers()
        return jsonify({'code': 0, 'data': bloggers})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/bloggers/search')
def api_search_bloggers():
    keyword = request.args.get('q', '')
    if not keyword:
        return jsonify({'code': -1, 'error': '请输入搜索关键词'}), 400

    try:
        results = search_user(keyword)
        return jsonify({'code': 0, 'data': results})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


def _get_blogger_by_uid(platform_uid):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bloggers WHERE platform_uid=? AND status='active'",
        (str(platform_uid),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _fetch_and_save_recent_videos(blogger_id, platform_uid, count=20, start_date='', end_date=''):
    count = max(1, min(int(count or 20), 50))
    try:
        videos = fetch_user_recent_videos(
            str(platform_uid),
            count=count,
            start_date=start_date,
            end_date=end_date,
        )
    except BilibiliRiskControlError as e:
        return [], 0, str(e)
    added = add_videos_batch(blogger_id, videos) if videos else 0
    return videos, added, ''


@app.route('/api/bloggers', methods=['POST'])
def api_add_blogger():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'error': '请求数据为空'}), 400

        platform_uid = str(data.get('platform_uid', '')).strip()
        if not platform_uid:
            return jsonify({'code': -1, 'error': '缺少 platform_uid（B站UID）'}), 400

        # 如果只有 UID，尝试从B站获取信息
        if not data.get('name'):
            info = get_user_info(platform_uid)
            if info:
                data.update(info)
            else:
                return jsonify({'code': -1, 'error': f'无法获取UID={platform_uid}的用户信息'}), 400

        blogger_id = add_blogger(
            name=data.get('name', platform_uid),
            platform_uid=platform_uid,
            platform=data.get('platform', 'bilibili'),
            avatar=data.get('avatar', ''),
            followers=data.get('followers', ''),
            bio=data.get('bio', ''),
        )

        if blogger_id is None:
            return jsonify({'code': -1, 'error': '该博主已存在'}), 409

        # 自动低频获取最近视频；失败不影响博主建档
        _fetch_and_save_recent_videos(blogger_id, platform_uid, count=20)

        return jsonify({'code': 0, 'data': {'id': blogger_id, 'name': data.get('name')}})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/bloggers/import-videos', methods=['POST'])
def api_import_blogger_videos():
    """通过UP主主页链接、UID或名称创建/复用博主，并拉取最近视频。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'error': '请求数据为空'}), 400

        user_input = str(data.get('input', '')).strip()
        count = max(1, min(int(data.get('count', 20) or 20), 50))
        start_date = str(data.get('start_date', '')).strip()
        end_date = str(data.get('end_date', '')).strip()
        if not user_input:
            return jsonify({'code': -1, 'error': '请输入UP主主页链接、UID或名称'}), 400

        info = resolve_user_input(user_input)
        if not info or not info.get('platform_uid'):
            return jsonify({'code': -1, 'error': '无法识别该UP主，请优先使用B站空间主页链接或UID'}), 400

        platform_uid = str(info['platform_uid'])
        existing = _get_blogger_by_uid(platform_uid)
        created = False
        if existing:
            blogger_id = existing['id']
            blogger_name = existing.get('name') or info.get('name') or platform_uid
        else:
            blogger_id = add_blogger(
                name=info.get('name') or platform_uid,
                platform_uid=platform_uid,
                platform='bilibili',
                avatar=info.get('avatar', ''),
                followers=info.get('followers', ''),
                bio=info.get('bio', ''),
            )
            if blogger_id is None:
                existing = _get_blogger_by_uid(platform_uid)
                if not existing:
                    return jsonify({'code': -1, 'error': '博主创建失败'}), 500
                blogger_id = existing['id']
                blogger_name = existing.get('name') or info.get('name') or platform_uid
            else:
                created = True
                blogger_name = info.get('name') or platform_uid

        videos, added, fetch_error = _fetch_and_save_recent_videos(
            blogger_id,
            platform_uid,
            count=count,
            start_date=start_date,
            end_date=end_date,
        )
        if not videos:
            return jsonify({
                'code': -1,
                'error': fetch_error or '未能获取到视频，可能触发B站风控。建议稍后重试，或使用手动BV批量/单条添加。',
                'data': {
                    'blogger_id': blogger_id,
                    'blogger_name': blogger_name,
                    'created': created,
                    'total_fetched': 0,
                    'new_videos': 0,
                }
            }), 200

        return jsonify({
            'code': 0,
            'data': {
                'blogger_id': blogger_id,
                'blogger_name': blogger_name,
                'created': created,
                'total_fetched': len(videos),
                'new_videos': added,
            },
            'message': f'{blogger_name}: 获取到 {len(videos)} 个视频，新增 {added} 个',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/bloggers/<int:blogger_id>', methods=['DELETE'])
def api_delete_blogger(blogger_id):
    try:
        delete_blogger(blogger_id)
        return jsonify({'code': 0, 'message': '已删除'})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/bloggers/<int:blogger_id>/fetch', methods=['POST'])
def api_fetch_videos(blogger_id):
    """获取博主最新视频（从空间页抓取）"""
    try:
        blogger = get_blogger(blogger_id)
        if not blogger:
            return jsonify({'code': -1, 'error': '博主不存在'}), 404

        count = request.args.get('count', default=20, type=int)

        # 从空间页抓取视频
        videos, added, fetch_error = _fetch_and_save_recent_videos(blogger['id'], blogger['platform_uid'], count=count)
        if not videos:
            return jsonify({
                'code': -1,
                'error': fetch_error or '未能获取到视频（B站风控限制），请尝试手动添加BV号',
                'data': {'total_fetched': 0, 'new_videos': 0}
            }), 200

        return jsonify({
            'code': 0,
            'data': {'total_fetched': len(videos), 'new_videos': added},
            'message': f'获取到 {len(videos)} 个视频，新增 {added} 个',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== API: 手动添加视频（BV号/链接） ====================

@app.route('/api/videos/add', methods=['POST'])
def api_add_video():
    """通过BV号或视频链接手动添加单个视频"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'error': '请求数据为空'}), 400

        bv_input = data.get('bv', '').strip()
        blogger_id = data.get('blogger_id')

        if not bv_input:
            return jsonify({'code': -1, 'error': '请提供BV号或视频链接'}), 400
        if not blogger_id:
            return jsonify({'code': -1, 'error': '请选择所属博主'}), 400

        # 获取视频详情
        detail = fetch_video_by_url(bv_input)
        if not detail:
            return jsonify({'code': -1, 'error': '无法获取视频信息，请检查BV号是否正确'}), 400

        # 保存视频
        video_data = [{
            'platform_video_id': detail['bvid'],
            'title': detail['title'],
            'description': detail['description'],
            'cover_url': detail['cover_url'],
            'tags': detail['tags'],
            'publish_date': detail['publish_date'],
            'url': detail['url'],
            'duration': detail['duration'],
            'play_count': detail['play_count'],
        }]

        added = add_videos_batch(blogger_id, video_data)

        if added:
            return jsonify({
                'code': 0,
                'data': detail,
                'message': f'已添加视频: {detail["title"][:30]}...',
            })
        else:
            return jsonify({
                'code': 0,
                'data': detail,
                'message': '该视频已存在，无需重复添加',
            })

    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/add-batch', methods=['POST'])
def api_add_videos_batch_by_input():
    """批量通过BV号或视频链接添加视频。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': -1, 'error': '请求数据为空'}), 400

        text = str(data.get('text', '')).strip()
        blogger_id = data.get('blogger_id')
        if not text:
            return jsonify({'code': -1, 'error': '请粘贴BV号或B站视频链接'}), 400
        if not blogger_id:
            return jsonify({'code': -1, 'error': '请选择所属博主'}), 400

        candidates = []
        for item in re.split(r'[\s,，;；]+', text):
            item = item.strip()
            if item:
                candidates.append(item)

        seen = set()
        saved = []
        failed = []
        duplicates = 0
        for item in candidates[:50]:
            detail = fetch_video_by_url(item)
            if not detail:
                failed.append({'input': item, 'error': '无法获取视频信息'})
                continue
            bvid = detail['bvid']
            if bvid in seen:
                duplicates += 1
                continue
            seen.add(bvid)

            video_data = [{
                'platform_video_id': bvid,
                'title': detail['title'],
                'description': detail['description'],
                'cover_url': detail['cover_url'],
                'tags': detail['tags'],
                'publish_date': detail['publish_date'],
                'url': detail['url'],
                'duration': detail['duration'],
                'play_count': detail['play_count'],
            }]
            added = add_videos_batch(blogger_id, video_data)
            if added:
                saved.append({'bvid': bvid, 'title': detail['title']})
            else:
                duplicates += 1

        return jsonify({
            'code': 0,
            'data': {
                'total_input': len(candidates),
                'processed': min(len(candidates), 50),
                'new_videos': len(saved),
                'duplicates': duplicates,
                'failed': failed,
                'saved': saved,
            },
            'message': f'批量处理 {min(len(candidates), 50)} 条，新增 {len(saved)} 个，重复 {duplicates} 个，失败 {len(failed)} 个',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== API: 视频管理 ====================

@app.route('/api/videos')
def api_videos():
    try:
        blogger_id = request.args.get('blogger_id', type=int)
        status = request.args.get('status')
        keyword = request.args.get('q', '').strip()
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        include_total = request.args.get('include_total', '').lower() in ('1', 'true', 'yes')
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        videos = get_videos(
            blogger_id=blogger_id,
            status=status,
            limit=limit,
            offset=offset,
            keyword=keyword,
        )
        if include_total:
            total = count_videos(blogger_id=blogger_id, status=status, keyword=keyword)
            return jsonify({
                'code': 0,
                'data': {
                    'items': videos,
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                }
            })
        return jsonify({'code': 0, 'data': videos})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/<int:video_id>/analyze', methods=['POST'])
def api_analyze_video(video_id):
    """分析单个视频"""
    try:
        result = analyze_video(video_id)
        if result['success']:
            return jsonify({
                'code': 0,
                'data': {
                    'stores_found': len(result.get('store_ids', [])),
                    'summary': result.get('summary', ''),
                    'store_ids': result.get('store_ids', []),
                    'stores': result.get('stores', []),
                },
                'message': f"分析完成，识别到 {len(result.get('store_ids', []))} 家店铺",
            })
        return jsonify({'code': -1, 'error': result.get('error', '分析失败')}), 500
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/<int:video_id>/analyze/stream', methods=['POST'])
def api_analyze_video_stream(video_id):
    """
    流式分析单个视频 — 通过 SSE 实时推送分析进度
    前端使用 fetch + ReadableStream 读取进度事件
    """
    q = queue.Queue()

    def on_progress(step, total, name):
        q.put({
            'type': 'progress',
            'step': step,
            'total': total,
            'name': name,
        })

    def run_analysis():
        try:
            result = analyze_video(video_id, progress_callback=on_progress)
            q.put({
                'type': 'done',
                'success': result.get('success', False),
                'stores_found': len(result.get('store_ids', [])),
                'summary': result.get('summary', ''),
                'error': result.get('error', ''),
            })
        except Exception as e:
            q.put({'type': 'error', 'error': str(e)})

    thread = threading.Thread(target=run_analysis, daemon=True)
    thread.start()

    def generate():
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg['type'] in ('done', 'error'):
                    break
            except queue.Empty:
                # 心跳保持连接
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _update_analysis_job(job_id, **updates):
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)
        if not job:
            return
        job.update(updates)
        job['updated_at'] = time.time()


def _run_analysis_job(job_id):
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)
        if not job:
            return
        video_ids = list(job.get('video_ids') or [])

    results = []
    total_videos = len(video_ids)
    for index, vid in enumerate(video_ids, start=1):
        _update_analysis_job(
            job_id,
            status='running',
            current_video_id=vid,
            current_index=index,
            step=0,
            total_steps=9,
            current=f'开始分析视频 #{vid}',
        )

        def on_progress(step, total, name, current_vid=vid, current_index=index):
            _update_analysis_job(
                job_id,
                current_video_id=current_vid,
                current_index=current_index,
                step=step,
                total_steps=total,
                current=name,
            )

        try:
            result = analyze_video(vid, progress_callback=on_progress)
            results.append({
                'video_id': vid,
                'success': result.get('success', False),
                'stores_found': len(result.get('store_ids', [])),
                'summary': result.get('summary', ''),
                'error': result.get('error', ''),
            })
        except Exception as e:
            results.append({
                'video_id': vid,
                'success': False,
                'stores_found': 0,
                'summary': '',
                'error': str(e),
            })

        _update_analysis_job(job_id, results=results)

    success_count = sum(1 for item in results if item.get('success'))
    _update_analysis_job(
        job_id,
        status='success' if success_count == total_videos else 'failed',
        current_video_id=None,
        current_index=total_videos,
        step=9,
        total_steps=9,
        current=f'分析完成：{success_count}/{total_videos} 成功',
        completed_at=time.time(),
        results=results,
    )


@app.route('/api/analysis-jobs', methods=['POST'])
def api_create_analysis_job():
    try:
        data = request.get_json() or {}
        video_ids = data.get('video_ids')
        if video_ids is None and data.get('video_id'):
            video_ids = [data.get('video_id')]
        if not isinstance(video_ids, list):
            return jsonify({'code': -1, 'error': '请提供 video_ids'}), 400

        normalized_ids = []
        for item in video_ids:
            try:
                vid = int(item)
            except (TypeError, ValueError):
                continue
            if vid > 0 and vid not in normalized_ids:
                normalized_ids.append(vid)
        if not normalized_ids:
            return jsonify({'code': -1, 'error': '请提供有效的视频ID'}), 400
        if len(normalized_ids) > 50:
            return jsonify({'code': -1, 'error': '单次最多提交 50 个视频'}), 400

        job_id = uuid.uuid4().hex
        now = time.time()
        with analysis_jobs_lock:
            analysis_jobs[job_id] = {
                'id': job_id,
                'status': 'queued',
                'video_ids': normalized_ids,
                'total_videos': len(normalized_ids),
                'current_index': 0,
                'current_video_id': None,
                'step': 0,
                'total_steps': 9,
                'current': '任务已创建，等待开始',
                'results': [],
                'created_at': now,
                'updated_at': now,
            }

        thread = threading.Thread(target=_run_analysis_job, args=(job_id,), daemon=True)
        thread.start()
        with analysis_jobs_lock:
            job_snapshot = dict(analysis_jobs[job_id])
        return jsonify({'code': 0, 'data': job_snapshot, 'message': '分析任务已提交'})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/analysis-jobs/<job_id>')
def api_get_analysis_job(job_id):
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)
        if not job:
            return jsonify({'code': -1, 'error': '分析任务不存在或已过期'}), 404
        return jsonify({'code': 0, 'data': dict(job)})


@app.route('/api/videos/batch-analyze', methods=['POST'])
def api_batch_analyze():
    """批量分析视频"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])
        if not video_ids:
            return jsonify({'code': -1, 'error': '请提供视频ID列表'}), 400

        results = batch_analyze(video_ids)
        success_count = sum(1 for r in results if r['success'])
        return jsonify({
            'code': 0,
            'data': {
                'total': len(results),
                'success': success_count,
                'results': results,
            },
            'message': f'批量分析完成：{success_count}/{len(results)} 成功',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== API: 分析日志 ====================

@app.route('/api/analysis-logs')
def api_analysis_logs():
    try:
        video_id = request.args.get('video_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        logs = get_analysis_logs(video_id=video_id, limit=limit)
        return jsonify({'code': 0, 'data': logs})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/<int:video_id>/analysis/steps')
def api_video_analysis_steps(video_id):
    try:
        analysis_log_id = request.args.get('analysis_log_id', type=int)
        steps = get_analysis_steps(
            video_id=video_id,
            analysis_log_id=analysis_log_id,
            limit=100,
        )
        return jsonify({'code': 0, 'data': steps})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== 健康检查 ====================

@app.route('/api/videos/<int:video_id>', methods=['DELETE'])
def api_delete_video(video_id):
    try:
        video = get_video(video_id)
        if not video:
            return jsonify({'code': -1, 'error': '视频不存在'}), 404
        delete_video(video_id)
        return jsonify({'code': 0, 'message': '已删除'})
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/batch-delete', methods=['POST'])
def api_delete_videos_batch():
    try:
        data = request.get_json() or {}
        video_ids = data.get('video_ids') or []
        if not isinstance(video_ids, list) or not video_ids:
            return jsonify({'code': -1, 'error': '请选择要删除的视频'}), 400
        deleted = delete_videos_batch(video_ids)
        return jsonify({
            'code': 0,
            'data': {'deleted': deleted},
            'message': f'已删除 {deleted} 个视频',
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


@app.route('/api/videos/<int:video_id>/analysis')
def api_video_analysis(video_id):
    try:
        logs = get_analysis_logs(video_id=video_id, limit=1)
        video = get_video(video_id)
        if not video:
            return jsonify({'code': -1, 'error': '视频不存在'}), 404
        log = logs[0] if logs else None
        steps = get_analysis_steps(
            video_id=video_id,
            analysis_log_id=log['id'] if log else None,
            limit=100,
        ) if log else []
        return jsonify({
            'code': 0,
            'data': {
                'video': video,
                'log': log,
                'steps': steps,
            }
        })
    except Exception as e:
        return jsonify({'code': -1, 'error': str(e)}), 500


# ==================== 健康检查 ====================

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': '探店地图服务正常运行'})


# ==================== 启动 ====================

if __name__ == '__main__':
    print("=" * 50)
    print("  探店地图 - Food Explorer Backend")
    print("=" * 50)

    init_db()
    print("[OK] 数据库初始化完成")
    print(f"[OK] 数据库路径: {os.path.join(project_dir, 'data', 'tandian.db')}")
    print(f"[OK] 前台页面: http://localhost:5000/")
    print(f"[OK] API接口: http://localhost:5000/api/")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5000, debug=True)
