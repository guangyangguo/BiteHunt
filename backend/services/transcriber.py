"""
语音转文字服务 - 通过外部API或本地Whisper将音频转为文字
优先级：OpenAI Whisper API > 本地 openai-whisper 模型
"""
import os
import sys
import requests
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import get

# 本地 Whisper 模型（懒加载）
_whisper_model = None


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

    # 方案1: OpenAI Whisper API
    api_key = get('stt_api_key') or ''
    if api_key:
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
    """通过 OpenAI Whisper API 转写"""
    api_url = get('stt_api_url') or 'https://api.openai.com/v1/audio/transcriptions'
    model = get('stt_model') or 'whisper-1'

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
