from shared.common import *

def build(req):
    if not isinstance(req,dict) or 'policy' not in req or not isinstance(req.get('objects'),list) or not isinstance(req.get('policy'),dict):
        return None,400
    p=req['policy']; invalid_policy=True
    mn=parse_instant(p.get('minTime')); mx=parse_instant(p.get('maxTime')); th=p.get('contaminationThreshold')
    if mn and mx and mn<=mx and finite_range01(th): invalid_policy=False
    splits={'train':[],'validation':[],'test':[]}; rej_obj=[]; rej_rows=[]; lineage=[]; candidates=[]
    for o in req['objects']:
        uri=o.get('uri') if isinstance(o,dict) else None
        oc=[]
        if not isinstance(uri,str) or re.fullmatch(r'gs://[^/]+/[^/]+',uri) is None: oc.append('URI_INVALID')
        g=o.get('generation') if isinstance(o,dict) else None; fg=o.get('fetchedGeneration') if isinstance(o,dict) else None
        gv=isinstance(g,str) and g.isdecimal(); fgv=isinstance(fg,str) and fg.isdecimal()
        if not gv: oc.append('GENERATION_INVALID')
        if not fgv: oc.append('GENERATION_INVALID')
        if g != fg: oc.append('GENERATION_MISMATCH')
        crc=o.get('crc32c') if isinstance(o,dict) else None; content=o.get('content') if isinstance(o,dict) else None
        crcok=isinstance(crc,str) and re.fullmatch(r'[0-9a-f]{8}',crc) is not None
        if not crcok: oc.append('CRC32C_INVALID')
        elif isinstance(content,str) and crc32c_hex(content.encode())!=crc: oc.append('CRC32C_MISMATCH')
        schema=o.get('schemaId') if isinstance(o,dict) else None
        if schema!='training-v1' or not isinstance(content,str): oc.append('SCHEMA_INVALID')
        rows=[]
        if isinstance(content,str):
            lines=content.split('\n')
            nonblank=False
            for line in lines:
                if not line.strip(): continue
                nonblank=True
                try: row=json.loads(line)
                except Exception: oc.append('JSONL_INVALID'); continue
                if not isinstance(row,dict) or list(row.keys())!=['id','entity','eventTime','revision','text'] or not all(isinstance(row[k],str) for k in ['id','entity','eventTime','text']) or not safe_int(row.get('revision')):
                    oc.append('SCHEMA_INVALID'); continue
                if parse_instant(row['eventTime']) is None: oc.append('SCHEMA_INVALID'); continue
                rows.append(row)
            if not nonblank: oc.append('SCHEMA_INVALID')
        if oc:
            rej_obj.append({'uri':uri,'reasonCodes':codes(oc)}); continue
        lineage.append({'uri':uri,'generation':g,'crc32c':crc,'schemaId':schema})
        candidates.append((uri,rows))
    # dedupe by tuple, loser rejected
    retained={}
    for uri,rows in candidates:
        for r in rows:
            cr={'id':r['id'],'entity':norm_text(r['entity']),'eventTime':norm_time(r['eventTime']),'revision':r['revision'],'text':norm_text(r['text'])}
            key=(cr['entity'],cr['eventTime'],cr['text'])
            prev=retained.get(key)
            if prev is None or (cr['revision'],utf8key(cr['id']))>(prev[0]['revision'],utf8key(prev[0]['id'])):
                if prev: rej_rows.append({'id':prev[0]['id'],'reasonCodes':['DUPLICATE']})
                retained[key]=(cr,uri)
            else: rej_rows.append({'id':cr['id'],'reasonCodes':['DUPLICATE']})
    train=[]; others=[]
    for r,uri in retained.values():
        if invalid_policy: rej_rows.append({'id':r['id'],'reasonCodes':['POLICY_INVALID']}); continue
        dt=parse_instant(r['eventTime']);
        if not (mn<=dt<=mx): rej_rows.append({'id':r['id'],'reasonCodes':['OUT_OF_WINDOW']}); continue
        b=hashlib.sha256(r['entity'].encode()).digest()[0]%10
        split='train' if b<=5 else ('validation' if b<=7 else 'test')
        (train if split=='train' else others).append((r,split,uri))
    trainwords=[wordset(r['text']) for r in train]
    for r,split,uri in others:
        if any(jaccard(wordset(r['text']),tw)>=th for tw in trainwords): rej_rows.append({'id':r['id'],'reasonCodes':['TRAIN_CONTAMINATION']}); continue
        splits[split].append(r)
    for r,_,_ in train:splits['train'].append(r)
    for k in splits:
        splits[k]=sorted(splits[k],key=lambda r:(utf8key(r['id']),cbytes(r)))
    dig={k:sha256_hex_bytes((''.join(compact(r)+'\n' for r in splits[k])).encode()) for k in splits}
    resp={'splits':splits,'rejectedObjects':sorted(rej_obj,key=lambda x:(utf8key(x['uri']) if isinstance(x['uri'],str) else b'')),'rejectedRows':sorted(rej_rows,key=lambda x:utf8key(x['id'])),'digests':dig,'lineage':sorted(lineage,key=lambda x:utf8key(x['uri']))}
    return resp,200
