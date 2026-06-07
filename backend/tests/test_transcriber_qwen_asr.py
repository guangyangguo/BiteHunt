import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import transcriber


class QwenAsrTranscriberTests(unittest.TestCase):
    def test_transcribe_audio_skips_remote_api_when_disabled(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as audio:
            audio.write(b"fake-audio")
            audio_path = audio.name

        def fake_get(key, default=None):
            values = {
                "stt_use_remote_api": "false",
                "stt_api_key": "test-key",
            }
            return values.get(key, default)

        try:
            with patch.object(transcriber, "get", side_effect=fake_get), \
                 patch.object(transcriber, "_transcribe_via_api") as remote_api, \
                 patch.object(transcriber, "_transcribe_local", return_value="local text") as local_asr:
                text = transcriber.transcribe_audio(audio_path)

            self.assertEqual(text, "local text")
            remote_api.assert_not_called()
            local_asr.assert_called_once_with(audio_path)
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def test_qwen_asr_posts_input_audio_data_url_and_returns_text(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as audio:
            audio.write(b"fake-audio")
            audio_path = audio.name

        try:
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"text": "hello from qwen"})
                        }
                    }
                ]
            }

            with patch.object(transcriber.requests, "post", return_value=response) as post:
                text = transcriber._transcribe_via_qwen_asr(
                    audio_path,
                    api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    api_key="test-key",
                    model="qwen3-asr-flash",
                )

            self.assertEqual(text, "hello from qwen")
            kwargs = post.call_args.kwargs
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
            payload = kwargs["json"]
            self.assertEqual(payload["model"], "qwen3-asr-flash")
            audio_url = payload["messages"][0]["content"][0]["input_audio"]["data"]
            expected = base64.b64encode(b"fake-audio").decode("ascii")
            self.assertEqual(audio_url, f"data:audio/mp4;base64,{expected}")
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def test_qwen_asr_splits_long_audio_and_joins_segment_text(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as audio:
            audio.write(b"fake-audio")
            audio_path = audio.name

        segment_paths = ["segment-001.m4a", "segment-002.m4a"]

        try:
            with patch.object(transcriber, "_get_audio_duration_seconds", return_value=601), \
                 patch.object(transcriber, "_split_audio_for_qwen", return_value=segment_paths) as split_audio, \
                 patch.object(transcriber, "_transcribe_qwen_asr_single", side_effect=["第一段", "第二段"]) as transcribe_one, \
                 patch.object(transcriber.shutil, "rmtree") as rmtree:
                text = transcriber._transcribe_via_qwen_asr(
                    audio_path,
                    api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    api_key="test-key",
                    model="qwen3-asr-flash",
                )

            self.assertEqual(text, "第一段\n第二段")
            split_audio.assert_called_once_with(audio_path)
            self.assertEqual(transcribe_one.call_count, 2)
            rmtree.assert_called_once()
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def test_qwen_asr_splits_when_api_reports_audio_too_long(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as audio:
            audio.write(b"fake-audio")
            audio_path = audio.name

        segment_dir = tempfile.TemporaryDirectory()
        segment_one = Path(segment_dir.name) / "segment-001.m4a"
        segment_two = Path(segment_dir.name) / "segment-002.m4a"
        segment_one.write_bytes(b"segment-one")
        segment_two.write_bytes(b"segment-two")

        too_long_response = Mock()
        too_long_response.status_code = 400
        too_long_response.text = '{"error":{"message":"The audio is too long"}}'

        first_response = Mock()
        first_response.status_code = 200
        first_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"text": "part one"})}}]
        }

        second_response = Mock()
        second_response.status_code = 200
        second_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"text": "part two"})}}]
        }

        try:
            with patch.object(transcriber, "_get_audio_duration_seconds", return_value=None), \
                 patch.object(transcriber, "_split_audio_for_qwen", return_value=[str(segment_one), str(segment_two)]) as split_audio, \
                 patch.object(transcriber.requests, "post", side_effect=[too_long_response, first_response, second_response]):
                text = transcriber._transcribe_via_qwen_asr(
                    audio_path,
                    api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    api_key="test-key",
                    model="qwen3-asr-flash",
                )

            self.assertEqual(text, "part one\npart two")
            split_audio.assert_called_once_with(audio_path)
        finally:
            Path(audio_path).unlink(missing_ok=True)
            segment_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
