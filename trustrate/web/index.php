<?php
require __DIR__.'/bootstrap.php';
$error=null;
try {
    $user=currentUser();
    if($_SERVER['REQUEST_METHOD']==='POST') {
        requireCsrf(); $action=(string)($_POST['action']??'');
        if(in_array($action,['login','register'],true)) {
            limitRate('auth',20,900); $email=strtolower(trim((string)($_POST['email']??''))); $password=(string)($_POST['password']??'');
            if($action==='register') {
                $name=trim((string)($_POST['name']??''));
                if(!filter_var($email,FILTER_VALIDATE_EMAIL)||strlen($email)>254||strlen($password)<12||strlen($password)>72||$name===''||strlen($name)>100) throw new RuntimeException('Use a valid email, a name under 100 bytes, and a password of 12–72 bytes.');
                try { query('INSERT INTO users(email,name,password_hash) VALUES (?,?,?)',[$email,$name,password_hash($password,PASSWORD_DEFAULT)]); } catch(PDOException $e) { if($e->getCode()==='23000') throw new RuntimeException('Unable to register that email. Try signing in.'); throw $e; }
            }
            $account=query('SELECT * FROM users WHERE email=?',[$email])->fetch();
            if(!$account||!password_verify($password,$account['password_hash'])) throw new RuntimeException('Email or password is incorrect.');
            session_regenerate_id(true); $_SESSION['uid']=$account['id']; $_SESSION['signed_in']=time(); $_SESSION['csrf']=bin2hex(random_bytes(32));
        } elseif($action==='logout') { $_SESSION=[]; session_regenerate_id(true); }
        else {
            if(!$user) { http_response_code(401); throw new RuntimeException('Please sign in.'); }
            limitRate('review:'.$user['id'],30,3600);
            if(in_array($action,['create','edit'],true)) {
                $rating=filter_var($_POST['rating']??null,FILTER_VALIDATE_INT); $title=trim((string)($_POST['title']??'')); $body=trim((string)($_POST['body']??''));
                if(!$rating||$rating<1||$rating>5||$title===''||strlen($title)>200||strlen($body)<10||strlen($body)>10000) throw new RuntimeException('Choose 1–5 stars, a title up to 200 bytes, and a review of 10–10,000 bytes.');
            }
            db()->beginTransaction();
            if($action==='create') {
                $product=(int)($_POST['product_id']??1);
                if(!query('SELECT id FROM products WHERE id=?',[$product])->fetch()) throw new RuntimeException('Product not found.');
                query('INSERT INTO reviews(product_id,user_id,rating,title,body,ip_hash,ip_prefix,user_agent) VALUES (?,?,?,?,?,?,?,?)',[$product,$user['id'],$rating,$title,$body,ipHash(),ipPrefix(),substr($_SERVER['HTTP_USER_AGENT']??'',0,512)]); enqueue((int)db()->lastInsertId(),1);
            } elseif(in_array($action,['edit','delete'],true)) {
                $id=(int)($_POST['review_id']??0); $review=query('SELECT * FROM reviews WHERE id=? FOR UPDATE',[$id])->fetch();
                if(!$review||(int)$review['user_id']!==(int)$user['id']||$review['status']==='deleted') { http_response_code(403); throw new RuntimeException('You cannot change this review.'); }
                if((int)($_POST['revision']??0)!==(int)$review['revision']) { http_response_code(409); throw new RuntimeException('This review changed. Reload before saving.'); }
                if($action==='delete') { query("UPDATE reviews SET status='deleted',revision=revision+1 WHERE id=?",[$id]); query('DELETE FROM review_scores WHERE review_id=?',[$id]); query('DELETE FROM scoring_queue WHERE review_id=?',[$id]); }
                else {
                    // Editing cannot bypass a moderator removal; a previous restore is rescored.
                    query("UPDATE reviews SET rating=?,title=?,body=?,revision=revision+1,status=IF(status IN ('removed','watch'),status,'pending_score'),ip_hash=?,ip_prefix=?,user_agent=? WHERE id=?",[$rating,$title,$body,ipHash(),ipPrefix(),substr($_SERVER['HTTP_USER_AGENT']??'',0,512),$id]); enqueue($id,(int)$review['revision']+1);
                }
            } else throw new RuntimeException('Unknown action.');
            db()->commit();
        }
        header('Location: /index.php',true,303); exit;
    }
} catch(Throwable $e) {
    rollback(); $error=safeError($e);
}
$user=$user??null;
try {
    $products=query("SELECT * FROM products WHERE slug NOT LIKE 'native-%' ORDER BY CASE WHEN slug LIKE 'dataset-%' THEN 0 ELSE 1 END,id")->fetchAll();
    $productId=(int)($_GET['product']??($products[0]['id']??1)); $product=query('SELECT * FROM products WHERE id=?',[$productId])->fetch();
    if(!$product) { http_response_code(404); throw new RuntimeException('Product not found.'); }
    $reviews=query("SELECT r.*,u.name,s.label,s.hybrid_score FROM reviews r JOIN users u ON u.id=r.user_id LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision WHERE r.product_id=? AND (r.status NOT IN ('removed','deleted') OR (r.user_id=? AND r.status='removed')) ORDER BY r.created_at DESC,r.id DESC LIMIT 100",[$productId,$user['id']??0])->fetchAll();
    $stats=query("SELECT AVG(r.rating) raw_rating, AVG(CASE WHEN r.status='restored' OR (r.status='published' AND s.label IN ('genuine','watch') AND s.review_revision=r.revision) THEN r.rating END) genuine_rating, COUNT(*) total, SUM(r.status='pending_score') pending, SUM(r.status IN ('flagged','watch')) excluded FROM reviews r LEFT JOIN review_scores s ON s.review_id=r.id WHERE r.product_id=? AND r.status NOT IN ('removed','deleted')",[$productId])->fetch();
} catch(Throwable $e) { $error=$error??'Products are unavailable. Initialize the database first.'; $products=[]; $reviews=[]; $stats=[]; }
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrustRate · Product reviews</title><link rel="stylesheet" href="/styles.css"><style>main{max-width:1100px;margin:40px auto;padding:0 24px}section,article{background:white;border:1px solid #dce3dd;border-radius:16px;padding:24px;margin:20px 0}h1{font-size:42px;letter-spacing:-1px}input,textarea,select{display:block;width:100%;padding:12px;margin:8px 0 16px;border:1px solid #bbc9bf;border-radius:8px;font:inherit}textarea{min-height:100px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px}nav{height:auto;min-height:74px;gap:12px;flex-wrap:wrap;padding:18px 5vw}nav form{margin:0}.error{padding:16px;background:#fff0e8}small{color:#52625a}summary{cursor:pointer}button{margin:5px 0}</style></head><body><nav><a class="brand" href="/index.php">TrustRate</a><div><a href="/index.php">Products</a><?php if(($user['role']??'')==='admin'):?><a href="/admin.php">Moderation</a><?php endif;?></div><?php if($user):?><form method="post"><?=csrfField()?><input type="hidden" name="action" value="logout"><span><?=esc($user['name'])?></span> <button>Sign out</button></form><?php endif;?></nav><main>
<?php if($error):?><p role="alert" class="error"><?=esc($error)?></p><?php endif;?>
<p class="eyebrow">Real experiences. Clearer signals.</p><h1><?=esc($product['name']??'Product reviews')?></h1><p><?=esc($product['description']??'')?></p>
<?php foreach($products as $p):?><a href="?product=<?=(int)$p['id']?>"><?=esc($p['name'])?></a> <?php endforeach;?>
<p><a href="/models.php">Model evidence and hardware receipts</a></p>
<p class="dataset-note"><strong>Research dataset:</strong> real public review text from UCI (CC BY 4.0), with simulated products, accounts and cyber activity. These are not verified purchases. <strong><?= (int)($stats['excluded']??0) ?></strong> flagged/watched reviews excluded; <strong><?= (int)($stats['pending']??0) ?></strong> awaiting scoring.</p>
<section class="grid"><div><h2>Raw rating</h2><strong><?=isset($stats['raw_rating'])?number_format((float)$stats['raw_rating'],2):'—'?> / 5</strong><p>All reviews except removed and deleted, including pending and flagged.</p></div><div><h2>Genuine rating</h2><strong><?=isset($stats['genuine_rating'])?number_format((float)$stats['genuine_rating'],2):'—'?> / 5</strong><p>Published genuine or model-watch scores, plus moderator-restored reviews. Pending, flagged, and administrator-watched reviews are excluded.</p></div><div><h2><?=(int)($stats['total']??0)?> reviews</h2><p>Model signals assist moderation; they are not proof of fraud.</p></div></section>
<?php if(!$user):?><div class="grid"><?php foreach(['login'=>'Sign in','register'=>'Create account'] as $action=>$label):?><section><h2><?=$label?></h2><form method="post"><?=csrfField()?><input type="hidden" name="action" value="<?=$action?>"><?php if($action==='register'):?><label>Name<input name="name" required maxlength="100" autocomplete="name"></label><?php endif;?><label>Email<input type="email" name="email" required autocomplete="email"></label><label>Password<input type="password" name="password" required <?= $action==='register'?'minlength="12" maxlength="72"':''?> autocomplete="<?=$action==='login'?'current-password':'new-password'?>"></label><button><?=$label?></button></form></section><?php endforeach;?></div>
<?php else:?><section><h2>Share your experience</h2><form method="post"><?=csrfField()?><input type="hidden" name="action" value="create"><input type="hidden" name="product_id" value="<?=$productId?>"><label>Stars<select name="rating"><?php for($i=5;$i>=1;$i--):?><option><?=$i?></option><?php endfor;?></select></label><label>Title<input name="title" required maxlength="200"></label><label>Review<textarea name="body" required minlength="10" maxlength="10000"></textarea></label><button>Publish review</button></form></section><?php endif;?>
<h2>Recent reviews</h2><?php foreach($reviews as $r):?><article data-review-id="<?=(int)$r['id']?>"><h3><?=esc($r['title'])?> · <?=(int)$r['rating']?>/5</h3><small><?=esc($r['name'])?> · <?=esc($r['created_at'])?> · <?=esc($r['status'])?> · <?=esc($r['label']??'pending scoring')?></small><p style="white-space:pre-wrap"><?=esc($r['body'])?></p>
<?php if((int)($user['id']??0)===(int)$r['user_id']):?><details><summary>Edit your review</summary><form method="post"><?=csrfField()?><input type="hidden" name="action" value="edit"><input type="hidden" name="review_id" value="<?=(int)$r['id']?>"><input type="hidden" name="revision" value="<?=(int)$r['revision']?>"><label>Stars<input type="number" min="1" max="5" name="rating" value="<?=(int)$r['rating']?>" required></label><label>Title<input name="title" maxlength="200" value="<?=esc($r['title'])?>" required></label><label>Review<textarea name="body" required minlength="10" maxlength="10000"><?=esc($r['body'])?></textarea></label><button>Save and rescore</button></form></details><form method="post"><?=csrfField()?><input type="hidden" name="review_id" value="<?=(int)$r['id']?>"><input type="hidden" name="revision" value="<?=(int)$r['revision']?>"><button class="ghost" name="action" value="delete">Delete my review</button></form><?php endif;?></article><?php endforeach;?><?php if(!$reviews):?><p>No reviews yet.</p><?php endif;?></main></body></html>
