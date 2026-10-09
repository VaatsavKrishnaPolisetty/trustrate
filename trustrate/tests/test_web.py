"""Native PHP/MySQL integration checks (stdlib only).

Prerequisites: PHP with pdo_mysql/curl; initialized dedicated MySQL and private
db/.local/compose.env. Run TRUSTRATE_START_WEB=1 python3 -m unittest discover
-s tests -p test_web.py -v. Or set TRUSTRATE_WEB_URL for an already running PHP
server using the same private configuration. Never points at project .env.
Creates test accounts/reviews; all SQL mutations below execute via PHP.
"""
import http.cookiejar
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class Browser:
    def __init__(self, base):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def request(self, path="/index.php", data=None):
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            response = self.opener.open(self.base + path, payload, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode()

    def csrf(self, path="/index.php"):
        status, page = self.request(path)
        assert status == 200, (status, "Cannot obtain form")
        return re.search(r'name="csrf" value="([a-f0-9]+)"', page).group(1)

    def post(self, data, path="/index.php"):
        return self.request(path, {"csrf": self.csrf(path), **data})


@unittest.skipUnless(os.environ.get("TRUSTRATE_START_WEB") == "1" or os.environ.get("TRUSTRATE_WEB_URL"), "Set TRUSTRATE_START_WEB=1 or TRUSTRATE_WEB_URL for native integration")
class WebLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = Path(os.environ.get("TRUSTRATE_TEST_CONFIG", str(ROOT / "db/.local/compose.env")))
        cls.env = os.environ.copy()
        for line in config.read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                cls.env[key] = value
        cls.server = None
        cls.base = os.environ.get("TRUSTRATE_WEB_URL", "http://127.0.0.1:18080")
        if os.environ.get("TRUSTRATE_START_WEB") == "1":
            cls.server = subprocess.Popen(["php", "-S", "127.0.0.1:18080", "-t", str(ROOT / "web")], env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cls.addClassCleanup(cls.server.wait, timeout=10)
            cls.addClassCleanup(cls.server.terminate)
            for _ in range(60):
                try:
                    Browser(cls.base).request()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("PHP server did not start")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.terminate()
            cls.server.wait(timeout=10)

    def sql(self, sql, args=()):
        env = self.env | {"TEST_SQL": sql, "TEST_ARGS": json.dumps(args)}
        result = subprocess.run(["php", "-r", 'require "web/bootstrap.php"; $s=query(getenv("TEST_SQL"),json_decode(getenv("TEST_ARGS"),true)); echo json_encode($s->columnCount()?$s->fetchAll():[]);'], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, "PHP database test helper failed")
        return json.loads(result.stdout)

    def test_complete_lifecycle_and_worker_races(self):
        alice, bob, admin, anon = [Browser(self.base) for _ in range(4)]
        self.assertEqual(anon.request("/admin.php")[0], 403)
        self.assertEqual(anon.request("/models.php")[0], 401)
        self.assertEqual(anon.request(data={"action": "register"})[0], 403)
        self.assertEqual(anon.post({"action": "create"})[0], 401)
        token = secrets.token_hex(6)
        password = secrets.token_urlsafe(24)
        for client, name in [(alice, "Alice"), (bob, "Bob")]:
            status, page = client.post({"action": "register", "name": name, "email": f"{name}-{token}@example.invalid", "password": password})
            self.assertEqual(status, 200)
            self.assertIn("Share your experience", page)
        self.assertEqual(bob.request("/admin.php")[0], 403)
        self.assertEqual(alice.request("/models.php")[0], 200)
        title = "Native lifecycle " + token
        self.sql("INSERT INTO products(slug,name,description) VALUES (?,?,?)", ["native-" + token, title, "Native integration fixture"])
        product_id = self.sql("SELECT id FROM products WHERE slug=?", ["native-" + token])[0]["id"]
        content = {"rating": 5, "title": title, "body": "A detailed test review of the headphone controls and fit."}
        self.assertEqual(alice.post({"action": "create", "product_id": product_id, **content})[0], 200)
        review = self.sql("SELECT * FROM reviews WHERE title=?", [title])[0]
        rid = review["id"]
        self.assertEqual(review["status"], "pending_score")
        self.assertEqual(review["ip_prefix"], "127.0.0.0/24")
        self.assertEqual(len(review["ip_hash"]), 64)
        self.assertNotEqual(review["ip_hash"], "127.0.0.1")
        page = alice.request("/index.php?product=" + str(product_id))[1]
        self.assertIn('Raw rating</h2><strong>5.00 / 5', page)
        self.assertIn('Genuine rating</h2><strong>— / 5', page)
        self.assertEqual(bob.post({"action": "edit", "review_id": rid, "revision": 1, **content})[0], 403)
        self.assertEqual(bob.post({"action": "delete", "review_id": rid, "revision": 1})[0], 403)
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 1, **content})[0], 200)
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 1, **content})[0], 409)
        self.assertEqual(admin.post({"action": "login", "email": self.env["ADMIN_EMAIL"], "password": self.env["ADMIN_PASSWORD"]})[0], 200)
        self.assertEqual(admin.request("/admin.php")[0], 200)
        self.assertEqual(admin.post({"action": "inject", "scenario": "A1", "product_id": 1, "reason": "Disabled demo guard"}, "/admin.php")[0], 403)
        self.assertEqual(admin.request("/admin.php", {"action": "remove", "review_id": rid, "reason": "Missing CSRF"})[0], 403)
        self.assertEqual(admin.post({"action": "remove", "review_id": rid, "revision": 1, "reason": "Stale moderation"}, "/admin.php")[0], 409)

        case = self
        behavior = {"label": "suspicious", "race": None, "mismatch": False}

        class Scorer(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                if self.headers.get("X-API-Key") != case.env["SCORING_API_KEY"]:
                    self.send_error(401)
                    return
                incoming = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if incoming["review_id"] != rid:
                    self.send_error(400)
                    return
                current = case.sql("SELECT revision FROM reviews WHERE id=?", [rid])[0]
                if behavior["race"]:
                    behavior["race"]()
                body = json.dumps({"review_id": rid + int(behavior["mismatch"]), "review_revision": current["revision"], "classical_score": .91, "quantum_score": .72, "hybrid_score": .85, "label": behavior["label"], "reasons": ["Integration fixture: coordinated metadata"], "backend": "integration-fixture", "model_version": "test-only", "ibm_job_id": None}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        scorer = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Scorer)
        thread = threading.Thread(target=scorer.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(scorer.server_close)
        self.addCleanup(scorer.shutdown)

        def work():
            self.sql("UPDATE scoring_queue SET available_at='2000-01-01',locked_until=NULL WHERE review_id=?", [rid])
            env = self.env | {"SCORING_URL": f"http://127.0.0.1:{scorer.server_port}"}
            process = subprocess.run(["php", "db/score-worker.php", "--once"], cwd=ROOT, env=env, capture_output=True, timeout=20)
            self.assertEqual(process.returncode, 0, "Worker failed")

        work()
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "flagged")
        page = alice.request("/index.php?product=" + str(product_id))[1]
        self.assertIn('Raw rating</h2><strong>5.00 / 5', page)
        self.assertIn('Genuine rating</h2><strong>— / 5', page)
        for action, expected in [("watch", "watch"), ("restore", "restored"), ("remove", "removed")]:
            self.assertEqual(admin.post({"action": action, "review_id": rid, "revision": 2, "reason": "Integration moderation check"}, "/admin.php")[0], 200)
            self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], expected)
            page = alice.request("/index.php?product=" + str(product_id))[1]
            self.assertIn('Genuine rating</h2><strong>' + ('5.00' if action == 'restore' else '—') + ' / 5', page)
        self.assertGreaterEqual(len(self.sql("SELECT * FROM admin_actions WHERE review_id=?", [rid])), 3)
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 2, **content})[0], 200)
        work()
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "removed")
        self.assertEqual(admin.post({"action": "restore", "review_id": rid, "revision": 3, "reason": "Restore before edit"}, "/admin.php")[0], 200)
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 3, **content})[0], 200)
        # The HTTP response arrives after a real moderator restore. It must not undo it.
        behavior["race"] = lambda: admin.post({"action": "restore", "review_id": rid, "revision": 4, "reason": "Restore during scoring"}, "/admin.php")
        work()
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "restored")
        behavior["race"] = None
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 4, **content})[0], 200)
        behavior["label"] = "watch"
        work()
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "published")
        self.assertIn('Genuine rating</h2><strong>5.00 / 5', alice.request("/index.php?product=" + str(product_id))[1])
        # Stale scoring after an edit must not persist or delete the new queue entry.
        self.assertEqual(alice.post({"action": "edit", "review_id": rid, "revision": 5, **content})[0], 200)
        behavior["race"] = lambda: alice.post({"action": "edit", "review_id": rid, "revision": 6, **content})
        work()
        self.assertEqual(self.sql("SELECT revision FROM scoring_queue WHERE review_id=?", [rid])[0]["revision"], 7)
        self.assertEqual(self.sql("SELECT * FROM review_scores WHERE review_id=?", [rid]), [])
        behavior["race"] = None
        behavior["mismatch"] = True
        work()
        self.assertEqual(self.sql("SELECT * FROM review_scores WHERE review_id=?", [rid]), [])
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "pending_score")
        self.assertEqual(alice.post({"action": "delete", "review_id": rid, "revision": 7})[0], 200)
        self.assertEqual(self.sql("SELECT * FROM scoring_queue WHERE review_id=?", [rid]), [])
        self.assertEqual(self.sql("SELECT status FROM reviews WHERE id=?", [rid])[0]["status"], "deleted")
        status, page = admin.post({"action": "restore", "review_id": rid, "revision": 8, "reason": "Cannot restore deletion"}, "/admin.php")
        self.assertIn("cannot be moderated", page)
        self.assertEqual(alice.post({"action": "logout"})[0], 200)
        self.assertEqual(alice.request("/models.php")[0], 401)
        self.assertEqual(alice.post({"action": "login", "email": f"Alice-{token}@example.invalid", "password": password})[0], 200)
        self.assertEqual(alice.request("/models.php")[0], 200)
        session = next(cookie.value for cookie in alice.cookies if cookie.name == "PHPSESSID")
        expired = subprocess.run(["php", "-r", 'session_id(getenv("TEST_SESSION")); session_start(); $_SESSION["last_seen"]=time()-1801; session_write_close();'], env=self.env | {"TEST_SESSION": session}, capture_output=True)
        self.assertEqual(expired.returncode, 0)
        self.assertEqual(alice.request("/models.php")[0], 401)
        # Verify the reader has no write privilege against the actual MySQL instance.
        env = self.env | {"DB_USER": self.env["DB_READONLY_USER"], "DB_PASSWORD": self.env["DB_READONLY_PASSWORD"]}
        denied = subprocess.run(["php", "-r", 'require "web/bootstrap.php"; try {query("UPDATE reviews SET rating=rating WHERE id=0"); exit(2);} catch(PDOException $e) {exit($e->errorInfo[1]===1142?0:3);}'], cwd=ROOT, env=env, capture_output=True)
        self.assertEqual(denied.returncode, 0, "Reader write privilege was not denied")

    def test_demo_attack_injection_and_audit(self):
        server = subprocess.Popen(["php", "-S", "127.0.0.1:18081", "-t", str(ROOT / "web")], env=self.env | {"DEMO_MODE": "1"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: server.wait(timeout=10))
        self.addCleanup(server.terminate)
        client = Browser("http://127.0.0.1:18081")
        for _ in range(60):
            try:
                client.request()
                break
            except OSError:
                time.sleep(.1)
        self.assertEqual(client.request("/admin.php")[0], 403)
        test_admin = "native-admin-" + secrets.token_hex(8) + "@example.invalid"
        # A separate fixture administrator keeps repeated test runs inside the
        # real per-administrator demo rate limit, without disabling that limit.
        self.sql("INSERT INTO users(email,name,password_hash,role) SELECT ?,?,password_hash,'admin' FROM users WHERE email=?", [test_admin, "Native injection test", self.env["ADMIN_EMAIL"]])
        self.addCleanup(self.sql, "UPDATE users SET role='user' WHERE email=?", [test_admin])
        self.assertEqual(client.post({"action": "login", "email": test_admin, "password": self.env["ADMIN_PASSWORD"]})[0], 200)
        self.assertEqual(client.request("/admin.php", {"action": "inject", "scenario": "A1", "product_id": 1, "reason": "Missing CSRF"})[0], 403)
        reason = "Attack integration " + secrets.token_hex(8)
        for scenario in ["A1", "A2", "A3", "A4"]:
            self.assertEqual(client.post({"action": "inject", "scenario": scenario, "product_id": 1, "reason": reason}, "/admin.php")[0], 200)
        rows = self.sql("SELECT r.* FROM reviews r JOIN admin_actions a ON a.review_id=r.id WHERE a.reason=?", [reason])
        self.assertEqual(len(rows), 112)
        self.assertTrue(all(r["status"] == "pending_score" and r["is_synthetic"] == 1 for r in rows))
        self.assertEqual(len({r["user_id"] for r in rows if r["scenario"] == "A4"}), 24)
        self.assertEqual(len({r["ip_hash"] for r in rows if r["scenario"] == "A1"}), 5)
        self.assertEqual(len({r["ip_hash"] for r in rows if r["scenario"] == "A2"}), 3)
        self.assertEqual({r["rating"] for r in rows if r["scenario"] == "A2"}, {1})
        self.assertEqual({r["rating"] for r in rows if r["scenario"] == "A3"}, {5})
        self.assertIn("Related metadata and account history", client.request("/admin.php?review=" + str(rows[0]["id"]))[1])
        for row in rows:
            self.sql("UPDATE reviews SET status='deleted',revision=revision+1 WHERE id=?", [row["id"]])
            self.sql("DELETE FROM scoring_queue WHERE review_id=?", [row["id"]])


if __name__ == "__main__":
    unittest.main()
