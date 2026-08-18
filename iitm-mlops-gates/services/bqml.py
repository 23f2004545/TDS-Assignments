from shared.common import *

def process(req,db):
    if not isinstance(req,dict) or req.get('phase') not in ('select','evaluate') or not isinstance(req.get('runId'),str) or not req['runId'] or len(req['runId'])>128:return None,400
    if req['phase']=='select':
        run=req['runId']; existing=db.get('bqml',run)
        # Canonical replay identity is the complete request
        if existing:
            if existing['_input']==compact(req): return existing['response'],200
            return {'error':'RUN_ID_CONFLICT'},409
        rc=[]; rows=req.get('rows'); trials=req.get('trials'); limit=req.get('numTrialsLimit'); forbidden=req.get('forbiddenFeatures'); policy_ok=True
        if not isinstance(rows,list) or not rows: rc.append('INVALID_INPUT'); policy_ok=False
        if not isinstance(trials,list) or not safe_int(limit,True) or not isinstance(forbidden,list): rc.append('INVALID_INPUT'); policy_ok=False
        if isinstance(trials,list) and isinstance(limit,int) and len(trials)>limit: rc.append('TRIAL_LIMIT_EXCEEDED'); policy_ok=False
        retained={}; invalid_row=False
        if isinstance(rows,list):
            for r in rows:
                if not isinstance(r,dict) or set(r)!=set(['id','entity','eventTime','predictionTime','version','split','features']) or not isinstance(r.get('id'),str) or not isinstance(r.get('entity'),str) or parse_instant(r.get('eventTime')) is None or parse_instant(r.get('predictionTime')) is None or not safe_int(r.get('version')) or r.get('split') not in ('TRAIN','EVAL') or not isinstance(r.get('features'),dict): invalid_row=True; continue
                rr=dict(r); rr['eventTime']=norm_time(r['eventTime']); rr['predictionTime']=norm_time(r['predictionTime'])
                key=(rr['entity'],rr['eventTime']); old=retained.get(key)
                if old is None or (rr['version'],utf8key(rr['id']))>(old['version'],utf8key(old['id'])): retained[key]=rr
        if invalid_row: rc.append('INVALID_INPUT')
        feats=None
        if retained:
            common=set(next(iter(retained.values()))['features'])
            for r in retained.values(): common &= set(r['features'])
            feats=[]
            for f in common:
                if f in forbidden: continue
                ok=True
                for r in retained.values():
                    a=r['features'][f].get('availableAt') if isinstance(r['features'][f],dict) else None
                    if parse_instant(a) is None or parse_instant(a)>parse_instant(r['predictionTime']):ok=False
                if ok:feats.append(f)
            feats=sort_utf8(feats)
        eligible=[]
        if isinstance(trials,list):
            seen=set()
            for t in trials:
                if not isinstance(t,dict) or set(t)!=set(['trialId','status','evalMetric']) or not safe_int(t.get('trialId')) or t.get('trialId') in seen or t.get('status') not in ('SUCCEEDED','FAILED'): rc.append('INVALID_INPUT'); continue
                seen.add(t['trialId'])
                if t['status']=='SUCCEEDED' and finite_num(t['evalMetric']):eligible.append(t)
        if not eligible:rc.append('NO_SUCCESSFUL_TRIAL')
        sel=max(eligible,key=lambda t:(t['evalMetric'],-t['trialId'])) if eligible else None
        train=sort_utf8([r['id'] for r in retained.values() if r['split']=='TRAIN']); ev=sort_utf8([r['id'] for r in retained.values() if r['split']=='EVAL'])
        digest=sha256_hex({'trainRowIds':train,'evalRowIds':ev,'featureNames':feats}) if not rc or 'INVALID_INPUT' not in rc else None
        response={'runId':run,'selectedTrialId':sel['trialId'] if sel and 'INVALID_INPUT' not in rc else None,'trainRowIds':train if 'INVALID_INPUT' not in rc else [],'evalRowIds':ev if 'INVALID_INPUT' not in rc else [],'featureNames':feats if 'INVALID_INPUT' not in rc else [],'datasetDigest':digest,'reasonCodes':codes(rc)}
        db.put('bqml',run,{'_input':compact(req),'response':response}); return response,200
    stored=db.get('bqml',req['runId'])
    rc=[]
    if not stored or stored['response']['selectedTrialId'] is None or req.get('selectedTrialId')!=stored['response']['selectedTrialId'] or req.get('datasetDigest')!=stored['response']['datasetDigest']: rc.append('INVALID_LINEAGE')
    if not finite_range01(req.get('metricFloor')):rc.append('INVALID_INPUT')
    rs=req.get('requiredSlices'); rows=req.get('rows'); bp=req.get('bytesProcessed'); mb=req.get('maxBytes')
    if not isinstance(rs,dict) or not safe_int(bp) or not safe_int(mb):rc.append('INVALID_INPUT')
    test=None; slpass=False
    if not isinstance(rows,list) or not rows: rc.append('INVALID_TEST_ROW');
    else:
        vals=[]; slices={}
        for r in rows:
            if not isinstance(r,dict) or not isinstance(r.get('label'),int) or r.get('label') not in (0,1) or not isinstance(r.get('prediction'),int) or r.get('prediction') not in (0,1) or not isinstance(r.get('slice'),str) or not r['slice']:rc.append('INVALID_TEST_ROW');continue
            vals.append(r['label']==r['prediction']); slices.setdefault(r['slice'],[]).append(r['label']==r['prediction'])
        if not rc or 'INVALID_TEST_ROW' not in rc:
            test=round(sum(vals)/len(vals),12) if vals else None
            slpass=True
            for n,f in rs.items():
                if n not in slices:slpass=False;rc.append('MISSING_SLICE:'+n)
                elif round(sum(slices[n])/len(slices[n]),12)<f:slpass=False;rc.append('SLICE_FLOOR:'+n)
            if test is not None and test<req['metricFloor']:rc.append('AGGREGATE_FLOOR');slpass=False
    if isinstance(bp,int) and isinstance(mb,int) and bp>mb:rc.append('BYTE_LIMIT')
    if 'INVALID_INPUT' in rc or 'INVALID_LINEAGE' in rc or 'INVALID_TEST_ROW' in rc:slpass=False
    decision='admit' if not rc else 'reject'
    return {'runId':req['runId'],'selectedTrialId':req.get('selectedTrialId'),'datasetDigest':req.get('datasetDigest'),'testMetric':test,'criticalSlicePass':slpass,'decision':decision,'bytesProcessed':bp,'reasonCodes':codes(rc)},200
