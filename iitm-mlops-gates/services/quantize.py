from shared.common import *

def manifest(c):
    inv=[]
    if not isinstance(c,dict) or not isinstance(c.get('files'),dict) or not c['files'] or any(not isinstance(k,str) or not k or not isinstance(v,str) for k,v in c['files'].items()):return None
    for n,v in sorted(c['files'].items(),key=lambda x:utf8key(x[0])):inv.append({'name':n,'bytes':len(v.encode()),'sha256':sha256_hex_bytes(v.encode())})
    return inv,sum(x['bytes'] for x in inv),sha256_hex(inv)

def process(req,db):
    if not isinstance(req,dict) or req.get('phase') not in ('freeze','select'):return {'error':'INVALID_INPUT'},400
    if req['phase']=='freeze':
        fid=req.get('freezeId'); cands=req.get('candidates'); cal=req.get('calibrationDigest'); tok=req.get('tokenizerDigest'); allowed=req.get('allowedUnsupportedReasons')
        if not isinstance(fid,str) or not fid or len(fid)>128 or not isinstance(cands,list) or not isinstance(allowed,list) or not isinstance(cal,str) or not cal or not isinstance(tok,str) or not tok:return {'error':'INVALID_INPUT'},400
        old=db.get('quant',fid)
        if old:
            if old['_input']==compact(req):return old['response'],200
            return {'error':'FREEZE_ID_CONFLICT'},409
        out=[]
        for c in cands:
            rc=[]; m=manifest(c)
            if not m: inv=[];total=None;pd=None;rc.append('INVALID_INPUT')
            else: inv,total,pd=m
            ur=c.get('unsupportedReason');
            if ur is not None and ur not in allowed:rc.append('UNALLOWED_UNSUPPORTED_REASON')
            if not c.get('loadable'):rc.append('NOT_LOADABLE')
            if c.get('calibrationDigest')!=cal:rc.append('CALIBRATION_MISMATCH')
            if c.get('tokenizerDigest')!=tok:rc.append('TOKENIZER_MISMATCH')
            status='invalid' if rc else ('unsupported' if ur is not None else 'frozen')
            if m is None:inv=[];total=None;pd=None
            out.append({'name':c.get('name'),'status':status,'inventory':inv,'totalBytes':total,'packageDigest':pd,'reasonCodes':codes(rc)})
        out.sort(key=lambda x:utf8key(x['name']) if isinstance(x['name'],str) else b'')
        resp={'freezeId':fid,'candidates':out};db.put('quant',fid,{'_input':compact(req),'response':resp});return resp,200
    fid=req.get('freezeId'); stored=db.get('quant',fid) if isinstance(fid,str) else None
    if not stored or not isinstance(req.get('candidates'),list) or not isinstance(req.get('rows'),list) or not isinstance(req.get('policy'),dict):return {'error':'INVALID_INPUT'},400
    if req['candidates']!=stored['response']['candidates']: # exact JSON equality
        pass
    p=req['policy']; order=p.get('candidateOrder'); rows=req['rows']; lat=req.get('latencies')
    if not isinstance(order,list) or not isinstance(lat,dict) or not isinstance(p.get('requiredSlices'),dict):return {'error':'INVALID_INPUT'},400
    by={c['name']:c for c in stored['response']['candidates']}; results=[]
    for n in order:
        rc=[]; fr=by.get(n)
        if not fr:rc.append('NOT_FROZEN'); results.append({'name':n,'aggregate':None,'slices':{},'totalBytes':None,'latencyMs':None,'admitted':False,'reasonCodes':codes(rc)});continue
        inv=fr['inventory']; calc=sha256_hex(inv); total=sum(x['bytes'] for x in inv); valid_manifest=calc==fr['packageDigest'] and total==fr['totalBytes']
        if not valid_manifest:rc.append('INVALID_MANIFEST')
        if fr['status']!='frozen':rc.append('NOT_FROZEN')
        vals=[]; sl={}; predok=True
        for r in rows:
            pr=r.get('predictions',{}).get(n) if isinstance(r,dict) and isinstance(r.get('predictions'),dict) else None
            if not isinstance(r,dict) or r.get('label') not in (0,1) or pr not in (0,1) or not isinstance(r.get('slice'),str) or not r['slice']:predok=False;continue
            vals.append(r['label']==pr);sl.setdefault(r['slice'],[]).append(r['label']==pr)
        agg=round(sum(vals)/len(vals),12) if predok and vals else None; svals={k:round(sum(v)/len(v),12) for k,v in sl.items()} if predok else {}
        if not predok:rc.append('INVALID_PREDICTIONS')
        if agg is not None and agg<p.get('aggregateFloor',0):rc.append('AGGREGATE_FLOOR')
        for sn,f in p['requiredSlices'].items():
            if sn not in sl:rc.append('MISSING_SLICE:'+sn)
            elif svals[sn]<f:rc.append('SLICE_FLOOR:'+sn)
        lv=lat.get(n) if isinstance(lat,dict) else None
        if not finite_num(lv) or lv<0:lv=None;rc.append('INVALID_POLICY')
        if total>p.get('maxBytes',SAFE_MAX):rc.append('SIZE_LIMIT')
        if lv is not None and lv>p.get('maxLatencyMs',float('inf')):rc.append('LATENCY_LIMIT')
        results.append({'name':n,'aggregate':agg,'slices':svals,'totalBytes':total,'latencyMs':lv,'admitted':not rc,'reasonCodes':codes(rc)})
    winner=sorted([r for r in results if r['admitted']],key=lambda r:(r['totalBytes'],r['latencyMs'],order.index(r['name'])))[0] if any(r['admitted'] for r in results) else None
    return {'freezeId':fid,'selected':winner['name'] if winner else None,'results':results,'packageManifest':by[winner['name']] if winner else None},200
