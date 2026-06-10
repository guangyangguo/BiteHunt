import os
import shutil
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

import database


class VideoPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tmpdir, "test.db")
        database.init_db()
        self.blogger_id = database.add_blogger("分页博主", "uid-pagination")
        database.add_videos_batch(self.blogger_id, [
            {
                "platform_video_id": f"BVPG{i:010d}",
                "title": f"分页视频 {i}",
                "publish_date": f"2026-01-{(i % 28) + 1:02d}",
            }
            for i in range(65)
        ])

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_count_and_second_page(self):
        self.assertEqual(database.count_videos(), 65)
        first_page = database.get_videos(limit=50, offset=0)
        second_page = database.get_videos(limit=50, offset=50)
        self.assertEqual(len(first_page), 50)
        self.assertEqual(len(second_page), 15)

    def test_keyword_search(self):
        by_title = database.get_videos(keyword="分页视频 64", limit=50)
        by_bv = database.get_videos(keyword="BVPG0000000064", limit=50)
        by_blogger = database.get_videos(keyword="分页博主", limit=100)

        self.assertEqual(len(by_title), 1)
        self.assertEqual(by_title[0]["platform_video_id"], "BVPG0000000064")
        self.assertEqual(len(by_bv), 1)
        self.assertEqual(database.count_videos(keyword="分页视频"), 65)
        self.assertEqual(len(by_blogger), 65)


if __name__ == "__main__":
    unittest.main()
