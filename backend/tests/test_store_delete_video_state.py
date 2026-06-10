import os
import shutil
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

import database


class StoreDeleteVideoStateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tmpdir, "test.db")
        database.init_db()
        self.blogger_id = database.add_blogger("测试博主", "uid-delete-store")
        database.add_videos_batch(self.blogger_id, [{
            "platform_video_id": "BVDELETE0001",
            "title": "测试探店视频",
        }])
        self.video_id = database.get_videos()[0]["id"]
        database.update_video_status(self.video_id, "analyzed")

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_delete_last_store_marks_video_no_store(self):
        store_id = database.add_store({
            "name": "测试店铺",
            "source_video_id": self.video_id,
            "source_blogger_id": self.blogger_id,
        })

        result = database.delete_store(store_id)
        video = database.get_video(self.video_id)
        listed = database.get_videos()[0]

        self.assertEqual(result["source_video_id"], self.video_id)
        self.assertEqual(result["active_store_count"], 0)
        self.assertEqual(video["status"], "no_store")
        self.assertEqual(listed["active_store_count"], 0)


if __name__ == "__main__":
    unittest.main()
