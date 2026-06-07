# -*- coding: utf-8 -*-
"""
探店地图 - 统一配置模块
从 .env 文件和环境变量读取配置，不再依赖数据库 config 表
"""
import os


def _load_dotenv():
    """加载 .env 文件到环境变量（不覆盖已有的环境变量）"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        return

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            # 解析 KEY=VALUE
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            # 去掉引号
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # 不覆盖已有的环境变量
            if key not in os.environ:
                os.environ[key] = value


# 模块加载时自动读取 .env
_load_dotenv()

# 默认值
_DEFAULTS = {
    'llm_api_url': 'https://api.deepseek.com/v1/chat/completions',
    'llm_api_key': '',
    'llm_model': 'deepseek-chat',
    'amap_api_key': '',
    'stt_api_url': 'https://api.openai.com/v1/audio/transcriptions',
    'stt_api_key': '',
    'stt_model': 'whisper-1',
    'stt_use_remote_api': 'true',
    'stt_local_model': 'small',
    'map_center_lat': '30.655',
    'map_center_lng': '104.075',
    'map_default_zoom': '13',
}

# 环境变量名映射（小写 key -> 大写环境变量名）
_ENV_MAP = {
    'llm_api_url': 'LLM_API_URL',
    'llm_api_key': 'LLM_API_KEY',
    'llm_model': 'LLM_MODEL',
    'amap_api_key': 'AMAP_API_KEY',
    'stt_api_url': 'STT_API_URL',
    'stt_api_key': 'STT_API_KEY',
    'stt_model': 'STT_MODEL',
    'stt_use_remote_api': 'STT_USE_REMOTE_API',
    'stt_local_model': 'STT_LOCAL_MODEL',
    'map_center_lat': 'MAP_CENTER_LAT',
    'map_center_lng': 'MAP_CENTER_LNG',
    'map_default_zoom': 'MAP_DEFAULT_ZOOM',
}


def get(key, default=None):
    """读取配置，优先级：环境变量 > .env 文件 > 默认值 > default 参数"""
    env_name = _ENV_MAP.get(key)
    if env_name:
        val = os.environ.get(env_name)
        if val is not None and val != '':
            return val

    if key in _DEFAULTS:
        return _DEFAULTS[key]

    return default


def set(key, value):
    """设置配置（仅当前进程有效，不会写入 .env 文件）"""
    env_name = _ENV_MAP.get(key)
    if env_name:
        os.environ[env_name] = str(value) if value else ''


# 兼容旧接口
get_config = get
set_config = set
