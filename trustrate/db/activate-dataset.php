<?php
// Archive superseded synthetic imports without deleting user data, scores or audits.
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require __DIR__.'/../web/bootstrap.php';
try {
    $count=(int)query("SELECT COUNT(*) FROM reviews WHERE source_id LIKE 'v3-%' AND is_synthetic=1")->fetchColumn();
    if($count!==2208) throw new RuntimeException('Import the complete 2208-row v3 dataset before activation.');
    $admin=(int)query("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")->fetchColumn();
    db()->beginTransaction();
    $rows=query("SELECT id,status FROM reviews WHERE is_synthetic=1 AND source_id IS NOT NULL AND source_id NOT LIKE 'v3-%' AND status NOT IN ('removed','deleted') FOR UPDATE")->fetchAll();
    foreach($rows as $r) {
        query("UPDATE reviews SET status='removed' WHERE id=?",[$r['id']]);
        query('DELETE FROM scoring_queue WHERE review_id=?',[$r['id']]);
        query("INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,'remove',?,?)",[$admin,$r['id'],$r['status'],'Dataset v3 activation: superseded synthetic v2 row archived; score and content retained.']);
    }
    db()->commit(); echo 'Archived '.count($rows)." superseded synthetic rows; original scores, user reviews and audit records retained.\n";
} catch(Throwable $e) { rollback(); fwrite(STDERR,"Dataset activation stopped safely.\n"); exit(1); }
