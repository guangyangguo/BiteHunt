"""
B站视频采集服务
支持：UP主信息获取、手动BV号视频详情抓取、视频详情页解析
"""

import re
import json
import requests
from datetime import datetime

BILIBILI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


def _make_session():
    """创建一个带基础 cookie 的 session"""
    session = requests.Session()
    session.headers.update(BILIBILI_HEADERS)
    try:
        session.get('https://www.bilibili.com/', timeout=8)
    except Exception:
        pass
    return session


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


def fetch_user_recent_videos(mid: str, count: int = 10):
    """
    尝试获取UP主最近的视频（从空间页HTML提取）
    作为 API 不可用时的降级方案
    """
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


def _format_duration(seconds):
    """格式化秒数"""
    if not seconds:
        return ''
    try:
        s = int(seconds)
        return f'{s // 60}:{s % 60:02d}'
    except (ValueError, TypeError):
        return ''
