"""Opt-in HTTP/MySQL demo boundaries. Own servers/products only; never resets live products.

TRUSTRATE_TEST_DEMO=1 python3 -m unittest discover -s tests -p test_demo.py -v
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import unittest
from test_web import Browser

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TRUSTRATE_TEST_DEMO') == '1', 'Opt in with TRUSTRATE_TEST_DEMO=1')
class DemoBoundaries(unittest.TestCase):
    def sql(self, statement, args=()):
        run = subprocess.run(['php', '-r', 'require "web/bootstrap.php"; $s=query(getenv("TEST_SQL"),json_decode(getenv("TEST_ARGS"),true)); echo json_encode($s->columnCount()?$s->fetchAll():[]);'], cwd=ROOT, env=self.env | {'TEST_SQL': statement, 'TEST_ARGS': json.dumps(args)}, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, 'Database helper failed')
        return json.loads(run.stdout)

    def server(self, demo):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        server = subprocess.Popen(['php', '-S', f'127.0.0.1:{port}', '-t', str(ROOT / 'web')], env=self.env | {'DEMO_MODE': demo}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: server.wait(timeout=10))
        self.addCleanup(server.terminate)
        browser = Browser(f'http://127.0.0.1:{port}')
        for _ in range(60):
            if server.poll() is not None:
                self.fail('Dedicated PHP test server exited')
            try:
                browser.request()
                return browser
            except OSError:
                time.sleep(.1)
        self.fail('Dedicated PHP test server did not start')

    def setUp(self):
        self.env = os.environ.copy()
        for line in (ROOT / 'db/.local/compose.env').read_text().splitlines():
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                self.env[key] = value
        self.token = secrets.token_hex(8)
        self.password = secrets.token_urlsafe(24)
        self.admin = self.server('1')
        self.email = f'demo-test-{self.token}@example.invalid'
        self.assertEqual(self.admin.post({'action': 'register', 'email': self.email, 'name': 'Isolated demo test', 'password': self.password})[0], 200)
        self.assertEqual(self.admin.request('/admin.php')[0], 403)
        self.assertEqual(self.admin.request('/admin.php', {'csrf': self.admin.csrf(), 'action': 'reset_demo', 'product_id': 1, 'reason': 'non-admin guard'})[0], 403)
        self.sql("UPDATE users SET role='admin' WHERE email=?", [self.email])
        self.uid = self.sql('SELECT id FROM users WHERE email=?', [self.email])[0]['id']
        self.addCleanup(self.sql, "UPDATE users SET role='user' WHERE id=?", [self.uid])
        self.sql('INSERT INTO products(slug,name,description) VALUES (?,?,?)', ['native-demo-' + self.token, 'Isolated demo test', 'HTTP reset boundaries'])
        self.pid = self.sql('SELECT id FROM products WHERE slug=?', ['native-demo-' + self.token])[0]['id']

    def test_real_http_scenarios_and_reset_boundary(self):
        # Known scored rows are stable even if a real worker scores other pending rows.
        original = self.sql("SELECT r.id,r.revision,r.status,s.* FROM reviews r JOIN review_scores s ON s.review_id=r.id WHERE r.source_id IS NOT NULL AND r.split<>'demo' ORDER BY r.id LIMIT 10")
        self.assertEqual(self.admin.request('/admin.php', {'action': 'reset_demo', 'product_id': self.pid, 'reason': 'missing CSRF'})[0], 403)
        disabled = self.server('0')
        self.assertEqual(disabled.post({'action': 'login', 'email': self.email, 'password': self.password})[0], 200)
        for action in ['inject', 'reset_demo']:
            self.assertEqual(disabled.post({'action': action, 'scenario': 'A1', 'product_id': self.pid, 'reason': 'disabled guard'}, '/admin.php')[0], 403)

        # Retained fixtures cover imported data, ordinary users, and a demo marker
        # with no button-injection audit provenance.
        boundaries = []
        for kind, synthetic, split, source in [('dataset', 1, 'test', self.token), ('user', 0, None, None), ('not-button', 1, 'demo', None)]:
            self.sql("INSERT INTO reviews(product_id,user_id,rating,title,body,status,ip_hash,is_synthetic,split,source_id) VALUES (?,?,4,?,?,'published',REPEAT('a',64),?,?,?)", [self.pid, self.uid, kind + self.token, 'Boundary fixture review text for reset isolation.', synthetic, split, source])
            rid = self.sql('SELECT id FROM reviews WHERE title=?', [kind + self.token])[0]['id']
            self.sql("INSERT INTO review_scores(review_id,review_revision,classical_score,quantum_score,hybrid_score,label,reasons,backend,model_version) VALUES (?,1,0.1,0.2,0.15,'genuine','[]','test-fixture','boundary-only')", [rid])
            self.sql("INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,'watch','published',?)", [self.uid, rid, 'Retain audit ' + self.token])
            boundaries.append(rid)
        before = self.sql('SELECT r.*,s.hybrid_score,s.model_version FROM reviews r JOIN review_scores s ON s.review_id=r.id WHERE r.product_id=? ORDER BY r.id', [self.pid])
        for scenario in ['A1', 'A2', 'A3', 'A4', 'N1', 'N2']:
            status, page = self.admin.post({'action': 'inject', 'scenario': scenario, 'product_id': self.pid, 'reason': self.token}, '/admin.php')
            self.assertEqual(status, 200)
            self.assertNotIn('role="alert"', page)
        rows = self.sql("SELECT r.*,u.created_at account_created FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.product_id=? AND r.title LIKE 'Synthetic %' ORDER BY r.id", [self.pid])
        self.assertEqual(len(rows), 160)
        self.assertTrue(all(r['is_synthetic'] == 1 and r['split'] == 'demo' and r['source_id'] is None for r in rows))
        self.assertTrue(all(r['account_created'] < r['created_at'] for r in rows))
        grouped = {s: [r for r in rows if r['scenario'] == s] for s in ['A1', 'A2', 'A3', 'A4', 'N1', 'N2']}
        self.assertEqual(len(grouped['A1']), 40)
        self.assertEqual(len({r['ip_hash'] for r in grouped['A1']}), 5)
        self.assertEqual({r['rating'] for r in grouped['A2']}, {1})
        self.assertEqual(len({r['ip_hash'] for r in grouped['A2']}), 3)
        self.assertEqual(len({r['user_id'] for r in grouped['A4']}), 24)
        self.assertEqual(len({r['ip_prefix'] for r in grouped['A4']}), 1)
        self.assertEqual(len({r['ip_hash'] for r in grouped['A3']}), 24)
        self.assertGreater(len({r['created_at'][:10] for r in grouped['A3']}), 10)
        for scenario in ['N1', 'N2']:
            self.assertEqual({r['true_label'] for r in grouped[scenario]}, {'0'})
            self.assertEqual(len({r['body'] for r in grouped[scenario]}), 24)
        detail = self.admin.request('/admin.php?review=' + str(rows[0]['id']))[1]
        self.assertIn('Related metadata and account history', detail)
        self.assertIn('text overlap', detail)
        self.assertIn('not detector attribution', detail)
        public = self.admin.request('/index.php?product=' + str(self.pid))[1]
        for marker in ['Raw rating', 'Genuine rating', 'Scored', 'Pending', 'Flagged', 'Clear filters']:
            self.assertIn(marker, public)
        # Scores and queue entries both exist for the reset target; these values
        # are test-only fixtures, never displayed as actual model results.
        self.sql("INSERT IGNORE INTO review_scores(review_id,review_revision,classical_score,quantum_score,hybrid_score,label,reasons,backend,model_version) VALUES (?,1,0.1,0.2,0.15,'genuine','[]','test-fixture','reset-only')", [rows[0]['id']])
        status, page = self.admin.post({'action': 'reset_demo', 'product_id': self.pid, 'reason': self.token}, '/admin.php')
        self.assertEqual(status, 200)
        self.assertNotIn('role="alert"', page)
        reset = self.sql("SELECT r.*,s.review_id score_id,q.review_id queue_id FROM reviews r LEFT JOIN review_scores s ON s.review_id=r.id LEFT JOIN scoring_queue q ON q.review_id=r.id WHERE r.product_id=? AND r.title LIKE 'Synthetic %'", [self.pid])
        self.assertTrue(all(r['status'] == 'deleted' and r['revision'] == 2 and r['score_id'] is None and r['queue_id'] is None for r in reset))
        self.assertEqual(self.sql('SELECT r.*,s.hybrid_score,s.model_version FROM reviews r JOIN review_scores s ON s.review_id=r.id WHERE r.product_id=? ORDER BY r.id', [self.pid]), before)
        audit = self.sql('SELECT action,reason FROM admin_actions WHERE admin_id=?', [self.uid])
        self.assertEqual(sum(a['action'] == 'inject' for a in audit), 160)
        self.assertEqual(sum(a['reason'].startswith('DEMO RESET:') for a in audit), 160)
        self.assertEqual(sum(a['reason'].startswith('Retain audit') for a in audit), 3)
        if original:
            ids = ','.join(str(r['id']) for r in original)
            self.assertEqual(self.sql(f'SELECT r.id,r.revision,r.status,s.* FROM reviews r JOIN review_scores s ON s.review_id=r.id WHERE r.id IN ({ids}) ORDER BY r.id'), original)
        # Repeating reset is harmless and cannot resurrect/revise deleted rows.
        again = self.admin.post({'action': 'reset_demo', 'product_id': self.pid, 'reason': self.token}, '/admin.php')[1]
        self.assertIn('Nothing was changed', again)
        self.assertEqual(len(self.sql("SELECT id FROM admin_actions WHERE admin_id=? AND reason LIKE 'DEMO RESET:%'", [self.uid])), 160)


if __name__ == '__main__':
    unittest.main()
