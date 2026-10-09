<?php
// Server-to-server requests only: the scoring key never enters browser JavaScript.
function modelJobRequest(string $path, ?array $payload=null): array {
    $curl=curl_init(rtrim(envv('SCORING_URL','http://127.0.0.1:8001'),'/').$path);
    $options=[CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>3,CURLOPT_TIMEOUT=>8,CURLOPT_HTTPHEADER=>['Content-Type: application/json','X-API-Key: '.envv('SCORING_API_KEY')]];
    if($payload!==null) { $options[CURLOPT_POST]=true; $options[CURLOPT_POSTFIELDS]=json_encode($payload,JSON_THROW_ON_ERROR); }
    curl_setopt_array($curl,$options); $body=curl_exec($curl); $code=curl_getinfo($curl,CURLINFO_HTTP_CODE); unset($curl);
    if($body===false||!in_array($code,[200,202],true)) throw new RuntimeException('Experiment service unavailable or request rejected. Inspect the recent receipts before submitting again.');
    $data=json_decode($body,true,64,JSON_THROW_ON_ERROR);
    if(!is_array($data)) throw new RuntimeException('Invalid experiment receipt.');
    return $data;
}
function recentModelJobs(): array {
    $paths=glob(dirname(__DIR__).'/.runtime/jobs/job_*.json')?:[];
    usort($paths,fn($a,$b)=>filemtime($b)<=>filemtime($a));
    $result=[];
    foreach(array_slice($paths,0,10) as $path) {
        if(filesize($path)>500000) continue;
        $data=json_decode(file_get_contents($path),true);
        if(is_array($data)&&preg_match('/^job_[a-f0-9]{32}$/D',(string)($data['job_id']??''))) $result[]=$data;
    }
    return $result;
}
