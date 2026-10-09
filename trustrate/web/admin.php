<?php
require __DIR__.'/bootstrap.php';
require __DIR__.'/../db/demo.php';
$error=null; $rows=[]; $audit=[]; $related=[]; $detail=null; $products=[]; $filter=''; $filterProduct=0; $counts=[]; $sort='risk';
function reasonSummary(?string $json): string {
    $value=json_decode($json??'',true);
    if(!is_array($value)) return 'Awaiting real scoring.';
    $items=[];
    foreach($value as $key=>$item) {
        if(is_string($item)) $items[]=$item;
        elseif(is_array($item)&&isset($item['description'])) $items[]=(string)$item['description'];
        elseif(is_array($item)&&isset($item['reason'])) $items[]=(string)$item['reason'];
        elseif(is_scalar($item)) $items[]=str_replace('_',' ',(string)$key).': '.(string)$item;
        if(count($items)>=8) break;
    }
    return $items?implode(' · ',$items):'Structured model evidence is available in Model evidence. These are model signals, not proof of fraud.';
}
function textTokens(string $body): array { return array_unique(preg_split('/[^a-z0-9]+/',strtolower($body),-1,PREG_SPLIT_NO_EMPTY)); }
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
            injectDemo((int)$user['id'],(int)($_POST['product_id']??0),(string)($_POST['scenario']??''),$reason);
        } elseif($action==='reset_demo') {
            resetDemo((int)$user['id'],(int)($_POST['product_id']??0),$reason);
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
    $sort=(string)($_GET['sort']??'risk');
    $orders=['risk'=>"(r.status='flagged') DESC,s.hybrid_score DESC,r.created_at DESC,r.id DESC",'newest'=>'r.created_at DESC,r.id DESC','oldest'=>'r.created_at,r.id','rating'=>'r.rating,r.created_at DESC'];
    if(!isset($orders[$sort])) $sort='risk';
    $rows=query("SELECT r.*,u.name,u.created_at AS account_created,s.label,s.classical_score,s.quantum_score,s.hybrid_score,s.reasons,s.backend,s.model_version,s.ibm_job_id,q.attempts,q.last_error FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision LEFT JOIN scoring_queue q ON q.review_id=r.id WHERE $where ORDER BY ".$orders[$sort]." LIMIT 100",$params)->fetchAll();
    $counts=query("SELECT COUNT(*) total,SUM(s.review_id IS NOT NULL) scored,SUM(r.status='pending_score') pending,SUM(r.status='flagged') flagged FROM reviews r LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE $where",$params)->fetch();
    $products=query("SELECT id,name FROM products WHERE slug NOT LIKE 'native-%' ORDER BY CASE WHEN slug LIKE 'dataset-%' THEN 0 ELSE 1 END,id")->fetchAll();
    $selected=(int)($_GET['review']??0);
    if($selected) {
        $detail=query('SELECT r.*,u.created_at AS account_created,s.label,s.classical_score,s.quantum_score,s.hybrid_score,s.reasons,s.backend,s.model_version,s.ibm_job_id FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE r.id=?',[$selected])->fetch();
        if($detail) {
            $candidates=query("SELECT r.id,r.title,r.body,r.user_id,r.created_at,r.status,r.ip_hash,r.ip_prefix,r.user_agent,s.label FROM reviews r LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE r.id<>? AND r.status<>'deleted' AND (r.product_id=? OR r.user_id=? OR r.ip_hash=? OR (r.ip_prefix<>'' AND r.ip_prefix=?)) ORDER BY ABS(TIMESTAMPDIFF(SECOND,r.created_at,?)),r.id DESC LIMIT 200",[$selected,$detail['product_id'],$detail['user_id'],$detail['ip_hash'],$detail['ip_prefix'],$detail['created_at']])->fetchAll();
            $tokens=textTokens($detail['body']);
            foreach($candidates as $candidate) {
                $other=textTokens($candidate['body']); $union=count(array_unique(array_merge($tokens,$other)));
                $similarity=$union?count(array_intersect($tokens,$other))/$union:0;
                $minutes=abs(strtotime($candidate['created_at'])-strtotime($detail['created_at']))/60;
                $signals=[];
                if($candidate['user_id']===$detail['user_id']) $signals[]='same account';
                if($candidate['ip_hash']===$detail['ip_hash']) $signals[]='same IP identity';
                elseif($candidate['ip_prefix']!==''&&$candidate['ip_prefix']===$detail['ip_prefix']) $signals[]='shared subnet';
                if($similarity>=.35) $signals[]='text overlap '.round($similarity*100).'%';
                if($minutes<=60) $signals[]='within '.round($minutes).' min';
                if(!$signals) continue;
                $candidate['signals']=implode(' · ',$signals); $candidate['overlap']=$similarity; $related[]=$candidate;
            }
            usort($related,fn($a,$b)=>$b['overlap']<=>$a['overlap']); $related=array_slice($related,0,20);
        }
    }
    $audit=query('SELECT a.*,u.name FROM admin_actions a JOIN users u ON u.id=a.admin_id '.($selected?'WHERE review_id=? ':'').'ORDER BY a.id DESC LIMIT 50',$selected?[$selected]:[])->fetchAll();
} catch(Throwable $e) { $error='Moderation data is temporarily unavailable.'; }
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrustRate · Moderation</title><link rel="stylesheet" href="/styles.css"><style>main{max-width:1120px;margin:40px auto;padding:0 24px}article,section{background:white;padding:24px;border:1px solid #dce3dd;border-radius:16px;margin:16px 0}h1{font-size:42px;letter-spacing:-1px}input,select{padding:12px;margin:8px 0;width:100%;max-width:600px;border:1px solid #bbc9bf;border-radius:8px}button{margin:8px 8px 8px 0}p,pre{overflow-wrap:anywhere;white-space:pre-wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}nav{flex-wrap:wrap;height:auto;min-height:74px;padding:18px 5vw}</style></head><body><nav><a class="brand" href="/index.php">TrustRate</a><a href="/index.php">Products</a><a href="/admin.php">Moderation</a><a href="/models.php">Model evidence</a></nav><main><p class="eyebrow">Human judgment, supported by evidence</p><h1>Review moderation</h1><p>Remove excludes a review from both ratings. Restore explicitly includes it in Genuine. Administrator Watch keeps it in Raw but excludes it from Genuine, including formerly flagged reviews. A model watch is different: it is published and eligible for Genuine. Deleted reviews cannot be restored.</p>
<link rel="stylesheet" href="/evidence.css"><form method="post" action="/index.php"><?=csrfField()?><button name="action" value="logout">Sign out</button></form>
<section class="demo-kpis"><?php foreach(['total'=>'Reviews','scored'=>'Scored','pending'=>'Pending','flagged'=>'Flagged'] as $key=>$label):?><div><span><?=esc($label)?></span><strong><?=(int)($counts[$key]??0)?></strong></div><?php endforeach;?></section><p class="muted">Counts follow the selected filters. Showing at most 100 reviews. Refresh to see real scoring progress.</p>
<?php if($error):?><p role="alert"><?=esc($error)?></p><?php endif;?>
<form method="get"><div class="grid"><label>Status<select name="status"><option value="">All statuses</option><?php foreach(['pending_score','flagged','published','watch','removed','restored'] as $state):?><option value="<?=$state?>" <?=$filter===$state?'selected':''?>><?=$state?></option><?php endforeach;?></select></label><label>Product<select name="product"><option value="0">All products</option><?php foreach($products as $p):?><option value="<?=(int)$p['id']?>" <?=$filterProduct===(int)$p['id']?'selected':''?>><?=esc($p['name'])?></option><?php endforeach;?></select></label></div><button>Filter alert queue</button></form>
<?php if($detail):?><section><h2>Score breakdown</h2><div class="grid"><?php foreach(['classical_score'=>'Classical ensemble','quantum_score'=>'Quantum OCSVM · Aer','hybrid_score'=>'Hybrid suspicion'] as $key=>$name):?><div><strong><?=esc($name)?></strong><p><?=isset($detail[$key])?number_format((float)$detail[$key],3):'Pending'?></p><meter min="0" max="1" value="<?=esc($detail[$key]??0)?>" style="width:100%;height:30px"><?=esc($detail[$key]??0)?></meter></div><?php endforeach;?></div></section><?php endif;?>
<?php if(envv('DEMO_MODE')==='1'):?><section class="demo-lab"><h2>Synthetic attack laboratory</h2><p>A1 creates 40 reviews; other scenarios create 24. Every review is sent to the real scoring queue. Detection is not guaranteed: scenario labels describe simulation intent, not a model conclusion. N1/N2 are benign comparison simulations.</p><form method="post"><?=csrfField()?><div class="grid"><label>Scenario<select name="scenario"><?php foreach(demoScenarios() as $s=>$description):?><option value="<?=$s?>"><?=esc($s.' · '.$description)?></option><?php endforeach;?></select></label><label>Product<select name="product_id"><?php foreach($products as $p):?><option value="<?=(int)$p['id']?>"><?=esc($p['name'])?></option><?php endforeach;?></select></label></div><label>Audit reason<input name="reason" required maxlength="488" placeholder="Describe this demonstration"></label><button name="action" value="inject">Inject synthetic campaign</button><button class="ghost" name="action" value="reset_demo">Reset this product’s demo reviews</button><p class="muted">Reset soft-deletes only button-injected reviews for the selected product, clears their scores and queue entries, and preserves every audit event. Imported datasets and user reviews are retained.</p></form></section><?php endif;?>
<?php if($detail):?><section><h2>Review #<?=(int)$detail['id']?> · evidence</h2><p><?=esc($detail['body'])?></p><p>Account created <?=esc($detail['account_created'])?> · reviewed <?=esc($detail['created_at'])?> · revision <?=(int)$detail['revision']?> · prefix <?=esc($detail['ip_prefix'])?> · user agent <?=esc($detail['user_agent'])?></p><p>Backend <?=esc($detail['backend']??'pending')?> · model <?=esc($detail['model_version']??'pending')?> · IBM receipt <?=esc($detail['ibm_job_id']??'none')?></p><p><?=esc(reasonSummary($detail['reasons']))?></p><h3>Related metadata and account history</h3><p>Observational leads, not detector attribution or proof of fraud. Up to 200 nearby candidates are compared by account, masked network, review time, and token-set text overlap; the top 20 matches are shown.</p><?php foreach($related as $r):?><div class="related-review"><a href="?review=<?=(int)$r['id']?>">#<?=(int)$r['id']?> <?=esc($r['title'])?></a><small><?=esc($r['signals'])?> · <?=esc($r['created_at'])?> · <?=esc($r['status'])?></small><p><?=esc(substr($r['body'],0,300))?></p></div><?php endforeach;?><?php if(!$related):?><p>No related reviews found in the bounded sample.</p><?php endif;?></section><?php endif;?>
<form method="get" class="sort-form"><input type="hidden" name="status" value="<?=esc($filter)?>"><input type="hidden" name="product" value="<?=$filterProduct?>"><label>Order<select name="sort"><?php foreach(['risk'=>'Highest suspicion','newest'=>'Newest first','oldest'=>'Oldest first','rating'=>'Lowest rating first'] as $key=>$label):?><option value="<?=$key?>" <?=$sort===$key?'selected':''?>><?=$label?></option><?php endforeach;?></select></label><button>Sort reviews</button><a href="/admin.php">Clear filters</a></form>
<?php foreach($rows as $r):?><article data-review-id="<?=(int)$r['id']?>"><h2><a href="?review=<?=(int)$r['id']?>">#<?=(int)$r['id']?> <?=esc($r['title'])?></a></h2><small><?=esc($r['name'])?> · <?=esc($r['created_at'])?> · <?=(int)$r['rating']?>/5 · <?=esc($r['status'])?> · <?=esc($r['label']??'pending')?> · hybrid <?=isset($r['hybrid_score'])?number_format((float)$r['hybrid_score'],3):'—'?><?php if($r['is_synthetic']):?> · synthetic <?=esc($r['scenario'])?><?php endif;?></small><p class="review-body"><?=esc($r['body'])?></p><details><summary>Scoring reasons &amp; moderation</summary><p><?=esc(reasonSummary($r['reasons']))?></p><?php if($r['last_error']):?><p>Queue: <?=esc($r['last_error'])?> (<?=(int)$r['attempts']?> attempts)</p><?php endif;?><form method="post"><?=csrfField()?><input type="hidden" name="review_id" value="<?=(int)$r['id']?>"><input type="hidden" name="revision" value="<?=(int)$r['revision']?>"><label>Reason<input name="reason" required maxlength="500"></label><button name="action" value="remove">Remove</button><button name="action" value="restore">Restore</button><button name="action" value="watch">Watch</button></form></details></article><?php endforeach;?>
<h2>Audit history<?=$detail?' for selected review':''?></h2><?php foreach($audit as $a):?><article><strong><?=esc($a['action'])?> review #<?=(int)$a['review_id']?></strong><p><?=esc($a['name'])?> · <?=esc($a['created_at'])?> · previously <?=esc($a['previous_status'])?></p><p><?=esc($a['reason'])?></p></article><?php endforeach;?></main></body></html>
