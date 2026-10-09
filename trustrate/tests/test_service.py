"""Opt-in checks of the actual running PHP -> MySQL -> Aer -> PHP worker.

TRUSTRATE_LIVE=1 .venv/bin/python -m unittest discover -s tests -p test_service.py -v
Creates one account/review using HTTP; deletes the review through its owner.
Secrets are read only from the ignored local config and never printed.
"""
import os
import re
import secrets
import time
import unittest
import requests

from service.app.main import connect, snapshot, API_KEY, LOCAL, MODEL_PATH
from pipeline.models import TrustRateModel

WEB = "http://127.0.0.1:8080"
API = "http://127.0.0.1:8001"

def rows(sql, args=()):
    with connect() as c:
        with c.cursor() as s:
            s.execute(sql,args or None)
            return s.fetchall()

def csrf(session, path="/index.php"):
    page=session.get(WEB+path,timeout=20)
    page.raise_for_status()
    return re.search(r'name="csrf" value="([a-f0-9]+)"',page.text).group(1)

@unittest.skipUnless(os.getenv("TRUSTRATE_LIVE")=="1", "Requires local servers and real model")
class RealServiceTests(unittest.TestCase):
    def test_auth_errors_and_saved_model_inference(self):
        self.assertEqual(requests.get(API+"/health",timeout=10).json()["status"],"ready")
        self.assertEqual(requests.post(API+"/v1/score",json={"review_id":1},timeout=10).status_code,401)
        headers={"X-API-Key":API_KEY}
        self.assertEqual(requests.post(API+"/v1/score",json={"review_id":-1},headers=headers,timeout=10).status_code,422)
        self.assertEqual(requests.post(API+"/v1/score",json={"review_id":999999999},headers=headers,timeout=10).status_code,404)
        # No unauthenticated memory-review route or fake hardware queue remains.
        self.assertEqual(requests.post(API+"/v1/quantum/hardware-run",timeout=10).status_code,404)
        ids=[r["id"] for r in rows("SELECT id FROM reviews WHERE source_id IS NOT NULL AND status<>'deleted' ORDER BY id LIMIT 2")]
        batch=requests.post(API+"/v1/score/batch",json={"review_ids":ids},headers=headers,timeout=90)
        self.assertEqual(batch.status_code,200)
        model=TrustRateModel.load(MODEL_PATH)
        selected,history=snapshot(ids)
        for review,result in zip(selected,batch.json()["results"]):
            expected=model.score_review(review,history)
            self.assertAlmostEqual(result["hybrid_score"],expected["scores"]["hybrid"],places=10)
            single=requests.post(API+"/v1/score",json={"review_id":review["id"]},headers=headers,timeout=60).json()
            self.assertAlmostEqual(single["quantum_score"],result["quantum_score"],places=10)
            self.assertEqual(single["model_version"],model.model_version)
            self.assertEqual(single["backend"],"aer_simulator")

    def test_submit_persist_score_moderate_edit_delete(self):
        owner=requests.Session(); admin=requests.Session()
        tag=secrets.token_hex(8); password=secrets.token_urlsafe(24)
        response=owner.post(WEB+"/index.php",data={"csrf":csrf(owner),"action":"register","name":"Integration test", "email":f"live-{tag}@example.invalid","password":password},timeout=20)
        self.assertEqual(response.status_code,200)
        self.assertIn("Share your experience",response.text)
        product=rows("SELECT id FROM products WHERE slug LIKE 'dataset-%' ORDER BY id LIMIT 1")[0]["id"]
        title="Live Aer integration "+tag
        content={"product_id":product,"rating":4,"title":title,"body":"These headphones have clear speech and a comfortable fit on long calls."}
        response=owner.post(WEB+"/index.php",data={"csrf":csrf(owner),"action":"create",**content},timeout=20)
        self.assertEqual(response.status_code,200)
        review=rows("SELECT * FROM reviews WHERE title=%s",(title,))[0]; rid=review["id"]
        try:
            # Await the actual background worker, not a fabricated test score.
            result=[]
            for _ in range(180):
                result=rows("SELECT * FROM review_scores WHERE review_id=%s",(rid,))
                if result: break
                time.sleep(1)
            self.assertTrue(result,"Real PHP worker did not persist a score within 180s")
            self.assertEqual(result[0]["backend"],"aer_simulator")
            self.assertTrue(result[0]["model_version"].startswith("trustrate-uci-v2-"))
            self.assertNotEqual(rows("SELECT status FROM reviews WHERE id=%s",(rid,))[0]["status"],"pending_score")
            self.assertEqual(admin.post(WEB+"/index.php",data={"csrf":csrf(admin),"action":"login","email":LOCAL["ADMIN_EMAIL"],"password":LOCAL["ADMIN_PASSWORD"]},timeout=20).status_code,200)
            for action,state in [("remove","removed"),("restore","restored")]:
                rev=rows("SELECT revision FROM reviews WHERE id=%s",(rid,))[0]["revision"]
                response=admin.post(WEB+"/admin.php",data={"csrf":csrf(admin,"/admin.php"),"action":action,"review_id":rid,"revision":rev,"reason":"Automated real-service integration verification"},timeout=20)
                self.assertEqual(response.status_code,200)
                self.assertEqual(rows("SELECT status FROM reviews WHERE id=%s",(rid,))[0]["status"],state)
            audit=admin.get(WEB+f"/admin.php?review={rid}",timeout=20).text
            self.assertIn(f"remove review #{rid}",audit)
            self.assertIn(f"restore review #{rid}",audit)
            evidence=admin.get(WEB+"/models.php",timeout=20)
            self.assertIn("Detection benchmark",evidence.text)
            self.assertIn("IBM QUANTUM",evidence.text)
            rev=rows("SELECT revision FROM reviews WHERE id=%s",(rid,))[0]["revision"]
            response=owner.post(WEB+"/index.php",data={"csrf":csrf(owner),"action":"edit","review_id":rid,"revision":rev,**content,"body":content["body"]+" Updated after another week."},timeout=20)
            self.assertEqual(response.status_code,200)
            self.assertGreater(rows("SELECT revision FROM reviews WHERE id=%s",(rid,))[0]["revision"],rev)
        finally:
            rev=rows("SELECT revision FROM reviews WHERE id=%s",(rid,))[0]["revision"]
            response=owner.post(WEB+"/index.php",data={"csrf":csrf(owner),"action":"delete","review_id":rid,"revision":rev},timeout=20)
            self.assertEqual(response.status_code,200)
            self.assertEqual(rows("SELECT status FROM reviews WHERE id=%s",(rid,))[0]["status"],"deleted")

if __name__=="__main__": unittest.main()
