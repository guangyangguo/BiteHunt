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


class UserAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = database.DB_PATH
        self.original_database_url = database.DATABASE_URL
        database.DB_PATH = os.path.join(self.tmpdir, "test.db")
        database.DATABASE_URL = ""
        database.init_db()
        self.client = app.test_client()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        database.DATABASE_URL = self.original_database_url
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_profile_is_logged_out_without_token(self):
        response = self.client.get("/api/user/profile")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["code"], 0)
        self.assertFalse(body["data"]["is_logged_in"])

    def test_login_profile_and_logout_with_token(self):
        login_response = self.client.post(
            "/api/user/login",
            json={"provider": "wechat", "code": "wx-code", "device_id": "device-1"},
        )
        login_body = login_response.get_json()

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_body["code"], 0)
        self.assertTrue(login_body["data"]["is_logged_in"])
        token = login_body["data"]["token"]
        self.assertTrue(token)

        profile_response = self.client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        profile = profile_response.get_json()["data"]
        self.assertTrue(profile["is_logged_in"])
        self.assertEqual(profile["nickname"], "探店用户")

        logout_response = self.client.post(
            "/api/user/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_response.status_code, 200)

        logged_out = self.client.get(
            "/api/user/profile",
            headers={"Authorization": f"Bearer {token}"},
        ).get_json()["data"]
        self.assertFalse(logged_out["is_logged_in"])


if __name__ == "__main__":
    unittest.main()
