<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require __DIR__.'/../web/bootstrap.php';
$once=in_array('--once',$argv,true);
function scorePending(): bool {
    db()->beginTransaction();
    $job=query('SELECT * FROM scoring_queue WHERE available_at<=CURRENT_TIMESTAMP AND (locked_until IS NULL OR locked_until<CURRENT_TIMESTAMP) ORDER BY available_at LIMIT 1 FOR UPDATE SKIP LOCKED')->fetch();
    if(!$job) { db()->commit(); return false; }
    query('UPDATE scoring_queue SET locked_until=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 120 SECOND),attempts=attempts+1 WHERE review_id=?',[$job['review_id']]);
    db()->commit();
    try {
        $url=rtrim(envv('SCORING_URL','http://127.0.0.1:8000'),'/').'/v1/score';
        $curl=curl_init($url);
        curl_setopt_array($curl,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode(['review_id'=>(int)$job['review_id']],JSON_THROW_ON_ERROR),CURLOPT_HTTPHEADER=>['Content-Type: application/json','X-API-Key: '.envv('SCORING_API_KEY')],CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>5,CURLOPT_TIMEOUT=>90,CURLOPT_FOLLOWLOCATION=>false]);
        $body=curl_exec($curl); $code=curl_getinfo($curl,CURLINFO_HTTP_CODE); curl_close($curl);
        if($body===false||$code!==200) throw new RuntimeException('Scoring service unavailable');
        $result=json_decode($body,true,64,JSON_THROW_ON_ERROR);
        if(!is_array($result)) throw new RuntimeException('Invalid scoring response');
        if((int)($result['review_id']??0)!==(int)$job['review_id']||(int)($result['review_revision']??0)!==(int)$job['revision']) throw new RuntimeException('Scoring revision mismatch');
        foreach(['classical_score','quantum_score','hybrid_score'] as $key) if(!isset($result[$key])||!is_numeric($result[$key])||!is_finite((float)$result[$key])||(float)$result[$key]<0||(float)$result[$key]>1) throw new RuntimeException('Invalid score range');
        if(!in_array($result['label']??null,['genuine','suspicious','uncertain','watch'],true)||!is_array($result['reasons']??null)) throw new RuntimeException('Invalid score metadata');
        foreach(['backend','model_version'] as $key) if(!is_string($result[$key]??null)||$result[$key]===''||strlen($result[$key])>100) throw new RuntimeException('Invalid model metadata');
        db()->beginTransaction();
        // All writers lock the review before its queue entry: edits cannot install stale scores.
        $review=query('SELECT revision,status FROM reviews WHERE id=? FOR UPDATE',[$job['review_id']])->fetch();
        $current=query('SELECT revision FROM scoring_queue WHERE review_id=? FOR UPDATE',[$job['review_id']])->fetch();
        if($review&&$current&&$review['status']!=='deleted'&&(int)$review['revision']===(int)$job['revision']&&(int)$current['revision']===(int)$job['revision']) {
            query('INSERT INTO review_scores(review_id,review_revision,classical_score,quantum_score,hybrid_score,label,reasons,backend,model_version) VALUES (?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE review_revision=VALUES(review_revision),classical_score=VALUES(classical_score),quantum_score=VALUES(quantum_score),hybrid_score=VALUES(hybrid_score),label=VALUES(label),reasons=VALUES(reasons),backend=VALUES(backend),model_version=VALUES(model_version),scored_at=CURRENT_TIMESTAMP',[$job['review_id'],$job['revision'],$result['classical_score'],$result['quantum_score'],$result['hybrid_score'],$result['label'],json_encode($result['reasons'],JSON_THROW_ON_ERROR),$result['backend'],$result['model_version']]);
            query('DELETE FROM scoring_queue WHERE review_id=? AND revision=?',[$job['review_id'],$job['revision']]);
        }
        db()->commit();
        fwrite(STDOUT,"Processed review ".$job['review_id']." revision ".$job['revision']."\n");
    } catch(Throwable $e) {
        if(db()->inTransaction()) db()->rollBack();
        $delay=min(3600,15*(2**min((int)$job['attempts'],8)));
        // Persist no response bodies, SQL errors, tokens, or other sensitive error detail.
        query('UPDATE scoring_queue SET locked_until=NULL,last_error=?,available_at=TIMESTAMPADD(SECOND,?,CURRENT_TIMESTAMP) WHERE review_id=? AND revision=?',['Scoring failed; retry scheduled',$delay,$job['review_id'],$job['revision']]);
        fwrite(STDERR,"Scoring attempt failed for review ".$job['review_id']."; retry scheduled.\n");
    }
    return true;
}
try {
    do { $found=scorePending(); if(!$once&&!$found) sleep(3); } while(!$once);
    query('DELETE FROM rate_limits WHERE expires_at<?',[time()]);
} catch(Throwable $e) { if(db()->inTransaction()) db()->rollBack(); fwrite(STDERR,"Worker database unavailable.\n"); exit(1); }
