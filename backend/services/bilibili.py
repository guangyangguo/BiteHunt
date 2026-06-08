"""
B站视频采集服务
支持：UP主信息获取、手动BV号视频详情抓取、视频详情页解析
"""

import re
import json
import time
import hashlib
import requests
from urllib.parse import urlencode
from datetime import datetime

try:
    from config import get as get_config
except ImportError:
    get_config = None

BILIBILI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32,
    15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19,
    29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63,
    57, 62, 11, 36, 20, 34, 44, 52,
]


class BilibiliRiskControlError(Exception):
    """B站空间视频列表接口触发风控。"""


def _make_session():
    """创建一个带基础 cookie 的 session"""
    session = requests.Session()
    session.headers.update(BILIBILI_HEADERS)
    cookie = get_config('bilibili_cookie', '') if get_config else ''
    if cookie:
        session.headers.update({'Cookie': cookie})
    try:
        session.get('https://www.bilibili.com/', timeout=8)
    except Exception:
        pass
    return session


def _get_wbi_keys(session):
    """获取 WBI 签名所需 key。失败时返回空字符串。"""
    try:
        resp = session.get('https://api.bilibili.com/x/web-interface/nav', timeout=10)
        data = resp.json()
        wbi_img = data.get('data', {}).get('wbi_img', {})
        img_url = wbi_img.get('img_url', '')
        sub_url = wbi_img.get('sub_url', '')
        img_key = img_url.rsplit('/', 1)[-1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[-1].split('.')[0]
        return img_key, sub_key
    except Exception as e:
        print(f"[Bilibili] 获取WBI key失败: {e}")
        return '', ''


def _get_mixin_key(img_key, sub_key):
    raw = img_key + sub_key
    return ''.join(raw[i] for i in WBI_MIXIN_KEY_ENC_TAB if i < len(raw))[:32]


def _sign_wbi_params(params, img_key, sub_key):
    mixin_key = _get_mixin_key(img_key, sub_key)
    if not mixin_key:
        return params

    signed = dict(params)
    signed['wts'] = int(time.time())
    clean = {}
    for key, value in signed.items():
        value = str(value)
        for ch in "!'()*":
            value = value.replace(ch, '')
        clean[key] = value

    query = urlencode(sorted(clean.items()))
    clean['w_rid'] = hashlib.md5((query + mixin_key).encode('utf-8')).hexdigest()
    return clean


def get_user_info(mid: str):
    """获取UP主基本信息（通过空间页抓取）"""
    try:
        session = _make_session()
        resp = session.get(
            f'https://api.bilibili.com/x/space/wbi/acc/info?mid={mid}',
            headers={'Referer': f'https://space.bilibili.com/{mid}/'},
            timeout=10,
        )
        data = resp.json()
        if data.get('code') != 0:
            # 降级：从空间页面HTML提取
            return _get_user_info_from_html(mid)

        info = data['data']
        avatar = info.get('face', '')
        if avatar and avatar.startswith('//'):
            avatar = 'https:' + avatar

        return {
            'name': info.get('name', ''),
            'avatar': avatar,
            'bio': info.get('sign', ''),
            'followers': _format_count(info.get('follower', 0)),
            'platform_uid': str(mid),
        }
    except Exception as e:
        print(f"[Bilibili] 获取用户信息失败 mid={mid}: {e}")
        return _get_user_info_from_html(mid)


def _get_user_info_from_html(mid: str):
    """从B站空间页HTML提取用户信息"""
    try:
        session = _make_session()
        resp = session.get(
            f'https://space.bilibili.com/{mid}',
            timeout=10,
        )
        html = resp.text

        name_match = re.search(r'<span[^>]*id="h-name"[^>]*>([^<]+)</span>', html)
        name = name_match.group(1).strip() if name_match else f'UP主{mid}'

        avatar_match = re.search(r'<img[^>]*class="[^"]*avatar[^"]*"[^>]*src="([^"]+)"', html)
        avatar = avatar_match.group(1) if avatar_match else ''
        if avatar.startswith('//'):
            avatar = 'https:' + avatar

        return {
            'name': name,
            'avatar': avatar,
            'bio': '',
            'followers': '',
            'platform_uid': str(mid),
        }
    except Exception:
        return {
            'name': f'UP主{mid}',
            'avatar': '',
            'bio': '',
            'followers': '',
            'platform_uid': str(mid),
        }


def get_video_detail(bvid: str):
    """
    获取单个视频详情（通过B站 view API）
    这是最可靠的方式，不需要 wbi 签名
    """
    try:
        session = _make_session()
        resp = session.get(
            f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}',
            headers={'Referer': f'https://www.bilibili.com/video/{bvid}/'},
            timeout=15,
        )
        data = resp.json()
        if data.get('code') != 0:
            print(f"[Bilibili] 获取视频详情失败 bvid={bvid}: code={data.get('code')} msg={data.get('message')}")
            return None

        info = data['data']
        return {
            'bvid': bvid,
            'title': info.get('title', ''),
            'description': info.get('desc', ''),
            'tags': [t.get('tag_name', '') for t in info.get('tags', [])],
            'cover_url': info.get('pic', ''),
            'publish_date': _format_timestamp(info.get('pubdate', 0)),
            'url': f'https://www.bilibili.com/video/{bvid}',
            'duration': _format_duration(info.get('duration', 0)),
            'play_count': _format_count(info.get('stat', {}).get('view', 0)),
            'danmaku_count': info.get('stat', {}).get('danmaku', 0),
            'reply_count': info.get('stat', {}).get('reply', 0),
            'favorite_count': info.get('stat', {}).get('favorite', 0),
            'like_count': info.get('stat', {}).get('like', 0),
            'cid': info.get('cid', 0),
        }
    except Exception as e:
        print(f"[Bilibili] 获取视频详情异常 bvid={bvid}: {e}")
        return None


def fetch_video_by_url(url_or_bvid: str):
    """
    从BV号或B站视频URL提取视频信息并返回标准格式

    支持格式：
    - BV1xx411c7mD
    - https://www.bilibili.com/video/BV1xx411c7mD
    - https://b23.tv/xxxxx
    """
    bvid = _extract_bvid(url_or_bvid)
    if not bvid:
        return None
    return get_video_detail(bvid)


def resolve_user_input(user_input: str):
    """
    从 UID、B站空间主页链接或UP主名称解析用户信息。
    名称会走搜索接口并取第一个结果，适合作为便捷入口；精确性要求高时建议使用UID/主页链接。
    """
    mid = extract_mid(user_input)
    if mid:
        return get_user_info(mid)

    keyword = (user_input or '').strip()
    if not keyword:
        return None

    results = search_user(keyword)
    return results[0] if results else None


def search_user(keyword: str):
    """搜索UP主"""
    try:
        session = _make_session()
        resp = session.get(
            'https://api.bilibili.com/x/web-interface/search/type',
            params={
                'search_type': 'bili_user',
                'keyword': keyword,
                'page': 1,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get('code') != 0:
            return []

        results = []
        for u in data.get('data', {}).get('result', [])[:10]:
            avatar = u.get('upic', '')
            if avatar and avatar.startswith('//'):
                avatar = 'https:' + avatar

            results.append({
                'name': u.get('uname', ''),
                'platform_uid': str(u.get('mid', '')),
                'avatar': avatar,
                'bio': u.get('usign', ''),
                'followers': _format_count(u.get('fans', 0)),
                'video_count': u.get('videos', 0),
            })
        return results
    except Exception as e:
        print(f"[Bilibili] 搜索用户失败 keyword={keyword}: {e}")
        return []


def extract_mid(user_input: str) -> str:
    """从 UID 或 B站空间链接中提取 mid。"""
    if not user_input:
        return ''

    text = str(user_input).strip()
    if re.match(r'^\d{2,}$', text):
        return text

    patterns = [
        r'space\.bilibili\.com/(\d+)',
        r'bilibili\.com/space/(\d+)',
        r'[?&]mid=(\d+)',
        r'[?&]vmid=(\d+)',
        r'/(\d+)(?:[/?#]|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ''


def fetch_user_recent_videos(mid: str, count: int = 10, start_date: str = '', end_date: str = ''):
    """
    尝试获取UP主最近的视频。
    优先使用 WBI 视频列表接口；失败时再从空间页 HTML 提取，降低对单一方式的依赖。
    """
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    videos = _fetch_user_recent_videos_by_wbi(mid, count=count, start_dt=start_dt, end_dt=end_dt)
    if videos is None:
        raise BilibiliRiskControlError('B站空间视频列表接口触发风控，请配置 BILIBILI_COOKIE 后低频重试，或使用批量BV/链接添加。')
    if videos:
        return videos

    return _fetch_user_recent_videos_from_html(mid, count=count, start_dt=start_dt, end_dt=end_dt)


def _fetch_user_recent_videos_by_wbi(mid: str, count: int = 10, start_dt=None, end_dt=None):
    """通过 B站空间 WBI 接口获取最近视频。"""
    try:
        session = _make_session()
        img_key, sub_key = _get_wbi_keys(session)
        if not img_key or not sub_key:
            return []

        videos = []
        page_size = 30 if start_dt or end_dt else min(max(int(count or 10), 1), 30)
        page = 1
        max_pages = 8 if (start_dt or end_dt) else 3
        while len(videos) < count and page <= max_pages:
            params = _sign_wbi_params({
                'mid': str(mid),
                'pn': page,
                'ps': page_size,
                'tid': 0,
                'order': 'pubdate',
                'platform': 'web',
                'web_location': 1550101,
                'order_avoided': 'true',
            }, img_key, sub_key)
            resp = session.get(
                'https://api.bilibili.com/x/space/wbi/arc/search',
                params=params,
                headers={'Referer': f'https://space.bilibili.com/{mid}/video'},
                timeout=15,
            )
            data = resp.json()
            if data.get('code') != 0:
                print(f"[Bilibili] WBI视频列表失败 mid={mid}: code={data.get('code')} msg={data.get('message')}")
                if data.get('code') in (-412, -352):
                    return None
                return []

            vlist = data.get('data', {}).get('list', {}).get('vlist', [])
            if not vlist:
                break

            for v in vlist:
                bvid = v.get('bvid', '')
                if not bvid:
                    continue
                created_dt = _datetime_from_timestamp(v.get('created', 0))
                if end_dt and created_dt and created_dt.date() > end_dt.date():
                    continue
                if start_dt and created_dt and created_dt.date() < start_dt.date():
                    return videos[:count]
                videos.append({
                    'platform_video_id': bvid,
                    'title': v.get('title', ''),
                    'description': v.get('description', ''),
                    'cover_url': v.get('pic', ''),
                    'tags': _parse_tags(v.get('tag', '')),
                    'publish_date': _format_timestamp(v.get('created', 0)),
                    'url': f'https://www.bilibili.com/video/{bvid}',
                    'duration': _format_duration(v.get('length', '')),
                    'play_count': _format_count(v.get('play', 0)),
                })
                if len(videos) >= count:
                    break
            page += 1

        return videos[:count]
    except Exception as e:
        print(f"[Bilibili] WBI视频列表异常 mid={mid}: {e}")
        return []


def _fetch_user_recent_videos_from_html(mid: str, count: int = 10, start_dt=None, end_dt=None):
    """从空间页 HTML 提取最近视频，作为 API 失败后的兜底。"""
    try:
        session = _make_session()
        resp = session.get(
            f'https://space.bilibili.com/{mid}/video',
            timeout=15,
        )

        # 从 HTML 中提取 video 数据
        # B站空间页可能内嵌了 __INITIAL_STATE__ 或通过其他方式传递数据
        videos = []

        # 方法1: 尝试匹配 __INITIAL_STATE__
        match = re.search(
            r'__INITIAL_STATE__\s*=\s*(\{.*?"vlist":\s*\[[\s\S]*?\]\s*\})',
            resp.text, re.DOTALL
        )
        if match:
            try:
                state = json.loads(match.group(1))
                vlist = (
                    state.get('videoList', {})
                    .get('list', {})
                    .get('vlist', [])
                )
                for v in vlist[:count]:
                    bvid = v.get('bvid', '')
                    created_dt = _datetime_from_timestamp(v.get('created', 0))
                    if end_dt and created_dt and created_dt.date() > end_dt.date():
                        continue
                    if start_dt and created_dt and created_dt.date() < start_dt.date():
                        break
                    videos.append({
                        'platform_video_id': bvid,
                        'title': v.get('title', ''),
                        'description': v.get('description', ''),
                        'cover_url': v.get('pic', ''),
                        'tags': _parse_tags(v.get('tag', '')),
                        'publish_date': _format_timestamp(v.get('created', 0)),
                        'url': f'https://www.bilibili.com/video/{bvid}',
                        'duration': _format_duration(v.get('length', '')),
                        'play_count': _format_count(v.get('play', 0)),
                    })
                return videos
            except (json.JSONDecodeError, KeyError):
                pass

        # 方法2: 从页面链接提取
        bvid_pattern = re.findall(r'/video/(BV[a-zA-Z0-9]{10})', resp.text)
        title_pattern = re.findall(
            r'<a[^>]*title="([^"]*)"[^>]*class="[^"]*title[^"]*"[^>]*>',
            resp.text
        )
        seen = set()
        for bvid in bvid_pattern[:count]:
            if bvid not in seen:
                seen.add(bvid)
                # 尝试获取详情
                detail = get_video_detail(bvid)
                if detail:
                    videos.append({
                        'platform_video_id': bvid,
                        'title': detail['title'],
                        'description': detail['description'],
                        'cover_url': detail['cover_url'],
                        'tags': detail['tags'],
                        'publish_date': detail['publish_date'],
                        'url': detail['url'],
                        'duration': detail['duration'],
                        'play_count': detail['play_count'],
                    })

        return videos
    except Exception as e:
        print(f"[Bilibili] 空间页抓取失败 mid={mid}: {e}")
        return []


# ==================== 辅助函数 ====================

def _extract_bvid(url_or_bvid: str) -> str:
    """从输入中提取 BV 号"""
    if not url_or_bvid:
        return ''

    url_or_bvid = url_or_bvid.strip()

    # 已经是 BV 号
    if re.match(r'^BV[a-zA-Z0-9]{10}$', url_or_bvid):
        return url_or_bvid

    # 从 URL 提取
    patterns = [
        r'bilibili\.com/video/(BV[a-zA-Z0-9]{10})',
        r'b23\.tv/([a-zA-Z0-9]+)',
        r'bilibili\.com/video/av(\d+)',
        r'(BV[a-zA-Z0-9]{10})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_bvid)
        if match:
            return match.group(1)

    return ''


def _parse_tags(tag_str: str) -> list:
    """解析标签字符串"""
    if not tag_str:
        return []
    return [t.strip() for t in tag_str.split(',') if t.strip()]



def fetch_video_audio(bvid: str, output_path: str):
    """下载B站视频音频，保存到output_path，返回(成功, 文件大小)"""
    try:
        session = _make_session()
        ref = f'https://www.bilibili.com/video/{bvid}/'

        # 获取cid
        resp = session.get(
            f'https://api.bilibili.com/x/player/pagelist?bvid={bvid}',
            headers={'Referer': ref}, timeout=10
        )
        pdata = resp.json()
        if pdata.get('code') != 0 or not pdata.get('data'):
            return False, 0
        cid = pdata['data'][0].get('cid', 0)
        if not cid:
            return False, 0

        # 获取音频流URL（DASH格式）
        resp = session.get(
            f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16&fnver=0&fourk=1',
            headers={'Referer': ref}, timeout=15
        )
        pdata = resp.json()
        audio_streams = pdata.get('data', {}).get('dash', {}).get('audio', [])
        if not audio_streams:
            return False, 0

        # 选最高码率音频
        best = max(audio_streams, key=lambda a: a.get('bandwidth', 0))
        url = best.get('baseUrl', best.get('base_url', ''))
        if not url:
            return False, 0

        # 下载音频
        resp = session.get(url, headers={'Referer': ref}, timeout=120, stream=True)
        if resp.status_code != 200:
            return False, 0

        total_size = 0
        with open(output_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total_size += len(chunk)

        print(f"[Bilibili] 音频下载完成: {output_path} -> {total_size} bytes")
        return True, total_size
    except Exception as e:
        print(f"[Bilibili] 音频下载失败 bvid={bvid}: {e}")
        return False, 0


def fetch_video_subtitle(bvid: str, cid: int = 0):
    try:
        session = _make_session()
        ref = f'https://www.bilibili.com/video/{bvid}/'
        if not cid:
            resp = session.get(f'https://api.bilibili.com/x/player/pagelist?bvid={bvid}', headers={'Referer': ref}, timeout=10)
            pdata = resp.json()
            if pdata.get('code') != 0 or not pdata.get('data'):
                return ''
            cid = pdata['data'][0].get('cid', 0)
        if not cid: return ''
        resp = session.get(f'https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}', headers={'Referer': ref}, timeout=15)
        pdata = resp.json()
        subtitles = pdata.get('data',{}).get('subtitle',{}).get('subtitles',[])
        if not subtitles: return ''
        subtitle_url = ''
        for sub in subtitles:
            if 'ai' in sub.get('lan_doc','').lower() or 'zh' in sub.get('lan',''):
                subtitle_url = sub.get('subtitle_url','')
                break
        if not subtitle_url and subtitles:
            subtitle_url = subtitles[0].get('subtitle_url','')
        if not subtitle_url: return ''
        if subtitle_url.startswith('//'): subtitle_url = 'https:' + subtitle_url
        sr = session.get(subtitle_url, timeout=15)
        sd = sr.json()
        body = sd.get('body',[])
        lines = [item['content'] for item in body if item.get('content','').strip()]
        return '\n'.join(lines)
    except Exception as e:
        print(f'[Bilibili] 字幕获取失败 {bvid}: {e}')
        return ''

def _format_count(num):
    """格式化数字"""
    if num is None:
        return '0'
    num = int(num)
    if num >= 100000000:
        return f'{num / 100000000:.1f}亿'
    if num >= 10000:
        return f'{num / 10000:.1f}万'
    return str(num)


def _format_timestamp(ts):
    """格式化时间戳"""
    if not ts:
        return ''
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except (ValueError, OSError):
        return ''


def _datetime_from_timestamp(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts))
    except (ValueError, OSError, TypeError):
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d')
    except ValueError:
        return None


def _format_duration(seconds):
    """格式化秒数"""
    if not seconds:
        return ''
    if isinstance(seconds, str) and ':' in seconds:
        return seconds
    try:
        s = int(seconds)
        return f'{s // 60}:{s % 60:02d}'
    except (ValueError, TypeError):
        return ''
