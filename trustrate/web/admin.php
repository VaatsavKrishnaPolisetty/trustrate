<?php
require __DIR__.'/bootstrap.php';
$user=currentUser(); if(!$user||$user['role']!=='admin') { http_response_code(403); exit('Administrator access required.'); }
$error=null;
try {
    if($_SERVER['REQUEST_METHOD']==='POST') {
        requireCsrf(); $id=(int)($_POST['review_id']??0); $action=(string)($_POST['action']??''); $reason=trim((string)($_POST['reason']??''));
        $states=['remove'=>'removed','restore'=>'restored','watch'=>'watch'];
        if(!isset($states[$action])||$reason===''||strlen($reason)>500) throw new RuntimeException('Choose an action and give a reason up to 500 bytes.');
        db()->beginTransaction(); $review=query('SELECT * FROM reviews WHERE id=? FOR UPDATE',[$id])->fetch();
        if(!$review||$review['status']==='deleted') throw new RuntimeException('Deleted or missing reviews cannot be moderated.');
        query('UPDATE reviews SET status=? WHERE id=?',[$states[$action],$id]);
        query('INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,?,?,?)',[$user['id'],$id,$action,$review['status'],$reason]);
        db()->commit(); header('Location: /admin.php',true,303); exit;
    }
} catch(Throwable $e) { if(db()->inTransaction()) db()->rollBack(); $error=$e instanceof PDOException?'Unable to save moderation action.':$e->getMessage(); }
$rows=query("SELECT r.*,u.name,s.label,s.hybrid_score,q.attempts,q.last_error FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision LEFT JOIN scoring_queue q ON q.review_id=r.id WHERE r.status<>'deleted' ORDER BY r.created_at DESC LIMIT 100")->fetchAll();
$audit=query('SELECT a.*,u.name FROM admin_actions a JOIN users u ON u.id=a.admin_id ORDER BY a.id DESC LIMIT 50')->fetchAll();
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrustRate · Moderation</title><link rel="stylesheet" href="/styles.css"><style>main{max-width:1100px;margin:40px auto;padding:0 24px}article{background:white;padding:24px;border:1px solid #dce3dd;border-radius:16px;margin:16px 0}h1{font-size:42px;letter-spacing:-1px}input,select{padding:12px;margin:8px;width:100%;max-width:450px}button{margin:8px}p{overflow-wrap:anywhere}</style></head><body><nav><a class="brand" href="/index.php">TrustRate</a><a href="/index.php">Products</a></nav><main><h1>Review moderation</h1><p>Remove hides a review from public ratings. Restore explicitly includes it in the genuine rating. Watch keeps it visible and follows its current score. User-deleted reviews cannot be restored.</p><?php if($error):?><p role="alert"><?=esc($error)?></p><?php endif;?><?php foreach($rows as $r):?><article><h2>#<?=(int)$r['id']?> <?=esc($r['title'])?></h2><p><?=esc($r['name'])?> · <?=esc($r['status'])?> · <?=esc($r['label']??'pending')?> · <?=esc($r['hybrid_score']??'—')?></p><p><?=esc($r['body'])?></p><?php if($r['last_error']):?><p>Queue: <?=esc($r['last_error'])?> (<?=(int)$r['attempts']?> attempts)</p><?php endif;?><form method="post"><?=csrfField()?><input type="hidden" name="review_id" value="<?=(int)$r['id']?>"><label>Reason<input name="reason" required maxlength="500"></label><button name="action" value="remove">Remove</button><button name="action" value="restore">Restore</button><button name="action" value="watch">Watch</button></form></article><?php endforeach;?><h2>Recent audit history</h2><?php foreach($audit as $a):?><article><strong><?=esc($a['action'])?> review #<?=(int)$a['review_id']?></strong><p><?=esc($a['name'])?> · <?=esc($a['created_at'])?> · previously <?=esc($a['previous_status'])?></p><p><?=esc($a['reason'])?></p></article><?php endforeach;?></main></body></html>
