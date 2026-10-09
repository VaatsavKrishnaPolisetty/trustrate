<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
require __DIR__.'/../web/bootstrap.php';
try {
    $name=envv('DB_NAME','trustrate'); $app=envv('DB_USER','trustrate_app'); $reader=envv('DB_READONLY_USER','trustrate_reader');
    foreach([$name,$app,$reader] as $identifier) if(!preg_match('/^[a-zA-Z0-9_]+$/D',$identifier)) throw new RuntimeException('Invalid database identifier');
    if($app===$reader||in_array('root',[$app,$reader],true)) throw new RuntimeException('Separate non-root application and reader accounts are required');
    foreach(['DB_ROOT_PASSWORD','DB_PASSWORD','DB_READONLY_PASSWORD','ADMIN_PASSWORD','IP_HASH_KEY'] as $key) if(strlen(envv($key))<12) throw new RuntimeException('Missing setup configuration: '.$key);
    $root=new PDO('mysql:host='.envv('DB_HOST','127.0.0.1').';port='.envv('DB_PORT','3306').';charset=utf8mb4',envv('DB_ROOT_USER','root'),envv('DB_ROOT_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $root->exec("CREATE DATABASE IF NOT EXISTS `$name` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
    $root->exec("USE `$name`");
    $root->exec(file_get_contents(__DIR__.'/schema.sql'));
    foreach([[$app,envv('DB_PASSWORD')],[$reader,envv('DB_READONLY_PASSWORD')]] as [$account,$password]) {
        $identity=$root->quote($account)."@'%'";
        $root->exec('CREATE USER IF NOT EXISTS '.$identity.' IDENTIFIED BY '.$root->quote($password));
        $root->exec('ALTER USER '.$identity.' IDENTIFIED BY '.$root->quote($password));
        $root->exec('REVOKE ALL PRIVILEGES, GRANT OPTION FROM '.$identity);
    }
    $root->exec("GRANT SELECT,INSERT,UPDATE,DELETE ON `$name`.* TO ".$root->quote($app)."@'%'");
    // The scoring process can read source data, never mutate application state.
    foreach(['users','products','reviews','review_scores'] as $table) $root->exec("GRANT SELECT ON `$name`.`$table` TO ".$root->quote($reader)."@'%'");
    $email=envv('ADMIN_EMAIL','admin@trustrate.local');
    if(!filter_var($email,FILTER_VALIDATE_EMAIL)) throw new RuntimeException('Invalid administrator email');
    $s=$root->prepare("INSERT IGNORE INTO users(email,name,password_hash,role) VALUES (?, 'Administrator', ?, 'admin')");
    $s->execute([$email,password_hash(envv('ADMIN_PASSWORD'),PASSWORD_DEFAULT)]);
    fwrite(STDOUT,"Schema, least-privilege database accounts, product, and administrator initialized. Existing accounts retain their passwords.\n");
} catch(Throwable $e) { fwrite(STDERR,"Initialization failed. Check database availability and local setup configuration.\n"); exit(1); }
