<?php
declare(strict_types=1);
// Shared demo helpers. Callers supply an authenticated administrator and an open transaction.
function demoScenarios(): array {
    return [
        'A1'=>'Bot ring · 40 reviews, 5 IPs, 20-minute burst',
        'A2'=>'Review bombing · 1-star burst from a small IP set',
        'A3'=>'Low and slow · aged accounts, rotating IPs, paraphrases over days',
        'A4'=>'Sybil swarm · new accounts, one subnet, one review each',
        'N1'=>'Benign shared network · diverse reviews over hours',
        'N2'=>'Benign enthusiasm · established accounts, varied praise over hours',
    ];
}
function injectDemo(int $admin, int $product, string $scenario, string $reason): int {
    if(envv('DEMO_MODE')!=='1') { http_response_code(403); throw new RuntimeException('Attack injection is disabled.'); }
    if(!isset(demoScenarios()[$scenario])||!query('SELECT id FROM products WHERE id=?',[$product])->fetch()) throw new RuntimeException('Choose a valid scenario and product.');
    $batch=bin2hex(random_bytes(8)); $now=time(); $count=$scenario==='A1'?40:24;
    $password=password_hash(bin2hex(random_bytes(32)),PASSWORD_DEFAULT);
    $praise=['The wireless connection stayed stable during my commute, and the controls were easy to reach.','I used this on a long train ride. The comfortable fit was the best part, though the case is bulky.','Setup took a minute and the battery lasted through several work sessions. Good value for my needs.','Clear audio at a moderate volume; I would like a longer charging cable in the box.','The finish feels sturdy. After a week of daily use I am happy with the performance.','Useful for calls in a quiet room, but the microphone picks up street noise outside.'];
    $negative=['The connection keeps dropping during calls. This has been a disappointing purchase.','Audio cuts out repeatedly and charging is unreliable. I cannot recommend it.','The controls stopped responding and I had to reconnect several times. Poor quality.','Battery life falls far short of what I expected, and the fit is uncomfortable.'];
    // Benign controls reuse the same attributed public-text distribution rather
    // than abnormally long hand-written templates that create an OOD confound.
    $benignTexts=query("SELECT body FROM reviews WHERE source_id LIKE 'v3-%' AND scenario='G' AND split='test' ORDER BY id LIMIT 24")->fetchAll(PDO::FETCH_COLUMN);
    for($i=0;$i<$count;$i++) {
        $elapsed=match($scenario) { 'A1'=>(int)round(($count-1-$i)*1200/($count-1)), 'A2'=>($count-1-$i)*8, 'A3'=>($count-1-$i)*43200, 'A4'=>($count-1-$i)*20, default=>($count-1-$i)*1800 };
        $created=$now-$elapsed;
        $age=match($scenario) { 'A3'=>(400+$i)*86400, 'N1','N2'=>(120+$i)*86400, 'A2'=>3600+$i*20, default=>120+$i*15 };
        query('INSERT INTO users(email,name,password_hash,created_at) VALUES (?,?,?,?)',['attack-'.$batch.'-'.$i.'@dataset.invalid',"Simulation $scenario ".($i+1),$password,gmdate('Y-m-d H:i:s',$created-$age)]);
        $uid=(int)db()->lastInsertId();
        // Documentation-only IPv4/IPv6 ranges, persisted solely as HMACs and masked prefixes.
        $ip=match($scenario) { 'A1'=>'192.0.2.'.(10+$i%5), 'A2'=>'198.51.100.'.(20+$i%3), 'A4'=>'203.0.113.'.(20+$i), 'N1'=>'192.0.2.240', default=>'2001:db8:'.dechex(100+$i).'::20' };
        $body=match($scenario) { 'A1'=>'Absolutely perfect product, amazing value, five stars. Buy it today!', 'A2'=>$negative[$i%4], 'A3'=>$praise[$i%6].' '.['The pairing process was straightforward.','I mostly use it while working from home.','It has become part of my daily routine.','Delivery was prompt and the packaging was intact.'][intdiv($i,6)%4], 'A4'=>$praise[$i%3], default=>$praise[$i%6].' '.['I tried it on a morning walk.','My first test was a podcast at home.','I compared the settings during an evening call.','The manual explained the initial setup clearly.'][intdiv($i,6)%4] };
        if(str_starts_with($scenario,'N')&&count($benignTexts)>=24) $body=(string)$benignTexts[$i];
        $rating=$scenario==='A2'?1:($scenario==='N1'?3+$i%3:5);
        query("INSERT INTO reviews(product_id,user_id,rating,title,body,ip_hash,ip_prefix,user_agent,created_at,is_synthetic,true_label,scenario,split) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,'demo')",[$product,$uid,$rating,"Synthetic $scenario · ".($i+1),$body,ipHash($ip),ipPrefix($ip),['Chrome/120','Safari/17','Firefox/121'][$i%3],gmdate('Y-m-d H:i:s',$created),str_starts_with($scenario,'N')?'0':'1',$scenario]);
        $id=(int)db()->lastInsertId(); enqueue($id,1);
        query("INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,'inject','pending_score',?)",[$admin,$id,$reason]);
    }
    return $count;
}
function resetDemo(int $admin, int $product, string $reason): int {
    if(envv('DEMO_MODE')!=='1') { http_response_code(403); throw new RuntimeException('Demo reset is disabled.'); }
    if($product<1||!query('SELECT id FROM products WHERE id=?',[$product])->fetch()) throw new RuntimeException('Choose a valid product to reset.');
    // Lock review rows in the same order as writers. Injection audit is provenance,
    // so even a mislabeled imported/user row cannot enter this reset boundary.
    $rows=query("SELECT r.id,r.status FROM reviews r WHERE r.product_id=? AND r.is_synthetic=1 AND r.split='demo' AND r.source_id IS NULL AND r.status<>'deleted' AND EXISTS (SELECT 1 FROM admin_actions a WHERE a.review_id=r.id AND a.action='inject') ORDER BY r.id FOR UPDATE",[$product])->fetchAll();
    if(!$rows) throw new RuntimeException('No active button-injected demo reviews for this product. Nothing was changed.');
    foreach($rows as $row) {
        query("UPDATE reviews SET status='deleted',revision=revision+1 WHERE id=?",[$row['id']]);
        query('DELETE FROM scoring_queue WHERE review_id=?',[$row['id']]);
        query('DELETE FROM review_scores WHERE review_id=?',[$row['id']]);
        // Existing ENUM supports remove; explicit reset reason retains a per-review event.
        query("INSERT INTO admin_actions(admin_id,review_id,action,previous_status,reason) VALUES (?,?,'remove',?,?)",[$admin,$row['id'],$row['status'],'DEMO RESET: '.substr($reason,0,488)]);
    }
    return count($rows);
}
function demoProductNames(): array {
    return ['Aurora Wireless Headphones','Pulse Portable Speaker','Echo Studio Earbuds','Nova USB Microphone','Orbit Gaming Headset','Atlas Mechanical Keyboard','Vista HD Webcam','Volt USB-C Charging Hub'];
}
function refreshDemoProductNames(): void {
    foreach(demoProductNames() as $i=>$name) query('UPDATE products SET name=?,description=? WHERE slug=?',[$name,'Illustrative electronics product. UCI research text is reused with simulated accounts and activity; it is not a review of this product or a verified purchase.','dataset-'.substr(hash('sha256','product-'.$i),0,32)]);
}
