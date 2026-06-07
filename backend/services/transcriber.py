"""
语音转文字服务 - 通过外部API或本地Whisper将音频转为文字
优先级：OpenAI Whisper API > 本地 openai-whisper 模型
"""
import os
import sys
import base64
import json
import mimetypes
import shutil
import subprocess
import requests
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import get

# 本地 Whisper 模型（懒加载）
_whisper_model = None
QWEN_ASR_MAX_SECONDS = 270
QWEN_ASR_MAX_BYTES = 9 * 1024 * 1024


class QwenAudioTooLongError(Exception):
    """Raised when Qwen3-ASR-Flash rejects audio for exceeding the duration limit."""


def _config_bool(key: str, default=True) -> bool:
    value = get(key)
    if value is None or value == '':
        return default
    return str(value).strip().lower() not in ('0', 'false', 'no', 'off')


def _get_local_whisper():
    """懒加载本地 Whisper 模型"""
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            model_size = get('stt_local_model') or 'small'
            print(f"[STT] 加载本地 Whisper 模型: {model_size}（首次运行会下载，请耐心等待）...")
            _whisper_model = whisper.load_model(model_size)
            print("[STT] 本地 Whisper 模型加载完成")
        except ImportError:
            print("[STT] 未安装 openai-whisper，请执行: pip install openai-whisper")
            return None
        except Exception as e:
            print(f"[STT] 本地 Whisper 模型加载失败: {e}")
            return None
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    """调用STT服务将音频文件转为文字，优先API，兜底本地模型"""
    if not os.path.exists(audio_path):
        print(f"[STT] 音频文件不存在: {audio_path}")
        return ''

    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        print("[STT] 音频文件为空，跳过转写")
        return ''

    print(f"[STT] 开始转写: {audio_path} ({file_size/1024/1024:.1f}MB)")

    # 方案1: OpenAI Whisper API / 百炼 Qwen ASR API
    api_key = get('stt_api_key') or ''
    use_remote_api = _config_bool('stt_use_remote_api', True)
    if use_remote_api and api_key:
        result = _transcribe_via_api(audio_path, api_key)
        if result:
            return result
        print("[STT] API 转写失败，降级到本地模型...")

    # 方案2: 本地 Whisper 模型
    result = _transcribe_local(audio_path)
    if result:
        return result

    print("[STT] 所有转写方案均失败，返回空结果")
    return ''


def _transcribe_via_api(audio_path: str, api_key: str) -> str:
    """通过 OpenAI Whisper API 或百炼 Qwen ASR API 转写"""
    api_url = get('stt_api_url') or 'https://api.openai.com/v1/audio/transcriptions'
    model = get('stt_model') or 'whisper-1'

    if _is_qwen_asr_config(api_url, model):
        return _transcribe_via_qwen_asr(audio_path, api_url, api_key, model)

    try:
        with open(audio_path, 'rb') as f:
            resp = requests.post(
                api_url,
                headers={'Authorization': f'Bearer {api_key}'},
                files={'file': (os.path.basename(audio_path), f, 'audio/mp4')},
                data={'model': model, 'language': 'zh', 'response_format': 'json'},
                timeout=180,
            )

        if resp.status_code != 200:
            print(f"[STT] API返回错误: {resp.status_code} - {resp.text[:200]}")
            return ''

        result = resp.json()
        text = result.get('text', '').strip()
        print(f"[STT] API转写完成: {len(text)} 字符")
        return text
    except Exception as e:
        print(f"[STT] API转写失败: {e}")
        return ''


def _is_qwen_asr_config(api_url: str, model: str) -> bool:
    """判断是否使用百炼/Qwen ASR 兼容模式"""
    value = f"{api_url} {model}".lower()
    return 'qwen3-asr' in value or 'dashscope' in value


def _guess_audio_mime(audio_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(audio_path)
    if mime_type:
        return mime_type

    ext = os.path.splitext(audio_path)[1].lower()
    if ext == '.m4a':
        return 'audio/mp4'
    if ext == '.mp3':
        return 'audio/mpeg'
    if ext == '.wav':
        return 'audio/wav'
    return 'audio/mp4'


def _extract_qwen_asr_text(content) -> str:
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                text_parts.append(str(item.get('text') or item.get('transcript') or ''))
            else:
                text_parts.append(str(item))
        return ''.join(text_parts).strip()

    if content is None:
        return ''

    text = str(content).strip()
    if not text:
        return ''

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ('text', 'transcript', 'content'):
                value = parsed.get(key)
                if value:
                    return str(value).strip()
    except json.JSONDecodeError:
        pass

    return text


def _is_qwen_audio_too_long_error(response_text: str) -> bool:
    text = (response_text or '').lower()
    return 'audio is too long' in text or 'invalidparameter' in text and 'too long' in text


def _transcribe_qwen_asr_single(audio_path: str, api_url: str, api_key: str, model: str) -> str:
    """Transcribe one audio file that is already within Qwen3-ASR-Flash limits."""
    file_size = os.path.getsize(audio_path)
    if file_size > 10 * 1024 * 1024:
        print("[STT] Qwen3-ASR-Flash segment is over 10MB, skipped")
        return ''

    try:
        with open(audio_path, 'rb') as f:
            data_url = (
                f"data:{_guess_audio_mime(audio_path)};base64,"
                f"{base64.b64encode(f.read()).decode('ascii')}"
            )

        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'input_audio',
                            'input_audio': {'data': data_url},
                        }
                    ],
                }
            ],
            'stream': False,
            'asr_options': {
                'language': 'zh',
                'enable_itn': False,
            },
        }

        resp = requests.post(
            api_url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=180,
        )

        if resp.status_code != 200:
            if _is_qwen_audio_too_long_error(resp.text):
                raise QwenAudioTooLongError(resp.text[:200])
            print(f"[STT] Qwen ASR API returned error: {resp.status_code} - {resp.text[:200]}")
            return ''

        result = resp.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        text = _extract_qwen_asr_text(content)
        print(f"[STT] Qwen ASR done: {len(text)} chars")
        return text
    except QwenAudioTooLongError:
        raise
    except Exception as e:
        print(f"[STT] Qwen ASR failed: {e}")
        return ''


def _get_audio_duration_seconds(audio_path: str):
    """Return audio duration using ffprobe, or None when ffprobe is unavailable."""
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[STT] Could not read audio duration, trying direct ASR: {e}")
        return None


def _split_audio_for_qwen(audio_path: str):
    """Split audio into chunks below the Qwen3-ASR-Flash short-audio duration limit."""
    segment_dir = tempfile.mkdtemp(prefix='tandian_qwen_asr_')
    output_pattern = os.path.join(segment_dir, 'segment_%03d.m4a')
    try:
        subprocess.run(
            [
                'ffmpeg', '-y',
                '-i', audio_path,
                '-vn',
                '-map', '0:a:0',
                '-ac', '1',
                '-ar', '16000',
                '-c:a', 'aac',
                '-b:a', '64k',
                '-f', 'segment',
                '-segment_time', str(QWEN_ASR_MAX_SECONDS),
                '-reset_timestamps', '1',
                output_pattern,
            ],
            capture_output=True,
            timeout=240,
            check=True,
        )
        segment_paths = [
            os.path.join(segment_dir, name)
            for name in sorted(os.listdir(segment_dir))
            if name.lower().endswith('.m4a')
        ]
        print(f"[STT] Qwen ASR split complete: {len(segment_paths)} segments")
        return segment_paths
    except FileNotFoundError:
        print("[STT] ffmpeg not found, cannot split long audio")
        shutil.rmtree(segment_dir, ignore_errors=True)
        return []
    except Exception as e:
        print(f"[STT] Qwen ASR split failed: {e}")
        shutil.rmtree(segment_dir, ignore_errors=True)
        return []


def _transcribe_via_qwen_asr(audio_path: str, api_url: str, api_key: str, model: str) -> str:
    """Transcribe with Qwen3-ASR-Flash, splitting long audio into short chunks."""
    duration = _get_audio_duration_seconds(audio_path)
    file_size = os.path.getsize(audio_path)
    if (duration and duration > QWEN_ASR_MAX_SECONDS) or file_size > QWEN_ASR_MAX_BYTES:
        print(f"[STT] Qwen ASR needs split: {duration or 0:.1f}s, {file_size/1024/1024:.1f}MB")
        segment_paths = _split_audio_for_qwen(audio_path)
        if not segment_paths:
            return ''

        segment_dir = os.path.dirname(segment_paths[0])
        try:
            parts = []
            for index, segment_path in enumerate(segment_paths, start=1):
                print(f"[STT] Qwen ASR segment {index}/{len(segment_paths)}")
                text = _transcribe_qwen_asr_single(segment_path, api_url, api_key, model)
                if text:
                    parts.append(text)
            return '\n'.join(parts).strip()
        finally:
            try:
                shutil.rmtree(segment_dir)
            except Exception:
                pass

    try:
        return _transcribe_qwen_asr_single(audio_path, api_url, api_key, model)
    except QwenAudioTooLongError:
        print("[STT] Qwen ASR reported audio too long, retrying with split audio")
        segment_paths = _split_audio_for_qwen(audio_path)
        if not segment_paths:
            return ''

        segment_dir = os.path.dirname(segment_paths[0])
        try:
            parts = []
            for index, segment_path in enumerate(segment_paths, start=1):
                print(f"[STT] Qwen ASR segment {index}/{len(segment_paths)}")
                text = _transcribe_qwen_asr_single(segment_path, api_url, api_key, model)
                if text:
                    parts.append(text)
            return '\n'.join(parts).strip()
        finally:
            try:
                shutil.rmtree(segment_dir)
            except Exception:
                pass


def _transcribe_local(audio_path: str) -> str:
    """通过本地 openai-whisper 模型转写"""
    model = _get_local_whisper()
    if model is None:
        return ''

    try:
        # 如果音频文件较大（>25MB），先转换为更小的格式
        audio_to_process = audio_path
        file_size = os.path.getsize(audio_path)

        if file_size > 25 * 1024 * 1024:
            print("[STT] 音频文件较大，进行压缩...")
            compressed = _compress_audio(audio_path)
            if compressed:
                audio_to_process = compressed
            else:
                print("[STT] 音频压缩失败，尝试直接处理原始文件...")

        result = model.transcribe(
            audio_to_process,
            language='zh',
            task='transcribe',
            verbose=False,
        )
        text = result.get('text', '').strip()
        print(f"[STT] 本地模型转写完成: {len(text)} 字符")

        # 清理临时压缩文件
        if audio_to_process != audio_path and os.path.exists(audio_to_process):
            try:
                os.remove(audio_to_process)
            except Exception:
                pass

        return text
    except Exception as e:
        print(f"[STT] 本地模型转写失败: {e}")
        return ''


def _compress_audio(input_path: str) -> str:
    """将音频压缩为 16kHz 单声道 wav，减少 Whisper 处理时间"""
    try:
        import subprocess
        output_path = input_path + '.compressed.wav'
        subprocess.run(
            [
                'ffmpeg', '-y', '-i', input_path,
                '-ac', '1', '-ar', '16000',
                '-b:a', '32k',
                output_path,
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        compressed_size = os.path.getsize(output_path)
        original_size = os.path.getsize(input_path)
        print(f"[STT] 音频压缩完成: {original_size/1024/1024:.1f}MB → {compressed_size/1024/1024:.1f}MB")
        return output_path
    except FileNotFoundError:
        print("[STT] 未找到 ffmpeg，跳过音频压缩")
        return ''
    except Exception as e:
        print(f"[STT] 音频压缩失败: {e}")
        return ''
