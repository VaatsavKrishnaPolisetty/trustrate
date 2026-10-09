<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
$dir=__DIR__.'/.local';
if(!is_dir($dir)&&!mkdir($dir,0700,true)) throw new RuntimeException('Cannot create local configuration directory');
$path=$dir.'/compose.env';
if(file_exists($path)) { fwrite(STDOUT,"Local configuration already exists; left unchanged.\n"); exit; }
umask(0077);
$settings=['DB_NAME'=>'trustrate','DB_HOST'=>'127.0.0.1','DB_PORT'=>getenv('DB_PORT')?:'3306','DB_ROOT_PASSWORD'=>bin2hex(random_bytes(24)), 'DB_USER'=>'trustrate_app','DB_PASSWORD'=>bin2hex(random_bytes(24)), 'DB_READONLY_USER'=>'trustrate_reader','DB_READONLY_PASSWORD'=>bin2hex(random_bytes(24)), 'IP_HASH_KEY'=>bin2hex(random_bytes(32)), 'SCORING_API_KEY'=>bin2hex(random_bytes(32)), 'ADMIN_EMAIL'=>'admin@trustrate.local','ADMIN_PASSWORD'=>bin2hex(random_bytes(16))];
$f=fopen($path,'x'); if(!$f) throw new RuntimeException('Cannot create local configuration');
foreach($settings as $key=>$value) fwrite($f,$key.'='.$value."\n");
fclose($f); chmod($path,0600);
fwrite(STDOUT,"Generated db/.local/compose.env (0600). Credentials are stored only there; open locally to obtain the administrator password.\n");
