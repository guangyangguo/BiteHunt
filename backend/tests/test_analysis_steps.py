import os
import shutil
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

import database


class AnalysisStepTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        database.DATABASE_URL = ""
        database.DB_PATH = os.path.join(self.tmpdir, "test.db")
        database.init_db()
        blogger_id = database.add_blogger("测试博主", "uid-test")
        database.add_videos_batch(blogger_id, [
            {
                "platform_video_id": "BVTEST000001",
                "title": "测试视频",
            }
        ])

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_record_complete_and_query_steps(self):
        run_id = "test-run"
        step_id = database.start_analysis_step(
            video_id=1,
            run_id=run_id,
            step_name="调用大模型",
            input_summary="prompt 1000 chars",
            metadata={"model": "test-model"},
        )

        database.finish_analysis_step(
            step_id,
            status="success",
            output_summary="stores=2",
            metadata={"prompt_tokens": 10},
        )

        steps = database.get_analysis_steps(video_id=1)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["step_name"], "调用大模型")
        self.assertEqual(steps[0]["status"], "success")
        self.assertEqual(steps[0]["input_summary"], "prompt 1000 chars")
        self.assertEqual(steps[0]["output_summary"], "stores=2")
        self.assertGreaterEqual(steps[0]["duration_ms"], 0)
        self.assertIn("prompt_tokens", steps[0]["metadata_json"])

    def test_attach_steps_to_analysis_log(self):
        run_id = "attach-run"
        database.start_analysis_step(1, run_id, "解析 JSON")
        log_id = database.add_analysis_log(
            video_id=1,
            model_name="model",
            raw_response="{}",
            extracted_data={},
            store_ids=[],
            success=True,
        )

        database.attach_analysis_steps_to_log(run_id, log_id)
        steps = database.get_analysis_steps(video_id=1, analysis_log_id=log_id)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["analysis_log_id"], log_id)


if __name__ == "__main__":
    unittest.main()
