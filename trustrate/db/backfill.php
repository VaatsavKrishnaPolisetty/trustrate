<?php
// Explicit bulk scoring of imported synthetic reviews, through the real API.
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require __DIR__.'/../web/bootstrap.php';
$total=0;
try {
    while(true) {
        $batch=query("SELECT id,revision FROM reviews WHERE status='pending_score' AND source_id IS NOT NULL ORDER BY created_at,id LIMIT 64")->fetchAll();
        if(!$batch) break;
        $ids=array_map(fn($r)=>(int)$r['id'],$batch); $expected=array_column($batch,'revision','id');
        $curl=curl_init(rtrim(envv('SCORING_URL','http://127.0.0.1:8001'),'/').'/v1/score/batch');
        curl_setopt_array($curl,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode(['review_ids'=>$ids],JSON_THROW_ON_ERROR),CURLOPT_HTTPHEADER=>['Content-Type: application/json','X-API-Key: '.envv('SCORING_API_KEY')],CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>120]);
        $body=curl_exec($curl); $code=curl_getinfo($curl,CURLINFO_HTTP_CODE); unset($curl);
        if($code===429) { sleep(60); continue; }
        if($body===false||$code!==200) throw new RuntimeException('Batch scoring unavailable; database left pending.');
        $result=json_decode($body,true,64,JSON_THROW_ON_ERROR)['results']??[];
        if(count($result)!==count($ids)) throw new RuntimeException('Incomplete batch response');
        $seen=[];
        foreach($result as $r) {
            $id=(int)($r['review_id']??0);
            if(!isset($expected[$id])||isset($seen[$id])||(int)$r['review_revision']!==(int)$expected[$id]) throw new RuntimeException('Batch revision or ID mismatch');
            $seen[$id]=true;
            foreach(['classical_score','quantum_score','hybrid_score'] as $f) if(!isset($r[$f])||!is_numeric($r[$f])||!is_finite((float)$r[$f])||$r[$f]<0||$r[$f]>1) throw new RuntimeException('Invalid model score');
            if(!in_array($r['label']??null,['genuine','watch','suspicious'],true)||!is_array($r['reasons']??null)||($r['backend']??null)!=='aer_simulator'||!is_string($r['model_version']??null)) throw new RuntimeException('Invalid model metadata');
            db()->beginTransaction();
            $row=query('SELECT status,revision FROM reviews WHERE id=? FOR UPDATE',[$id])->fetch();
            if($row&&$row['status']==='pending_score'&&(int)$row['revision']===(int)$expected[$id]) {
                query('INSERT INTO review_scores(review_id,review_revision,classical_score,quantum_score,hybrid_score,label,reasons,backend,model_version) VALUES (?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE review_revision=VALUES(review_revision),classical_score=VALUES(classical_score),quantum_score=VALUES(quantum_score),hybrid_score=VALUES(hybrid_score),label=VALUES(label),reasons=VALUES(reasons),backend=VALUES(backend),model_version=VALUES(model_version),scored_at=CURRENT_TIMESTAMP',[$id,$r['review_revision'],$r['classical_score'],$r['quantum_score'],$r['hybrid_score'],$r['label'],json_encode($r['reasons'],JSON_THROW_ON_ERROR),$r['backend'],$r['model_version']]);
                query('UPDATE reviews SET status=? WHERE id=?',[$r['label']==='suspicious'?'flagged':'published',$id]);
                query('DELETE FROM scoring_queue WHERE review_id=? AND revision=?',[$id,$r['review_revision']]); $total++;
            }
            db()->commit();
        }
        fwrite(STDOUT,"Persisted $total real model scores in this backfill.\n");
    }
    fwrite(STDOUT,"All imported reviews have current persisted scores.\n");
} catch(Throwable $e) { rollback(); fwrite(STDERR,"Backfill stopped safely; pending reviews retained.\n"); exit(1); }
