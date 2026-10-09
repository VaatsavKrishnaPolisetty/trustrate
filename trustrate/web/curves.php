<?php
// Draw only numeric data from the held-out evaluation artifact; no CDN/scripts.
function evaluationCurve(array $testRows, string $model, string $kind): string {
    $rows=array_values(array_filter($testRows,fn($r)=>isset($r['scores'][$model],$r['true_label'])&&is_numeric($r['scores'][$model])));
    usort($rows,fn($a,$b)=>(float)$b['scores'][$model]<=>(float)$a['scores'][$model]);
    $positives=count(array_filter($rows,fn($r)=>(int)$r['true_label']===1)); $negatives=count($rows)-$positives;
    if(!$positives||!$negatives) return '';
    $tp=0; $fp=0; $points=$kind==='roc'?[[0,0]]:[[0,1]];
    foreach($rows as $i=>$row) {
        if((int)$row['true_label']===1) $tp++; else $fp++;
        // Threshold ties are stepped together, not artificially rank-ordered.
        if(isset($rows[$i+1])&&(float)$rows[$i+1]['scores'][$model]===(float)$row['scores'][$model]) continue;
        $points[]=$kind==='roc'?[$fp/$negatives,$tp/$positives]:[$tp/$positives,$tp/($tp+$fp)];
    }
    return implode(' ',array_map(fn($p)=>number_format(44+320*$p[0],2,'.','').','.number_format(230-200*$p[1],2,'.',''),$points));
}
function renderEvaluationChart(array $testRows,string $kind): void {
    $title=$kind==='roc'?'Receiver operating characteristic':'Precision–recall';
    $x=$kind==='roc'?'False-positive rate':'Recall'; $y=$kind==='roc'?'Recall':'Precision';
    $colors=['isolation_forest'=>'#236b4b','classical_ocsvm'=>'#945420','quantum_ocsvm'=>'#7051a1','hybrid'=>'#126594'];
    echo '<svg role="img" aria-label="'.esc($title).' on held-out test data" viewBox="0 0 400 280" style="width:100%;height:auto">';
    echo '<path d="M44 30V230H364" fill="none" stroke="#52625a"/><path d="M44 130H364 M204 30V230" stroke="#dce3dd" stroke-dasharray="4 4"/>';
    foreach($colors as $key=>$color) echo '<polyline fill="none" stroke="'.$color.'" stroke-width="2" points="'.esc(evaluationCurve($testRows,$key,$kind)).'"/>';
    echo '<g fill="#52625a" font-size="12"><text x="36" y="247">0</text><text x="358" y="247">1</text><text x="23" y="35">1</text><text x="155" y="270">'.esc($x).'</text><text x="3" y="20">'.esc($y).'</text></g></svg>';
    echo '<p>Green: Isolation Forest · brown: classical OCSVM · purple: quantum OCSVM · blue: hybrid</p>';
}
