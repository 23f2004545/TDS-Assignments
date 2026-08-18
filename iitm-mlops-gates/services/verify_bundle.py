from shared.common import *
REQUIRED=['README.md','training_manifest.json','evaluation.json','inventory.json','adapter_model.safetensors','adapter_config.json']

def process(req):
    p=req.get('policy') if isinstance(req,dict) else None; files=req.get('files') if isinstance(req,dict) else None
    if not isinstance(p,dict) or not isinstance(files,dict):return {'error':'INVALID_INPUT'},400
    if not isinstance(p.get('requiredSlices'),list) or not p['requiredSlices'] or len(set(p['requiredSlices']))!=len(p['requiredSlices']) or any(not isinstance(x,str) or not x for x in p['requiredSlices']) or any(not isinstance(p.get(x),str) or not p[x] for x in ('license','intendedUse','limitations')):return {'error':'INVALID_INPUT'},400
    v=[]
    for n in REQUIRED:
        if n not in files:v.append('MISSING_FILE:'+n)
        elif not isinstance(files[n],str):v.append('INVALID_FILE:'+n)
    for n in files:
        if n not in REQUIRED:v.append('UNTRACKED_FILE')
        if any(n.endswith(ext) for ext in ('.bin','.pt','.pth','.pkl','.pickle')):v.append('UNSAFE_WEIGHTS')
    parsed={}
    for n in ('inventory.json','adapter_config.json','training_manifest.json','evaluation.json'):
        if isinstance(files.get(n),str):
            try:parsed[n]=json.loads(files[n])
            except: v.append('INVALID_JSON:'+n)
    inv=parsed.get('inventory.json'); actual=[]
    for n in files:
        if n!='inventory.json':actual.append({'name':n,'bytes':len(files[n].encode()),'sha256':sha256_hex_bytes(files[n].encode())})
    actual.sort(key=lambda x:utf8key(x['name']))
    invdigest=sha256_hex(actual)
    if not isinstance(inv,list) or inv!=actual:v.append('INVENTORY_MISMATCH')
    ac=parsed.get('adapter_config.json')
    if not isinstance(ac,dict) or not safe_int(ac.get('r'),True) or not isinstance(ac.get('target_modules'),list) or not ac['target_modules'] or len(set(ac['target_modules']))!=len(ac['target_modules']) or any(not isinstance(x,str) or not x for x in ac['target_modules']):v.append('INVALID_ADAPTER_CONFIG')
    tm=parsed.get('training_manifest.json')
    fields=['baseRevision','task','datasetDigest','codeDigest','trainingConfigDigest','modelArtifactDigest','evaluationArtifactDigest']
    if not isinstance(tm,dict):v.append('INVALID_TRAINING_MANIFEST')
    else:
        if not isinstance(tm.get('baseRevision'),str) or not HEX40.fullmatch(tm.get('baseRevision','')):v.append('MUTABLE_BASE_REVISION')
        for f in fields[1:]:
            if not isinstance(tm.get(f),str) or not tm[f]:v.append('MISSING_MANIFEST_FIELD:'+f)
        if tm.get('modelArtifactDigest')!=sha256_hex_bytes(files.get('adapter_model.safetensors','').encode()):v.append('MODEL_ARTIFACT_MISMATCH')
        if tm.get('evaluationArtifactDigest')!=sha256_hex_bytes(files.get('evaluation.json','').encode()):v.append('EVALUATION_DIGEST_MISMATCH')
    ev=parsed.get('evaluation.json')
    if not isinstance(ev,dict):v.append('INVALID_EVALUATION')
    else:
        if ev.get('modelArtifactDigest')!= (tm or {}).get('modelArtifactDigest'):v.append('EVALUATION_ARTIFACT_MISMATCH')
        if not finite_range01(ev.get('aggregate')):v.append('INVALID_AGGREGATE')
        for n in p['requiredSlices']:
            if not isinstance(ev.get('slices'),dict) or n not in ev['slices']:v.append('MISSING_SLICE:'+n)
            elif not finite_range01(ev['slices'][n]):v.append('SLICE_RANGE:'+n)
    readme=files.get('README.md',''); marker='<!-- tds-model-card '
    starts=[i for i in range(len(readme)) if readme.startswith(marker,i)]
    if len(starts)==0:v+=['MODEL_CARD_COUNT','MISSING_MODEL_CARD']
    elif len(starts)>1:v.append('MODEL_CARD_COUNT')
    else:
        end=readme.find(' -->',starts[0]+len(marker))
        if end<0:
            v.append('INVALID_MODEL_CARD')
        else:
            try: card=json.loads(readme[starts[0]+len(marker):end]);
            except: card=None
            if not isinstance(card,dict):v.append('INVALID_MODEL_CARD')
            else:
                for k in ('task','baseRevision','datasetDigest','modelArtifactDigest','license','intendedUse','limitations'):
                    expected=(tm or {}).get(k) if k in ('task','baseRevision','datasetDigest','modelArtifactDigest') else p.get(k)
                    if card.get(k)!=expected:v.append('MODEL_CARD_MISMATCH');break
    return {'decision':'admit' if not v else 'reject','violations':codes(v),'inventoryDigest':invdigest},200
