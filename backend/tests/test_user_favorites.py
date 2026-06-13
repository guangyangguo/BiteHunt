import os
import shutil
import sys
import tempfile
import unittest

os.environ["DATABASE_URL"] = ""

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
from app import app


class UserFavoriteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        database.DB_PATH = os.path.join(self.tmpdir, "test.db")
        database.DATABASE_URL = ""
        database.init_db()
        self.client = app.test_client()

        self.blogger_id = database.add_blogger("收藏博主", "uid-fav")
        database.add_videos_batch(self.blogger_id, [{
            "platform_video_id": "BVFAV000001",
            "title": "收藏测试视频",
        }])
        self.video_id = database.get_videos()[0]["id"]
        self.store_id = database.add_store({
            "name": "收藏测试店",
            "category": "小吃",
            "source_video_id": self.video_id,
            "source_blogger_id": self.blogger_id,
        })

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def login_headers(self):
        response = self.client.post(
            "/api/user/login",
            json={"provider": "wechat", "code": "fav-code", "device_id": "fav-device"},
        )
        token = response.get_json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_favorite_requires_login(self):
        response = self.client.post(f"/api/stores/{self.store_id}/favorite")
        body = response.get_json()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(body["code"], -1)

    def test_favorite_cancel_and_profile_count(self):
        headers = self.login_headers()

        favorite = self.client.post(f"/api/stores/{self.store_id}/favorite", headers=headers)
        self.assertEqual(favorite.status_code, 200)
        self.assertTrue(favorite.get_json()["data"]["is_favorited"])

        profile = self.client.get("/api/user/profile", headers=headers).get_json()["data"]
        self.assertEqual(profile["stats"]["favorites"], 1)

        stores = self.client.get("/api/stores", headers=headers).get_json()["data"]
        self.assertTrue(stores[0]["is_favorited"])

        favorites = self.client.get("/api/user/favorites", headers=headers).get_json()["data"]
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]["id"], self.store_id)

        cancel = self.client.delete(f"/api/stores/{self.store_id}/favorite", headers=headers)
        self.assertEqual(cancel.status_code, 200)
        self.assertFalse(cancel.get_json()["data"]["is_favorited"])

        profile = self.client.get("/api/user/profile", headers=headers).get_json()["data"]
        self.assertEqual(profile["stats"]["favorites"], 0)


if __name__ == "__main__":
    unittest.main()
