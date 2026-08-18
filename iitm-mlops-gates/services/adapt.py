from shared.common import *
PRIORITY=['prompt_only','retrieval','lora','qlora']

def process(req):
    if not isinstance(req,dict) or req.get('operation') not in ('choose','repair'):return {'error':'INVALID_INPUT'},400
    if req['operation']=='choose':
        p=req.get('policy'); cs=req.get('candidates')
        if not isinstance(p,dict) or not isinstance(cs,list) or len(cs)!=4:return {'error':'INVALID_INPUT'},400
        by={}; total={}; reasons={}; eligible=[]
        for c in cs:
            n=c.get('name'); r=[]
            if n not in PRIORITY or n in by:r.append('INVALID_INPUT')
            by[n]=c
            if not c.get('available'):r.append('UNAVAILABLE')
            for k in ('quality',):
                if not finite_range01(c.get(k)):r.append('INVALID_INPUT')
            for k in ('latencyMs','memoryMb','labeledExamples','oneTimeCost','recurringCost'):
                if not finite_num(c.get(k)) or c[k]<0:r.append('INVALID_INPUT')
            cost=round(c.get('oneTimeCost',0)+p.get('horizonRequests',0)*c.get('recurringCost',0),12) if finite_num(c.get('oneTimeCost')) and finite_num(c.get('recurringCost')) and safe_int(p.get('horizonRequests')) else None
            total[n]=cost
            if c.get('quality',-1)<p.get('minQuality',0):r.append('QUALITY_FLOOR')
            if p.get('freshnessRequired') and not c.get('freshness'):r.append('FRESHNESS_REQUIRED')
            if finite_num(c.get('latencyMs')) and c['latencyMs']>p.get('maxLatencyMs',float('inf')):r.append('LATENCY_LIMIT')
            if finite_num(c.get('memoryMb')) and c['memoryMb']>p.get('maxMemoryMb',float('inf')):r.append('MEMORY_LIMIT')
            if safe_int(c.get('labeledExamples')) and c['labeledExamples']>p.get('maxLabeledExamples',SAFE_MAX):r.append('DATA_LIMIT')
            if cost is not None and finite_num(p.get('maxTotalCost')) and cost>p['maxTotalCost']:r.append('COST_LIMIT')
            reasons[n]=codes(r)
            if not reasons[n]:eligible.append(n)
        return {'selected':eligible[0] if eligible else None,'eligible':[n for n in PRIORITY if n in eligible],'totalCosts':total,'reasonCodes':reasons},200
    rc=[]
    toks=req.get('tokens'); params=req.get('parameters'); allowed=req.get('allowedTargets')
    labels=[]
    if not isinstance(toks,list) or not toks:rc.append('INVALID_TOKEN')
    else:
        valid=True
        for t in toks:
            if not isinstance(t,dict) or not safe_int(t.get('id')) or t.get('role') not in ('system','user','assistant') or not isinstance(t.get('padding'),bool) or not isinstance(t.get('text'),str):valid=False
        if not valid:rc.append('INVALID_TOKEN');labels=[-100]*len(toks)
        else:labels=[t['id'] if t['role']=='assistant' and not t['padding'] else -100 for t in toks]
    if req.get('templateApplications')!=1:rc.append('CHAT_TEMPLATE_COUNT')
    if not isinstance(params,list) or not isinstance(allowed,list) or not allowed or len(set(allowed))!=len(allowed) or any(not isinstance(x,str) or not x for x in allowed):rc.append('INVALID_PARAMETER')
    train=[]
    if isinstance(params,list):
        names=set()
        for p in params:
            if not isinstance(p,dict) or not isinstance(p.get('name'),str) or p.get('name') in names or not safe_int(p.get('numel'),True) or not isinstance(p.get('target'),str):rc.append('INVALID_PARAMETER');continue
            names.add(p['name'])
            if p['target'] in allowed and (p['name'].endswith('.lora_A.weight') or p['name'].endswith('.lora_B.weight')):train.append((p['name'],p['numel']))
    if not train:rc.append('INVALID_PARAMETER')
    if req.get('inferenceMode') is not False:rc.append('INFERENCE_MODE')
    if req.get('dropoutActiveDuringEval') is not False:rc.append('EVAL_DROPOUT_ACTIVE')
    tids=req.get('trainRowIds'); eids=req.get('evalRowIds')
    if not isinstance(tids,list) or not isinstance(eids,list) or not tids or not eids or any(not isinstance(x,str) or not x for x in tids+eids) or len(set(tids))!=len(tids) or len(set(eids))!=len(eids):rc.append('EVAL_LEAKAGE')
    if isinstance(tids,list) and isinstance(eids,list) and set(tids)&set(eids):rc.append('EVAL_LEAKAGE')
    af=req.get('artifactFiles'); expected=['adapter_config.json','adapter_model.safetensors']
    if not isinstance(af,list) or sorted(af,key=utf8key)!=sorted(expected,key=utf8key) or len(af)!=2:rc.append('ADAPTER_FILE_SET')
    if not isinstance(req.get('baseRevision'),str) or not HEX40.fullmatch(req.get('baseRevision','')):rc.append('MUTABLE_BASE_REVISION')
    for k in ('datasetDigest','codeDigest','configDigest'):
        if not isinstance(req.get(k),str) or not HEX64.fullmatch(req.get(k,'')):rc.append('LINEAGE_MISMATCH')
    eb=req.get('expectedEffectiveBatch')
    if not all(safe_int(req.get(k),True) for k in ('microBatch','gradientAccumulation','replicas','expectedEffectiveBatch')) or req['microBatch']*req['gradientAccumulation']*req['replicas']!=eb:rc.append('EFFECTIVE_BATCH_MISMATCH')
    cp=req.get('checkpoint');
    if not isinstance(cp,dict) or any(k not in cp for k in ('model','optimizer','scheduler','step','rng','dataPosition')):rc.append('INCOMPLETE_CHECKPOINT')
    a,b=req.get('uninterruptedWeights'),req.get('resumedWeights'); tol=req.get('resumeTolerance')
    resume=True
    if not isinstance(a,list) or not isinstance(b,list) or not a or len(a)!=len(b) or not finite_num(tol) or tol<0 or any(not finite_num(x) for x in a+b) or any(abs(x-y)>tol for x,y in zip(a,b)):resume=False;rc.append('RESUME_DIVERGENCE')
    train=sorted(train,key=lambda x:utf8key(x[0])); count=sum(n for _,n in train)
    return {'labels':labels,'templatePass':'CHAT_TEMPLATE_COUNT' not in rc,'trainableParams':[n for n,_ in train],'trainableCount':count,'peftConfigPass':'INVALID_PARAMETER' not in rc,'adapterFiles':sorted(expected,key=utf8key) if 'ADAPTER_FILE_SET' not in rc else sorted(af,key=utf8key) if isinstance(af,list) else [],'checkpointComplete':'INCOMPLETE_CHECKPOINT' not in rc,'lineagePass':not any(x in rc for x in ('MUTABLE_BASE_REVISION','LINEAGE_MISMATCH')),'evalIsolated':'EVAL_LEAKAGE' not in rc,'evaluationDeterministic':'EVAL_DROPOUT_ACTIVE' not in rc,'resumePass':resume,'reasonCodes':codes(rc)},200
