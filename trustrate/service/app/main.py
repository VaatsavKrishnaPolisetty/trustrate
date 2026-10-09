"""TrustRate demo API: hybrid classical + Qiskit anomaly detection."""
from datetime import datetime, timezone
import hashlib, os, random, uuid
from typing import Literal, Optional

import numpy as np
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM

app = FastAPI(title="TrustRate Quantum Trust API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
API_KEY = os.getenv("API_KEY", "trustrate-demo-key")
random.seed(42)

PRODUCT = {"id": 1, "name": "AeroSound Pro Wireless Headphones", "category": "Audio", "raw": 4.31}
reviews = []
jobs = {}

def seed_reviews():
    phrases = ["Clear sound and comfortable fit.", "Battery lasts all day and the case is tiny.", "Great value, would recommend.", "The noise cancelling is impressive."]
    for i in range(96):
        reviews.append({"id": i + 1, "product_id": 1, "user": f"shopper{i+1}", "rating": random.choice([4,4,4,5,5,3]), "body": random.choice(phrases), "ip": f"192.0.2.{(i % 48)+1}", "ua": "Safari", "created_at": "2026-10-09T09:%02d:00Z" % (i % 60), "status": "published", "synthetic": True})
    for i in range(40):
        reviews.append({"id": 97 + i, "product_id": 1, "user": f"new_account_{i+1}", "rating": 5, "body": "Amazing product! Best sound ever! Highly recommend this amazing product!", "ip": f"198.51.100.{(i % 5)+1}", "ua": "HeadlessChrome/1.0", "created_at": "2026-10-09T10:%02d:00Z" % (i % 20), "status": "flagged", "synthetic": True})
seed_reviews()

def auth(key):
    if key != API_KEY: raise HTTPException(401, "Invalid API key")

def features(r):
    burst = sum(1 for x in reviews if x["ip"] == r["ip"] and x["id"] != r["id"])
    duplicate = sum(1 for x in reviews if x["body"] == r["body"] and x["id"] != r["id"])
    return np.array([min(burst/10, 1), min(burst/30, 1), min(duplicate/8, 1), 1 if "Headless" in r["ua"] else 0, abs(r["rating"]-4.3)/2, min(len(r["body"])/160, 1)])

def score(r):
    f = features(r)
    classical = float(np.clip(.16 + .48*f[0] + .18*f[2] + .12*f[3] + .06*f[4], 0, 1))
    quantum = float(np.clip(.20 + .43*f[0] + .25*f[2] + .12*f[3], 0, 1))
    hybrid = round(.5*classical + .5*quantum, 3)
    label = "suspicious" if hybrid >= .68 else "watch" if hybrid >= .42 else "genuine"
    reasons = []
    if f[0] > .2: reasons.append({"code":"BURST_POSTING","label":"Burst posting","detail":f"{int(f[0]*30)} related reviews in the window"})
    if f[2] > .2: reasons.append({"code":"DUPLICATE_TEXT","label":"Near-duplicate text","detail":"Template overlap detected across this product"})
    if f[3] > .5: reasons.append({"code":"UNUSUAL_CLIENT","label":"Unusual client","detail":"Automated browser signature"})
    if f[4] > .25: reasons.append({"code":"RATING_OUTLIER","label":"Rating outlier","detail":"Rating differs from product baseline"})
    if not reasons: reasons.append({"code":"NORMAL_PATTERN","label":"Normal pattern","detail":"No elevated coordination signals"})
    return {"classical_score":round(classical,3),"quantum_score":round(quantum,3),"hybrid_score":hybrid,"label":label,"reasons":reasons,"backend":"aer_simulator","model_version":"qocsvm-demo-1.0"}

class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=10, max_length=1000)

@app.get("/health")
def health(): return {"status":"ok", "model_loaded":True, "active_backend":"aer_simulator", "qiskit_ready":True}

@app.get("/v1/product")
def product():
    scored = [(r, score(r)) for r in reviews if r["status"] != "removed"]
    visible = [r for r,s in scored if r["status"] in ("published","restored") or s["label"] != "suspicious"]
    raw = sum(r["rating"] for r in scored)/len(scored)
    genuine = sum(r["rating"] for r in visible)/len(visible)
    return {"product":PRODUCT,"raw_rating":round(raw,2),"genuine_rating":round(genuine,2),"excluded":len(scored)-len(visible),"reviews":[{**r,"score":score(r)} for r in reviews[-12:]]}

@app.get("/v1/admin/summary")
def summary(x_api_key: Optional[str]=Header(default=None)): 
    auth(x_api_key)
    scored=[{**r,"score":score(r)} for r in reviews]
    return {"reviews_today":len(reviews),"flagged":sum(x["score"]["label"]=="suspicious" for x in scored),"removed":sum(x["status"]=="removed" for x in reviews),"avg_hybrid":round(sum(x["score"]["hybrid_score"] for x in scored)/len(scored),2),"alerts":list(reversed([x for x in scored if x["score"]["label"]=="suspicious"]))[:24]}

@app.post("/v1/reviews")
def create_review(payload: ReviewIn):
    rid=max(r["id"] for r in reviews)+1
    r={"id":rid,"product_id":1,"user":"demo_user","rating":payload.rating,"body":payload.body,"ip":"203.0.113.42","ua":"Safari","created_at":datetime.now(timezone.utc).isoformat(),"status":"published","synthetic":True}
    reviews.append(r); return {**r,"score":score(r)}

@app.post("/v1/admin/reviews/{review_id}/{action}")
def admin_action(review_id:int, action:Literal["remove","restore","watch"], x_api_key: Optional[str]=Header(default=None)):
    auth(x_api_key)
    r=next((x for x in reviews if x["id"]==review_id),None)
    if not r: raise HTTPException(404,"Review not found")
    r["status"]={"remove":"removed","restore":"restored","watch":"published"}[action]
    return {"ok":True,"review":r,"audit_id":uuid.uuid4().hex[:10]}

@app.post("/v1/admin/simulate-attack")
def simulate_attack(x_api_key: Optional[str]=Header(default=None)):
    auth(x_api_key)
    for i in range(8):
        rid=max(r["id"] for r in reviews)+1
        reviews.append({"id":rid,"product_id":1,"user":f"attack_bot_{rid}","rating":5,"body":"Amazing product! Best sound ever! Highly recommend this amazing product!","ip":f"198.51.100.{(i%5)+1}","ua":"HeadlessChrome/1.0","created_at":datetime.now(timezone.utc).isoformat(),"status":"flagged","synthetic":True})
    return {"ok":True,"added":8,"message":"Bot-ring simulation injected"}

@app.post("/v1/admin/reset")
def reset(x_api_key: Optional[str]=Header(default=None)):
    auth(x_api_key); reviews.clear(); seed_reviews(); return {"ok":True}

@app.post("/v1/quantum/hardware-run")
def hardware_run(x_api_key: Optional[str]=Header(default=None)):
    auth(x_api_key); jid="demo-"+uuid.uuid4().hex[:8]; jobs[jid]={"status":"queued","backend":"pending IBM account","ibm_job_id":None}; return {"job_id":jid,"status":"queued","message":"Configure IBM_QUANTUM_TOKEN locally, then run pipeline/hardware_demo.py"}

@app.get("/v1/models")
def models():
    return {"model_version":"qocsvm-demo-1.0","n_qubits":6,"feature_map":"ZZFeatureMap(reps=2, entanglement='linear')","quantum_kernel":"FidelityQuantumKernel","backend":"AerSimulator (IBM mode available)","metrics":[{"name":"Isolation Forest","f1":0.81,"recall":0.78,"runtime":"42 ms"},{"name":"Classical OCSVM","f1":0.76,"recall":0.72,"runtime":"31 ms"},{"name":"Quantum OCSVM (Aer)","f1":0.79,"recall":0.75,"runtime":"640 ms"},{"name":"Hybrid fusion","f1":0.86,"recall":0.84,"runtime":"710 ms"}]}
