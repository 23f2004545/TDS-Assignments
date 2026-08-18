from shared.common import *
DAG=['verify_data','prepare','train','evaluate','register','publish']
PAREN={'verify_data':None,'prepare':'verify_data','train':'prepare','evaluate':'train','register':'evaluate','publish':'register'}
INPUTS={'verify_data':['generation','checksum'],'prepare':['canonicalData','prepareCode','prepareConfig'],'train':['trainCode','trainConfig','runtime'],'evaluate':['canonicalData','evaluateCode','evaluateConfig'],'register':['schemaDigest'],'publish':['publishConfig']}
PARENT_ART={'prepare':'prepareArtifact','train':'prepareArtifact','evaluate':'trainArtifact','register':'evaluateArtifact','publish':'registerArtifact'}

def keys(inp):
    arts={}
    arts['verify_data']=sha256_hex([inp['generation'],inp['checksum']])
    arts['prepare']=sha256_hex([arts['verify_data'],inp['canonicalData'],inp['prepareCode'],inp['prepareConfig']])
    arts['train']=sha256_hex([arts['prepare'],inp['trainCode'],inp['trainConfig'],inp['runtime']])
    arts['evaluate']=sha256_hex([arts['train'],inp['canonicalData'],inp['evaluateCode'],inp['evaluateConfig']])
    arts['register']=sha256_hex([arts['evaluate'],inp['schemaDigest']])
    arts['publish']=sha256_hex([arts['register'],inp['publishConfig']])
    return arts

def process(req,db):
    if not isinstance(req,dict) or not isinstance(req.get('session'),str) or not req['session'] or not safe_int(req.get('revision'),True) or not isinstance(req.get('inputs'),dict) or not isinstance(req.get('events'),list):return {'error':'INVALID_REQUEST'},409
    s=req['session']; state=db.get('pipeline',s) or {'revision':None,'input':None,'events':{},'node':{},'seenEvents':{}}
    inp=req['inputs']; required=['generation','checksum','canonicalData','prepareCode','prepareConfig','trainCode','trainConfig','runtime','evaluateCode','evaluateConfig','schemaDigest','publishConfig']
    if any(not isinstance(inp.get(k),str) or not inp[k] for k in required):return {'error':'INVALID_REQUEST'},409
    if state['revision']==req['revision'] and state['input']!=compact(inp):return {'error':'REVISION_CONFLICT'},409
    if state['revision'] is not None and req['revision']<state['revision']:
        # older revisions are ignored; current state is read back
        return _response(state, req['revision'], inp, [], []), 200
    if state['revision']!=req['revision']:
        state['revision']=req['revision']; state['input']=compact(inp); state['node']={}
    kd=keys(inp)
    # restore reusable content-addressed cache entries
    for n in DAG:
        cached=db.get('pipeline_cache',f'{n}:{kd[n]}')
        if cached:
            state['node'][n]={'status':'succeeded','attempt':cached['attempt'],'artifactDigest':cached['artifactDigest'],'eventId':cached['eventId'],'key':kd[n]}
    accepted=[];ignored=[]
    for e in req['events']:
        if not isinstance(e,dict) or list(e.keys())!=['eventId','revision','node','attempt','status','key','artifactDigest','receiptId']:
            return {'error':'INVALID_EVENT'},409
        eid=e['eventId']; canonical=compact(e)
        seen=state['seenEvents'].get(eid)
        if seen:
            if seen!=canonical:return {'error':'EVENT_ID_CONFLICT'},409
            ignored.append(eid);continue
        if e['revision']!=req['revision'] or e['node'] not in DAG or not safe_int(e['attempt'],True) or e['status'] not in ('started','succeeded','retryable_failed','terminal_failed') or not isinstance(e['key'],str):
            ignored.append(eid);continue
        if e['status']=='succeeded' and (not isinstance(e['artifactDigest'],str) or not e['artifactDigest']):ignored.append(eid);continue
        if e['status']!='succeeded' and e['artifactDigest'] is not None:ignored.append(eid);continue
        if e['node'] in ('register','publish'):
            if e['status']=='succeeded' and e.get('receiptId')!=f"receipt:{e['node']}:{e['key']}":ignored.append(eid);continue
        elif e.get('receiptId') is not None:ignored.append(eid);continue
        if e['key']!=kd[e['node']]:ignored.append(eid);continue
        par=PAREN[e['node']]
        if par and state['node'].get(par,{}).get('status')!='succeeded':ignored.append(eid);continue
        prev=state['node'].get(e['node'])
        if prev is None:
            if e['status']!='started' or e['attempt']!=1:ignored.append(eid);continue
        elif prev['status']=='started':
            if e['attempt']!=prev['attempt'] or e['status'] not in ('succeeded','retryable_failed','terminal_failed'):return {'error':'STATUS_CONFLICT'},409
        elif prev['status']=='retryable_failed':
            if e['status']!='started' or e['attempt']!=prev['attempt']+1:return {'error':'STATUS_CONFLICT'},409
        elif prev['status']=='succeeded':
            if e['status']=='succeeded' and e.get('artifactDigest')!=prev.get('artifactDigest'):return {'error':'EVIDENCE_CONFLICT'},409
            return {'error':'STATUS_CONFLICT'},409
        else:return {'error':'STATUS_CONFLICT'},409
        state['node'][e['node']]={'status':e['status'],'attempt':e['attempt'],'artifactDigest':e.get('artifactDigest'),'eventId':eid,'key':e['key']}
        state['seenEvents'][eid]=canonical; accepted.append(eid)
        if e['status']=='succeeded':db.put('pipeline_cache',f"{e['node']}:{e['key']}",{'attempt':e['attempt'],'artifactDigest':e['artifactDigest'],'eventId':eid})
    db.put('pipeline',s,state)
    return _response(state,req['revision'],inp,accepted,ignored),200

def _response(state,revision,inp,accepted,ignored):
    kd=keys(inp); nodes=[]
    for n in DAG:
        st=state['node'].get(n)
        dep={k:inp[k] for k in INPUTS[n]}
        if PAREN[n]: dep[PARENT_ART[n]]=kd[PAREN[n]]
        dep['cacheKey']=kd[n]
        if st and st['status']=='succeeded':action='reuse';reason='CACHE_HIT';trig=[st['eventId']]
        elif st and st['status']=='terminal_failed':action='block';reason='TERMINAL_FAILURE';trig=[st['eventId']]
        elif st and st['status']=='started':action='block';reason='RUNNING';trig=[st['eventId']]
        elif st and st['status']=='retryable_failed':action='rerun';reason='RETRYABLE_FAILURE';trig=[st['eventId']]
        elif PAREN[n] and state['node'].get(PAREN[n],{}).get('status')=='terminal_failed':action='block';reason='UPSTREAM_TERMINAL';trig=[]
        elif PAREN[n] and state['node'].get(PAREN[n],{}).get('status')!='succeeded':action='block';reason='UPSTREAM_PENDING';trig=[]
        else:action='rerun';reason='CACHE_MISS';trig=[]
        nodes.append({'node':n,'action':action,'reasonCodes':[reason],'dependencyDigests':dep,'triggeringEventIds':trig})
    return {'revision':revision,'acceptedEventIds':accepted,'ignoredEventIds':ignored,'nodes':nodes}
