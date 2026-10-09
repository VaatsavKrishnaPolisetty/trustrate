import argparse, json
from .data import synthetic_reviews,load_reviews,write_jsonl
from .features import extract_features
from .models import TrustRateModel
from .validation import calibrate,evaluate
def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True); d=sub.add_parser('data'); d.add_argument('--out',default='data/reviews.jsonl'); d.add_argument('--seed',type=int,default=42)
 t=sub.add_parser('train'); t.add_argument('--input',default='data/reviews.jsonl'); t.add_argument('--artifact',default='artifacts/model.joblib'); t.add_argument('--quantum',action='store_true')
 e=sub.add_parser('evaluate'); e.add_argument('--input',default='data/reviews.jsonl'); e.add_argument('--artifact',default='artifacts/model.joblib')
 a=p.parse_args()
 if a.cmd=='data': write_jsonl(synthetic_reviews(seed=a.seed),a.out); return
 rows=load_reviews(a.input); X=extract_features(rows); y=[int(r.get('label',0)) for r in rows]; m=TrustRateModel(getattr(a,'quantum',False)).fit(X); m.save(a.artifact)
 if a.cmd=='evaluate':
  s=m.scores(X)['hybrid']; c=calibrate(s,y); print(json.dumps(evaluate(s,y,c['threshold'])|c,indent=2))
if __name__=='__main__': main()
