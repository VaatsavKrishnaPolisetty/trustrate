<?php
// Load only the generated, private local configuration, never project .env files.
declare(strict_types=1);
if(PHP_SAPI!=='cli') exit;
$file=__DIR__.'/.local/compose.env';
if(!is_file($file)) { fwrite(STDERR,"Run php db/setup.php first.\n"); exit(1); }
foreach(file($file,FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) as $line) {
    [$key,$value]=explode('=',$line,2); if(getenv($key)===false) putenv($key.'='.$value);
}
$command=$argv[1]??'';
if(in_array($command,['init','import','score-worker','backfill','activate-dataset'],true)) { array_splice($argv,1,1); require __DIR__.'/'.$command.'.php'; }
elseif($command==='serve') { passthru(escapeshellarg(PHP_BINARY).' -S '.escapeshellarg(getenv('WEB_LISTEN')?:'127.0.0.1:8080').' -t '.escapeshellarg(__DIR__.'/../web'),$code); exit($code); }
else { fwrite(STDERR,"Usage: php db/run.php init|import|score-worker [--once]|serve\n"); exit(1); }
