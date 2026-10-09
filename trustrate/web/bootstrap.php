<?php
declare(strict_types=1);
function envv(string $key, string $default = ''): string { return getenv($key) !== false ? (string)getenv($key) : $default; }
function db(): PDO {
    static $db;
    if (!$db) {
        $db = new PDO('mysql:host='.envv('DB_HOST','127.0.0.1').';port='.envv('DB_PORT','3306').';dbname='.envv('DB_NAME','trustrate').';charset=utf8mb4',envv('DB_USER','trustrate_app'),envv('DB_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,PDO::ATTR_EMULATE_PREPARES=>false]);
        $db->exec("SET time_zone = '+00:00'");
    }
    return $db;
}
function query(string $sql, array $args = []): PDOStatement { $s=db()->prepare($sql); $s->execute($args); return $s; }
function esc(mixed $v): string { return htmlspecialchars((string)$v, ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'); }
function ipHash(?string $ip = null): string {
    $key=envv('IP_HASH_KEY'); if(strlen($key)<32) throw new RuntimeException('IP_HASH_KEY must be configured');
    // Forwarded headers are intentionally ignored: trust only the direct peer.
    return hash_hmac('sha256',$ip ?? ($_SERVER['REMOTE_ADDR']??'cli'),$key);
}
function ipPrefix(?string $ip = null): string {
    $packed=@inet_pton($ip ?? ($_SERVER['REMOTE_ADDR']??''));
    if($packed===false) return '';
    if(strlen($packed)===4) return inet_ntop(substr($packed,0,3)."\0").'/24';
    return inet_ntop(substr($packed,0,6).str_repeat("\0",10)).'/48';
}
function rollback(): void { try { if(db()->inTransaction()) db()->rollBack(); } catch(Throwable $ignored) {} }
function safeError(Throwable $e): string { return $e instanceof PDOException || !($e instanceof RuntimeException) ? 'The request could not be completed. Please try again later.' : $e->getMessage(); }
function limitRate(string $kind, int $maximum, int $seconds): void {
    $now=time(); $window=intdiv($now,$seconds)*$seconds;
    $bucket=hash('sha256',$kind.'|'.ipHash().'|'.$window);
    query('INSERT INTO rate_limits(bucket,hits,expires_at) VALUES (?,1,?) ON DUPLICATE KEY UPDATE hits=hits+1',[$bucket,$window+$seconds]);
    if((int)query('SELECT hits FROM rate_limits WHERE bucket=?',[$bucket])->fetchColumn()>$maximum) { http_response_code(429); throw new RuntimeException('Too many requests. Please try again later.'); }
}
function currentUser(): ?array {
    return isset($_SESSION['uid']) ? (query('SELECT id,name,email,role FROM users WHERE id=?',[$_SESSION['uid']])->fetch()?:null) : null;
}
function csrfField(): string { return '<input type="hidden" name="csrf" value="'.esc($_SESSION['csrf']).'">'; }
function requireCsrf(): void {
    if(!is_string($_POST['csrf']??null)||!hash_equals($_SESSION['csrf'],$_POST['csrf'])) { http_response_code(403); throw new RuntimeException('Invalid form token. Reload the page.'); }
}
function enqueue(int $id,int $revision): void {
    query('DELETE FROM review_scores WHERE review_id=?',[$id]);
    query('INSERT INTO scoring_queue(review_id,revision) VALUES (?,?) ON DUPLICATE KEY UPDATE revision=VALUES(revision),attempts=0,available_at=CURRENT_TIMESTAMP,locked_until=NULL,last_error=NULL',[$id,$revision]);
}
if(PHP_SAPI !== 'cli') {
    ini_set('display_errors','0'); ini_set('session.use_strict_mode','1'); ini_set('session.use_only_cookies','1');
    session_set_cookie_params(['httponly'=>true,'secure'=>envv('COOKIE_SECURE','0')==='1'||(!empty($_SERVER['HTTPS'])&&$_SERVER['HTTPS']!=='off'),'samesite'=>'Lax','path'=>'/']);
    session_start();
    if(isset($_SESSION['uid']) && (time()-($_SESSION['last_seen']??0)>1800 || time()-($_SESSION['signed_in']??0)>43200)) { $_SESSION=[]; session_regenerate_id(true); }
    $_SESSION['last_seen']=time(); $_SESSION['csrf'] ??= bin2hex(random_bytes(32));
    header('X-Content-Type-Options: nosniff'); header('X-Frame-Options: DENY'); header('Referrer-Policy: same-origin');
    header("Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
    header('Cache-Control: no-store');
}
