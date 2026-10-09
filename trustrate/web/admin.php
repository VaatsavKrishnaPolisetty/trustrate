<?php
require __DIR__.'/bootstrap.php';
$error=null; $rows=[]; $audit=[]; $related=[]; $detail=null; $products=[]; $filter=''; $filterProduct=0;
try {
    $user=currentUser();
    if(!$user||$user['role']!=='admin') { http_response_code(403); exit('Administrator access required.'); }
    if($_SERVER['REQUEST_METHOD']==='POST') {
        requireCsrf(); limitRate('moderate:'.$user['id'],100,3600);
        $action=(string)($_POST['action']??''); $reason=trim((string)($_POST['reason']??''));
        if($reason===''||strlen($reason)>500) throw new RuntimeException('Give an audit reason up to 500 bytes.');
        db()->beginTransaction();
        if($action==='inject') {
            if(envv('DEMO_MODE')!=='1') { http_response_code(403); throw new RuntimeException('Attack injection is disabled.'); }
            limitRate('inject:'.$user['id'],8,3600);
            $scenario=(string)($_POST['scenario']??''); $product=(int)($_POST['product_id']??0);
            if(!in_array($scenario,['A1','A2','A3','A4'],true)||!query('SELECT id FROM products WHERE id=?',[$product])->fetch()) throw new RuntimeException('Choose a valid scenario and product.');
            $batch=bin2hex(random_bytes(8)); $now=time(); $repeatUser=null;
            // Documentation-range addresses are synthetic, masked/HMACed before persistence.
            foreach(range(1,12) as $i) {
                $email='attack-'.$batch.'-'.$i.'@dataset.invalid';
                $account=gmdate('Y-m-d H:i:s',$now-($scenario==='A3'?86400*500:($scenario==='A4'?86400*30:($scenario==='A2'?3600:60))));
                if($scenario!=='A4'||$repeatUser===null) { query('INSERT INTO users(email,name,password_hash,created_at) VALUES (?,?,?,?)',[$email,"Synthetic $scenario $i",password_hash(bin2hex(random_bytes(24)),PASSWORD_DEFAULT),$account]); $uid=(int)db()->lastInsertId(); $repeatUser=$uid; }
                else $uid=$repeatUser;
                $ip=$scenario==='A2'?'2001:db8:'.dechex($i).'::20':($scenario==='A3'?"203.0.113.$i":'192.0.2.10');
                $body=match($scenario) {
                    'A1'=>'Absolutely perfect product, amazing value, five stars. Buy it today!',
                    'A2'=>['The controls work perfectly and the fit feels comfortable.','Excellent sound and finish. I recommend these headphones.','Great product, fast delivery and solid daily performance.'][$i%3],
                    'A3'=>"Terrible product, completely unusable. Avoid this purchase at all costs. Sample $i.",
                    'A4'=>'The controls work perfectly and the fit feels comfortable. Excellent product.',
                };
                $created=gmdate('Y-m-d H:i:s',$now-($scenario==='A3'?$i*900:$i*4));
                query("INSERT INTO reviews(product_id,user_id,rating,title,body,ip_hash,ip_prefix,user_agent,created_at,is_synthetic,true_label,scenario,split) VALUES (?,?,?,?,?,?,?,?,?,1,'1',?,'demo')",[$product,$uid,$scenario==='A3'?1:5,"Synthetic $scenario · $i",$body,ipHash($ip),ipPrefix($ip),$scenario==='A2'?'SyntheticAutomation/1':'SyntheticCampaign/1.0',$created,$scenario]);
                $id=(int)db()->lastInsertId(); enqueue($id,1);
                query("INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,'inject','pending_score',?)",[$user['id'],$id,$reason]);
            }
        } else {
            $states=['remove'=>'removed','restore'=>'restored','watch'=>'watch'];
            if(!isset($states[$action])) throw new RuntimeException('Choose a moderation action.');
            $id=(int)($_POST['review_id']??0); $review=query('SELECT * FROM reviews WHERE id=? FOR UPDATE',[$id])->fetch();
            if(!$review||$review['status']==='deleted') throw new RuntimeException('Deleted or missing reviews cannot be moderated.');
            if((int)($_POST['revision']??0)!==(int)$review['revision']) { http_response_code(409); throw new RuntimeException('Review content changed. Reload before moderating.'); }
            query('UPDATE reviews SET status=? WHERE id=?',[$states[$action],$id]);
            query('INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,?,?,?)',[$user['id'],$id,$action,$review['status'],$reason]);
        }
        db()->commit(); header('Location: /admin.php',true,303); exit;
    }
} catch(Throwable $e) { rollback(); $error=safeError($e); }
if(!isset($user)||!$user||$user['role']!=='admin') { http_response_code(503); exit('Moderation is temporarily unavailable.'); }
try {
    $where="r.status<>'deleted'"; $params=[];
    $filter=(string)($_GET['status']??''); $filterProduct=(int)($_GET['product']??0);
    if(in_array($filter,['pending_score','flagged','published','watch','removed','restored'],true)) { $where.=' AND r.status=?'; $params[]=$filter; }
    if($filterProduct>0) { $where.=' AND r.product_id=?'; $params[]=$filterProduct; }
    $rows=query("SELECT r.*,u.name,u.created_at AS account_created,s.label,s.classical_score,s.quantum_score,s.hybrid_score,s.reasons,s.backend,s.model_version,s.ibm_job_id,q.attempts,q.last_error FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision LEFT JOIN scoring_queue q ON q.review_id=r.id WHERE $where ORDER BY (r.status='flagged') DESC,s.hybrid_score DESC,r.created_at DESC,r.id DESC LIMIT 100",$params)->fetchAll();
    $products=query("SELECT id,name FROM products WHERE slug NOT LIKE 'native-%' ORDER BY CASE WHEN slug LIKE 'dataset-%' THEN 0 ELSE 1 END,id")->fetchAll();
    $selected=(int)($_GET['review']??0);
    if($selected) {
        $detail=query('SELECT r.*,u.created_at AS account_created,s.label,s.classical_score,s.quantum_score,s.hybrid_score,s.reasons,s.backend,s.model_version,s.ibm_job_id FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE r.id=?',[$selected])->fetch();
        if($detail) $related=query("SELECT r.id,r.title,r.user_id,r.created_at,r.status,r.ip_prefix,r.user_agent,s.label,s.hybrid_score FROM reviews r LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE r.id<>? AND (r.user_id=? OR r.ip_hash=? OR (r.ip_prefix<>'' AND r.ip_prefix=?) OR (r.user_agent<>'' AND r.user_agent=?)) ORDER BY r.created_at DESC LIMIT 50",[$selected,$detail['user_id'],$detail['ip_hash'],$detail['ip_prefix'],$detail['user_agent']])->fetchAll();
    }
    $audit=query('SELECT a.*,u.name FROM admin_actions a JOIN users u ON u.id=a.admin_id '.($selected?'WHERE review_id=? ':'').'ORDER BY a.id DESC LIMIT 50',$selected?[$selected]:[])->fetchAll();
} catch(Throwable $e) { $error='Moderation data is temporarily unavailable.'; }
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrustRate · Moderation</title><link rel="stylesheet" href="/styles.css"><style>main{max-width:1120px;margin:40px auto;padding:0 24px}article,section{background:white;padding:24px;border:1px solid #dce3dd;border-radius:16px;margin:16px 0}h1{font-size:42px;letter-spacing:-1px}input,select{padding:12px;margin:8px 0;width:100%;max-width:600px;border:1px solid #bbc9bf;border-radius:8px}button{margin:8px 8px 8px 0}p,pre{overflow-wrap:anywhere;white-space:pre-wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}nav{flex-wrap:wrap;height:auto;min-height:74px;padding:18px 5vw}</style></head><body><nav><a class="brand" href="/index.php">TrustRate</a><a href="/index.php">Products</a><a href="/admin.php">Moderation</a><a href="/models.php">Model evidence</a></nav><main><p class="eyebrow">Human judgment, supported by evidence</p><h1>Review moderation</h1><p>Remove excludes a review from both ratings. Restore explicitly includes it in Genuine. Administrator Watch keeps it in Raw but excludes it from Genuine, including formerly flagged reviews. A model watch is different: it is published and eligible for Genuine. Deleted reviews cannot be restored.</p>
<form method="post" action="/index.php"><?=csrfField()?><button name="action" value="logout">Sign out</button></form>
<?php if($error):?><p role="alert"><?=esc($error)?></p><?php endif;?>
<form method="get"><div class="grid"><label>Status<select name="status"><option value="">All statuses</option><?php foreach(['pending_score','flagged','published','watch','removed','restored'] as $state):?><option value="<?=$state?>" <?=$filter===$state?'selected':''?>><?=$state?></option><?php endforeach;?></select></label><label>Product<select name="product"><option value="0">All products</option><?php foreach($products as $p):?><option value="<?=(int)$p['id']?>" <?=$filterProduct===(int)$p['id']?'selected':''?>><?=esc($p['name'])?></option><?php endforeach;?></select></label></div><button>Filter alert queue</button></form>
<?php if($detail):?><section><h2>Score breakdown</h2><div class="grid"><?php foreach(['classical_score'=>'Classical ensemble','quantum_score'=>'Quantum OCSVM · Aer','hybrid_score'=>'Hybrid suspicion'] as $key=>$name):?><div><strong><?=esc($name)?></strong><p><?=isset($detail[$key])?number_format((float)$detail[$key],3):'Pending'?></p><meter min="0" max="1" value="<?=esc($detail[$key]??0)?>" style="width:100%;height:30px"><?=esc($detail[$key]??0)?></meter></div><?php endforeach;?></div></section><?php endif;?>
<?php if(envv('DEMO_MODE')==='1'):?><section><h2>Synthetic attack laboratory</h2><p>Creates 12 labeled synthetic reviews and queues real scoring. A1: new-account, one-IP exact-copy burst. A2: distributed new accounts with coordinated praise. A3: aged-account, slower negative campaign. A4: one account rapidly repeating a review. No score is fabricated.</p><form method="post"><?=csrfField()?><input type="hidden" name="action" value="inject"><label>Scenario<select name="scenario"><?php foreach(['A1','A2','A3','A4'] as $s):?><option><?=$s?></option><?php endforeach;?></select></label><label>Product<select name="product_id"><?php foreach($products as $p):?><option value="<?=(int)$p['id']?>"><?=esc($p['name'])?></option><?php endforeach;?></select></label><label>Audit reason<input name="reason" required maxlength="500"></label><button>Inject synthetic campaign</button></form></section><?php endif;?>
<?php if($detail):?><section><h2>Review #<?=(int)$detail['id']?> · evidence</h2><p>Account created <?=esc($detail['account_created'])?> · revision <?=(int)$detail['revision']?> · prefix <?=esc($detail['ip_prefix'])?> · user agent <?=esc($detail['user_agent'])?></p><p>Classical <?=esc($detail['classical_score']??'pending')?> · quantum <?=esc($detail['quantum_score']??'pending')?> · hybrid <?=esc($detail['hybrid_score']??'pending')?> · backend <?=esc($detail['backend']??'pending')?> · model <?=esc($detail['model_version']??'pending')?> · IBM receipt <?=esc($detail['ibm_job_id']??'none')?></p><pre><?=esc($detail['reasons']??'No current score.')?></pre><h3>Related metadata and account history</h3><p>Matches use shared account, HMAC identity, masked prefix, or user agent. Shared metadata is a lead, not proof of fraud.</p><?php foreach($related as $r):?><p><a href="?review=<?=(int)$r['id']?>">#<?=(int)$r['id']?> <?=esc($r['title'])?></a> · <?=esc($r['status'])?> · <?=esc($r['created_at'])?> · <?=esc($r['label']??'pending')?></p><?php endforeach;?></section><?php endif;?>
<?php foreach($rows as $r):?><article data-review-id="<?=(int)$r['id']?>"><h2><a href="?review=<?=(int)$r['id']?>">#<?=(int)$r['id']?> <?=esc($r['title'])?></a></h2><p><?=esc($r['name'])?> · <?=esc($r['status'])?> · <?=esc($r['label']??'pending')?> · hybrid <?=esc($r['hybrid_score']??'—')?><?php if($r['is_synthetic']):?> · synthetic <?=esc($r['scenario'])?><?php endif;?></p><p><?=esc($r['body'])?></p><details><summary>Scoring reasons</summary><pre><?=esc($r['reasons']??'Awaiting real scoring.')?></pre></details><?php if($r['last_error']):?><p>Queue: <?=esc($r['last_error'])?> (<?=(int)$r['attempts']?> attempts)</p><?php endif;?><form method="post"><?=csrfField()?><input type="hidden" name="review_id" value="<?=(int)$r['id']?>"><input type="hidden" name="revision" value="<?=(int)$r['revision']?>"><label>Reason<input name="reason" required maxlength="500"></label><button name="action" value="remove">Remove</button><button name="action" value="restore">Restore</button><button name="action" value="watch">Watch</button></form></article><?php endforeach;?>
<h2>Audit history<?=$detail?' for selected review':''?></h2><?php foreach($audit as $a):?><article><strong><?=esc($a['action'])?> review #<?=(int)$a['review_id']?></strong><p><?=esc($a['name'])?> · <?=esc($a['created_at'])?> · previously <?=esc($a['previous_status'])?></p><p><?=esc($a['reason'])?></p></article><?php endforeach;?></main></body></html>
