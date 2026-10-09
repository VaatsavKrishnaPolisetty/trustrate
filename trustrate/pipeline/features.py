"""PRD F1-F10 features; each row only sees strictly earlier events."""
import re
FEATURE_NAMES=["F1_ip_burst","F2_ip_reuse","F3_duplicate_text","F4_account_velocity","F5_automation_ua","F6_rating_deviation","F7_review_length","F8_exclamation_rate","F9_caps_rate","F10_time_cluster"]
def extract_features(rows):
 rows=sorted(rows,key=lambda r:(float(r.get('timestamp',0)),str(r.get('id','')))); ips={}; bodies={}; users={}; times=[]; ratings=[]; out=[]
 for r in rows:
  text=str(r.get('body','')); letters=[c for c in text if c.isalpha()]; t=float(r.get('timestamp',0)); baseline=sum(ratings)/len(ratings) if ratings else 3.0; n=len(times); ip=r.get('ip',''); body=text.lower(); user=r.get('user',''); nearby=sum(abs(t-x)<=60 for x in times)
  out.append([min(ips.get(ip,0)/10,1),min(ips.get(ip,0)/max(n,1),1),min(bodies.get(body,0)/8,1),min(users.get(user,0)/3,1),float(bool(re.search('headless|bot|selenium',r.get('ua',''),re.I))),min(abs(float(r.get('rating',3))-baseline)/2,1),min(len(text)/500,1),min(text.count('!')/10,1),sum(c.isupper() for c in letters)/max(len(letters),1),min(nearby/20,1)])
  ips[ip]=ips.get(ip,0)+1; bodies[body]=bodies.get(body,0)+1; users[user]=users.get(user,0)+1; times.append(t); ratings.append(float(r.get('rating',3)))
 return out
