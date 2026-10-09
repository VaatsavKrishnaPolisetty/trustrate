<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require_once __DIR__.'/../web/bootstrap.php';
$options=[];
for($i=1;$i<count($argv);$i++) {
    if(preg_match('/^--(file|split)=(.+)$/D',$argv[$i],$m)) $options[$m[1]]=$m[2];
    elseif(in_array($argv[$i],['--file','--split'],true)&&isset($argv[$i+1])) $options[substr($argv[$i],2)]=$argv[++$i];
    else { fwrite(STDERR,"Usage: php db/import.php [--file path.jsonl] [--split train|validation|test]\n"); exit(1); }
}
$path=$options['file']??(__DIR__.'/../data/reviews.jsonl'); $split=$options['split']??null;
function importDate(mixed $value): string {
    if(is_int($value)||is_float($value)) return gmdate('Y-m-d H:i:s',(int)$value);
    if(!is_string($value)||$value==='') throw new RuntimeException('Missing dataset timestamp.');
    return (new DateTimeImmutable($value,new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
}
try {
    $file=fopen($path,'r'); if(!$file) throw new RuntimeException('Dataset is unavailable.');
    $count=0; $skipped=0; $lineNo=0; $disabledPassword=password_hash(bin2hex(random_bytes(32)),PASSWORD_DEFAULT);
    while(($line=fgets($file))!==false) {
        $lineNo++; if(trim($line)==='') continue;
        $r=json_decode($line,true,64,JSON_THROW_ON_ERROR);
        if(!is_array($r)) throw new RuntimeException('Invalid dataset row.');
        if($split!==null&&($r['split']??null)!==$split) continue;
        $source=(string)($r['id']??$r['review_id']??''); $uid=(string)($r['user_id']??''); $pid=(string)($r['product_id']??'');
        if($source===''||strlen($source)>100||$uid===''||$pid==='') throw new RuntimeException('Canonical id, user_id and product_id are required.');
        if(query('SELECT id FROM reviews WHERE source_id=?',[$source])->fetch()) { $skipped++; continue; }
        $rating=filter_var($r['rating']??null,FILTER_VALIDATE_INT); $body=(string)($r['body']??''); $title=(string)($r['title']??('Synthetic review '.$source));
        if(!$rating||$rating<1||$rating>5||$title===''||strlen($title)>200||strlen($body)<1||strlen($body)>10000) throw new RuntimeException('Invalid canonical review content.');
        $created=importDate($r['created_at']??null); $account=importDate($r['account_created']??$r['account_created_at']??$created);
        $raw=$r['ip']??$r['ip_address']??null;
        $hash=$raw!==null?ipHash((string)$raw):(string)($r['ip_hash']??'');
        if(!preg_match('/^[a-f0-9]{64}$/D',$hash)) $hash=ipHash('synthetic:'.$uid);
        $prefix=$raw!==null?ipPrefix((string)$raw):ipPrefix(explode('/',(string)($r['ip_prefix']??''))[0]);
        // Preserve synthetic network grouping as a masked ULA /48, not as a raw identifier.
        if($prefix===''&&isset($r['ip_prefix'])) { $group=substr(hash('sha256',(string)$r['ip_prefix']),0,8); $prefix='fd00:'.substr($group,0,4).':'.substr($group,4,4).'::/48'; }
        db()->beginTransaction();
        $email='synthetic-'.hash('sha256',$uid).'@dataset.invalid';
        query("INSERT INTO users(email,name,password_hash,created_at) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE created_at=LEAST(created_at,VALUES(created_at))",[$email,'Synthetic '.substr($uid,0,70),$disabledPassword,$account]);
        $user=(int)query('SELECT id FROM users WHERE email=?',[$email])->fetchColumn();
        $slug='dataset-'.substr(hash('sha256',$pid),0,32);
        query('INSERT IGNORE INTO products(slug,name,description) VALUES (?,?,?)',[$slug,substr((string)($r['product_name']??('Dataset product '.$pid)),0,200),'Synthetic demonstration dataset; reviews are not real customer experiences.']);
        $product=(int)query('SELECT id FROM products WHERE slug=?',[$slug])->fetchColumn();
        query('INSERT INTO reviews(product_id,user_id,rating,title,body,ip_hash,ip_prefix,user_agent,revision,created_at,status,is_synthetic,true_label,scenario,split,source_id) VALUES (?,?,?,?,?,?,?,?,?,?,\'pending_score\',1,?,?,?,?)',[$product,$user,$rating,$title,$body,$hash,$prefix,substr((string)($r['user_agent']??''),0,512),max(1,(int)($r['revision']??1)),$created,isset($r['true_label'])?substr((string)$r['true_label'],0,40):null,isset($r['scenario'])?substr((string)$r['scenario'],0,80):null,isset($r['split'])?substr((string)$r['split'],0,20):null,$source]);
        enqueue((int)db()->lastInsertId(),max(1,(int)($r['revision']??1))); db()->commit(); $count++;
    }
    fclose($file); fwrite(STDOUT,"Imported $count synthetic reviews; skipped $skipped existing source IDs. All imported reviews queued for scoring.\n");
} catch(Throwable $e) { rollback(); fwrite(STDERR,'Import stopped at line '.($lineNo??0).': '.safeError($e)."\n"); exit(1); }
