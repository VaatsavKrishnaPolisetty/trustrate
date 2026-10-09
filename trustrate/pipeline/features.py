"""The ten explainable, leakage-safe review features."""
import re, math
FEATURE_NAMES=["ip_burst","ip_share","duplicate_text","account_velocity","automation_ua","rating_deviation","text_length","exclamation_rate","caps_rate","time_cluster"]
def _counts(rows,key):
    out={}
    for r in rows: out[key(r)]=out.get(key(r),0)+1
    return out
def extract_features(rows):
    ips=_counts(rows,lambda r:r.get('ip','')); bodies=_counts(rows,lambda r:r.get('body','').lower()); users=_counts(rows,lambda r:r.get('user',''))
    ratings=[float(r.get('rating',3)) for r in rows]; baseline=sum(ratings)/len(ratings)
    times=[float(r.get('timestamp',0)) for r in rows]
    out=[]
    for r in rows:
        text=str(r.get('body','')); letters=[c for c in text if c.isalpha()]
        t=float(r.get('timestamp',0)); nearby=sum(abs(t-x)<=60 for x in times)-1
        out.append([min(ips.get(r.get('ip',''),1)/10,1), min(ips.get(r.get('ip',''),1)/max(len(rows),1),1), min(bodies.get(text.lower(),1)/8,1), min(users.get(r.get('user',''),1)/3,1), float(bool(re.search('headless|bot|selenium',r.get('ua',''),re.I))), min(abs(float(r.get('rating',3))-baseline)/2,1), min(len(text)/500,1), min(text.count('!')/10,1), (sum(c.isupper() for c in letters)/max(len(letters),1)), min(nearby/20,1)])
    return out
