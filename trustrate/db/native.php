<?php
// Explicitly starts only a dedicated development instance, never the host's server.
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
$action=$argv[1]??'';
if(!in_array($action,['start','stop'],true)) { fwrite(STDERR,"Usage: php db/native.php start|stop\nDedicated development MySQL on 127.0.0.1:13306; data stays in db/.local/mysql.\n"); exit(1); }
umask(0077);
$local=__DIR__.'/.local'; $data=$local.'/mysql'; $socket=$local.'/mysql.sock'; $pid=$local.'/mysql.pid';
if($action==='stop') {
    if(!is_file($local.'/compose.env')||!is_file($pid)||!file_exists($socket)) { fwrite(STDERR,"No running dedicated instance found; nothing changed.\n"); exit(1); }
    $settings=[]; foreach(file($local.'/compose.env',FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) as $line) { [$k,$v]=explode('=',$line,2); $settings[$k]=$v; }
    try {
        $connection=new PDO('mysql:unix_socket='.$socket,'root',$settings['DB_ROOT_PASSWORD'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
        if(rtrim((string)$connection->query('SELECT @@datadir')->fetchColumn(),'/')!==$data) throw new RuntimeException('Not the dedicated data directory');
        $connection->exec('SHUTDOWN'); fwrite(STDOUT,"Dedicated MySQL stopped; its data is retained.\n");
    } catch(Throwable $e) { fwrite(STDERR,"Could not safely stop the dedicated instance; nothing else was changed.\n"); exit(1); }
    exit;
}
if(!is_dir($local)) mkdir($local,0700,true);
if(!is_file($local.'/compose.env')) { putenv('DB_PORT=13306'); require __DIR__.'/setup.php'; }
$settings=[]; foreach(file($local.'/compose.env',FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) as $line) { [$k,$v]=explode('=',$line,2); $settings[$k]=$v; }
if(($settings['DB_PORT']??'')!=='13306') { fwrite(STDERR,"Existing generated configuration uses a different port; left unchanged. Set DB_PORT=13306 in that private file before dedicated startup.\n"); exit(1); }
if(is_file($pid)) { fwrite(STDERR,"Dedicated instance has a PID file. Verify it before another startup; nothing changed.\n"); exit(1); }
$binary=trim((string)shell_exec('command -v mysqld')); if($binary==='') { fwrite(STDERR,"Install native MySQL first.\n"); exit(1); }
$new=!is_dir($data); if($new) mkdir($data,0700);
$base=escapeshellarg($binary).' --no-defaults --datadir='.escapeshellarg($data);
if($new) { exec($base.' --initialize-insecure > '.escapeshellarg($local.'/mysql-init.log').' 2>&1',$output,$code); if($code!==0) { fwrite(STDERR,"Dedicated MySQL initialization failed; inspect db/.local/mysql-init.log.\n"); exit(1); } }
exec($base.' --bind-address=127.0.0.1 --port=13306 --socket='.escapeshellarg($socket).' --pid-file='.escapeshellarg($pid).' --mysqlx=OFF --log-error='.escapeshellarg($local.'/mysql.log').' > /dev/null 2>&1 &');
$connection=null;
for($i=0;$i<60;$i++) {
    try { $connection=new PDO('mysql:unix_socket='.$socket,'root',$new?'':$settings['DB_ROOT_PASSWORD'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]); break; } catch(Throwable $e) { usleep(500000); }
}
if(!$connection) { fwrite(STDERR,"Dedicated startup failed; inspect db/.local/mysql.log. Existing host MySQL was not changed.\n"); exit(1); }
if($new) $connection->exec("ALTER USER 'root'@'localhost' IDENTIFIED BY ".$connection->quote($settings['DB_ROOT_PASSWORD']));
fwrite(STDOUT,"Dedicated MySQL ready on 127.0.0.1:13306. Credentials remain only in db/.local/compose.env.\nRun php db/run.php init. This instance does not change the existing MySQL service.\n");
