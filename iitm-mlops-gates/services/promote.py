from shared.common import *

def process(req):
    if not isinstance(req,dict) or not isinstance(req.get('policy'),dict) or not isinstance(req.get('versions'),list) or not isinstance(req.get('championVersion'),str):return {'error':'INVALID_INPUT'},400
    p=req['policy']; rc_global=[]
    asof=parse_instant(req.get('asOf')); digests=[p.get('datasetDigest'),p.get('schemaDigest')]
    if asof is None:rc_global.append('INVALID_TIMESTAMP')
    if any(not isinstance(x,str) or not x for x in digests):rc_global.append('INVALID_POLICY')
    for k in ('maxAgeSeconds','maxSizeBytes'):
        if not safe_int(p.get(k)):rc_global.append('INVALID_POLICY')
    for k in ('accuracyFloor','minImprovement'):
        if not finite_range01(p.get(k)):rc_global.append('INVALID_POLICY')
    if not finite_num(p.get('maxLatencyMs')) or p['maxLatencyMs']<0:rc_global.append('INVALID_POLICY')
    versions=req['versions']; seen=set(); entries=[]
    for v in versions:
        r=[]; vid=v.get('version') if isinstance(v,dict) else None
        if not isinstance(vid,str) or not re.fullmatch(r'[1-9]\d*',vid) or not safe_int(int(vid),True):r.append('INVALID_VERSION')
        if isinstance(vid,str) and vid in seen:r.append('DUPLICATE_VERSION')
        if isinstance(vid,str):seen.add(vid)
        ev=v.get('evaluation') if isinstance(v,dict) else None
        if not isinstance(ev,dict):r.append('MISSING_EVALUATION')
        if isinstance(ev,dict):
            for k in ('accuracy','latencyMs','sizeBytes'):
                if not finite_num(ev.get(k)):r.append('NON_FINITE')
            if finite_num(ev.get('accuracy')) and not 0<=ev['accuracy']<=1:r.append('METRIC_RANGE')
            ct=parse_instant(ev.get('createdAt'))
            if ct is None:r.append('INVALID_TIMESTAMP')
            elif asof:
                if ct>asof:r.append('FUTURE_EVALUATION')
                elif (asof-ct).total_seconds()>p['maxAgeSeconds']:r.append('STALE_EVALUATION')
            if ev.get('artifactDigest')!=v.get('artifactDigest'):r.append('ARTIFACT_MISMATCH')
            if ev.get('datasetDigest')!=p.get('datasetDigest'):r.append('DATASET_MISMATCH')
            if ev.get('schemaDigest')!=p.get('schemaDigest'):r.append('SCHEMA_MISMATCH')
            if finite_num(ev.get('accuracy')) and ev['accuracy']<p.get('accuracyFloor',0):r.append('ACCURACY_FLOOR')
            if finite_num(ev.get('latencyMs')) and ev['latencyMs']>p.get('maxLatencyMs',float('inf')):r.append('LATENCY_LIMIT')
            if safe_int(ev.get('sizeBytes')) and ev['sizeBytes']>p.get('maxSizeBytes',SAFE_MAX):r.append('SIZE_LIMIT')
            for n,f in (p.get('requiredSlices') or {}).items():
                if not isinstance(ev.get('slices'),dict) or n not in ev['slices']:r.append('MISSING_SLICE:'+n)
                elif not finite_range01(ev['slices'][n]):r.append('SLICE_RANGE:'+n)
                elif ev['slices'][n]<f:r.append('SLICE_FLOOR:'+n)
        entries.append((v,codes(r)))
    eligible=[v for v,r in entries if not r]
    eligible=sorted(eligible,key=lambda v:(-v['evaluation']['accuracy'],v['evaluation']['latencyMs'],v['evaluation']['sizeBytes'],int(v['version'])))
    lookup={v.get('version'): (v,r) for v,r in entries if isinstance(v,dict) and isinstance(v.get('version'),str)}
    champ=req['championVersion']; champion=lookup.get(champ)
    if not champion or champion[1] or rc_global:
        action='block'; selected=None; ev=None
    else:
        selected=eligible[0]['version'] if eligible else champ; ev=lookup.get(selected,(None,[]))[0]['evaluation'] if selected else None
        delta=round(eligible[0]['evaluation']['accuracy']-champion[0]['evaluation']['accuracy'],12) if eligible else 0
        action='promote' if eligible and selected!=champ and delta>=p['minImprovement'] else 'retain'
        if action=='retain':selected=champ;ev=champion[0]['evaluation']
    failed={v.get('version'):r for v,r in entries if r and isinstance(v,dict) and isinstance(v.get('version'),str)}
    resp={'action':action,'championVersion':champ,'selectedVersion':selected,'eligibleVersions':[v['version'] for v in eligible],'failedGates':failed,'aliasMutation':{'alias':'champion','version':selected} if action=='promote' else None,'evidence':ev}
    return resp,200
