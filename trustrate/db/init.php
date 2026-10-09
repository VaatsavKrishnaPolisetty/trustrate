<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require __DIR__.'/../web/bootstrap.php';
try {
    $name=envv('DB_NAME','trustrate'); $app=envv('DB_USER','trustrate_app'); $reader=envv('DB_READONLY_USER','trustrate_reader');
    if($name!=='trustrate') throw new RuntimeException('Initialization is restricted to the trustrate database.');
    foreach([$app,$reader] as $identifier) if(!preg_match('/^trustrate_[a-zA-Z0-9_]+$/D',$identifier)) throw new RuntimeException('Database users must have the trustrate_ prefix.');
    if($app===$reader) throw new RuntimeException('Separate application and reader accounts are required.');
    foreach(['DB_PASSWORD','DB_READONLY_PASSWORD','ADMIN_PASSWORD','IP_HASH_KEY','SCORING_API_KEY'] as $key) if(strlen(envv($key))<16) throw new RuntimeException('Missing setup configuration: '.$key);
    $host=envv('DB_ACCOUNT_HOST','localhost');
    if(!in_array($host,['localhost','127.0.0.1','%'],true)) throw new RuntimeException('Invalid account host.');
    $dsn=envv('DB_SOCKET')!==''?'mysql:unix_socket='.envv('DB_SOCKET'):'mysql:host='.envv('DB_HOST','127.0.0.1').';port='.envv('DB_PORT','3306');
    $root=new PDO($dsn.';charset=utf8mb4',envv('DB_ROOT_USER','root'),envv('DB_ROOT_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    // Reuse only authenticated, already least-privilege accounts. Never alter them.
    $existing=[];
    foreach([$app,$reader] as $account) {
        $s=$root->prepare('SELECT COUNT(*) FROM mysql.user WHERE User=? AND Host=?'); $s->execute([$account,$host]);
        if($s->fetchColumn()) {
            $check=new PDO($dsn.';charset=utf8mb4',$account,envv($account===$app?'DB_PASSWORD':'DB_READONLY_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
            $grants=$root->query('SHOW GRANTS FOR '.$root->quote($account).'@'.$root->quote($host))->fetchAll(PDO::FETCH_COLUMN);
            foreach($grants as $grant) {
                if(str_starts_with($grant,'GRANT USAGE ON *.* TO ')) continue;
                $allowed=$account===$app?'SELECT, INSERT, UPDATE, DELETE':'SELECT';
                if(!str_starts_with($grant,'GRANT '.$allowed.' ON `trustrate`.')||str_contains($grant,'WITH GRANT OPTION')) throw new RuntimeException('Existing account has unexpected grants; left unchanged. Use fresh trustrate_-prefixed accounts.');
            }
            $existing[$account]=true;
        }
    }
    $root->exec("CREATE DATABASE IF NOT EXISTS `$name` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
    $root->exec("USE `$name`"); $root->exec(file_get_contents(__DIR__.'/schema.sql'));
    // Additive migration for the original TrustRate schema only.
    $root->exec("ALTER TABLE reviews MODIFY status ENUM('pending_score','published','flagged','watch','removed','restored','deleted') NOT NULL DEFAULT 'pending_score'");
    $columns=['ip_prefix'=>"VARCHAR(64) NOT NULL DEFAULT ''",'user_agent'=>"VARCHAR(512) NOT NULL DEFAULT ''",'is_synthetic'=>'BOOLEAN NOT NULL DEFAULT FALSE','true_label'=>'VARCHAR(40) NULL','scenario'=>'VARCHAR(80) NULL','split'=>'VARCHAR(20) NULL','source_id'=>'VARCHAR(100) NULL UNIQUE'];
    foreach($columns as $column=>$type) {
        $s=$root->prepare('SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=? AND table_name=? AND column_name=?'); $s->execute([$name,'reviews',$column]);
        if(!$s->fetchColumn()) $root->exec("ALTER TABLE reviews ADD COLUMN `$column` $type");
    }
    $s=$root->query("SHOW COLUMNS FROM review_scores LIKE 'ibm_job_id'"); if(!$s->fetch()) $root->exec('ALTER TABLE review_scores ADD COLUMN ibm_job_id VARCHAR(255) NULL');
    $root->exec("ALTER TABLE admin_actions MODIFY action ENUM('remove','restore','watch','inject') NOT NULL");
    $root->exec("UPDATE reviews r LEFT JOIN review_scores s ON s.review_id=r.id AND s.review_revision=r.revision SET r.status='pending_score' WHERE r.status='published' AND s.review_id IS NULL");
    $root->exec("INSERT IGNORE INTO scoring_queue(review_id,revision) SELECT id,revision FROM reviews WHERE status='pending_score'");
    foreach([[$app,envv('DB_PASSWORD')],[$reader,envv('DB_READONLY_PASSWORD')]] as [$account,$password]) if(!isset($existing[$account])) $root->exec('CREATE USER '.$root->quote($account).'@'.$root->quote($host).' IDENTIFIED BY '.$root->quote($password));
    if(!isset($existing[$app])) $root->exec("GRANT SELECT,INSERT,UPDATE,DELETE ON `$name`.* TO ".$root->quote($app).'@'.$root->quote($host));
    if(!isset($existing[$reader])) foreach(['users','products','reviews','review_scores'] as $table) $root->exec("GRANT SELECT ON `$name`.`$table` TO ".$root->quote($reader).'@'.$root->quote($host));
    $email=envv('ADMIN_EMAIL','admin@trustrate.local');
    if(!filter_var($email,FILTER_VALIDATE_EMAIL)) throw new RuntimeException('Invalid administrator email');
    $s=$root->prepare("INSERT IGNORE INTO users(email,name,password_hash,role) VALUES (?, 'Administrator', ?, 'admin')"); $s->execute([$email,password_hash(envv('ADMIN_PASSWORD'),PASSWORD_DEFAULT)]);
    fwrite(STDOUT,"TrustRate schema and least-privilege accounts initialized. Existing accounts and administrators retain their passwords.\n");
} catch(Throwable $e) { fwrite(STDERR,($e instanceof PDOException?'Initialization failed; check database availability and privileges.':$e->getMessage())."\n"); exit(1); }
