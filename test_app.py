import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from serve import Store, create_server


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        sample = {
            "schema_version": 1,
            "updated_at": "2026-10-28",
            "jobs": [{"id": "j-1", "role": "产品运营", "url": "https://example.org/job"}],
            "fairs": [{"id": "f-1", "name": "招聘会", "date": "2026-11-01"}],
        }
        (self.directory / "data.json").write_text(json.dumps(sample), encoding="utf-8")
        self.store = Store(self.directory)
        self.server = create_server(0, self.directory)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def test_baseline_state_and_mark_persistence_after_data_refresh(self):
        with urlopen(self.url + "/api/state") as response:
            initial = json.load(response)
        self.assertEqual(initial["marks"], {"jobs": {}, "fairs": {}})
        self.assertEqual(initial["data"]["jobs"][0]["role"], "产品运营")

        payload = json.dumps({"kind": "jobs", "id": "j-1", "status": "已投", "note": "已投官网"}).encode()
        request = Request(
            self.url + "/api/mark", data=payload, method="POST",
            headers={"Content-Type": "application/json", "Origin": self.url},
        )
        with urlopen(request) as response:
            self.assertEqual(json.load(response)["saved"]["status"], "已投")

        fresh_data = initial["data"]
        fresh_data["updated_at"] = "2026-10-29"
        fresh_data["jobs"][0]["role"] = "增长运营"
        (self.directory / "data.json").write_text(json.dumps(fresh_data), encoding="utf-8")
        with urlopen(self.url + "/api/state") as response:
            refreshed = json.load(response)
        self.assertEqual(refreshed["data"]["jobs"][0]["role"], "增长运营")
        self.assertEqual(refreshed["marks"]["jobs"]["j-1"], {"status": "已投", "note": "已投官网"})

    def test_invalid_status_and_origin_rejected(self):
        for payload, origin, expected in [
            ({"kind": "jobs", "id": "j-1", "status": "伪造", "note": ""}, self.url, 400),
            ({"kind": "jobs", "id": "j-1", "status": "已投", "note": ""}, "https://example.org", 403),
        ]:
            body = json.dumps(payload).encode()
            request = Request(
                self.url + "/api/mark", data=body, method="POST",
                headers={"Content-Type": "application/json", "Origin": origin},
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, expected)
        self.assertEqual(self.store.read_marks(), {"jobs": {}, "fairs": {}})


if __name__ == "__main__":
    unittest.main()
