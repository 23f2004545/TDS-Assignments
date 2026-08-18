import hashlib, json, math, re, unicodedata
from typing import Any
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

OBJ_CODES = ["URI_INVALID", "GENERATION_INVALID", "GENERATION_MISMATCH", "CRC32C_INVALID", "CRC32C_MISMATCH", "SCHEMA_INVALID", "JSONL_INVALID"]
ROW_CODES = ["DUPLICATE", "POLICY_INVALID", "OUT_OF_WINDOW", "TRAIN_CONTAMINATION"]
GEN_RE = re.compile(r"^[0-9]+$")
CRC_RE = re.compile(r"^[0-9a-f]{8}$")
URI_RE = re.compile(r"^gs://[^/]+/.+$")
TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$")

# CRC-32C (Castagnoli), reflected polynomial.
CRC32C_TABLE = []
for n in range(256):
    c = n
    for _ in range(8):
        c = (c >> 1) ^ (0x82F63B78 if c & 1 else 0)
    CRC32C_TABLE.append(c)

def crc32c(data: bytes) -> int:
    c = 0xffffffff
    for b in data:
        c = CRC32C_TABLE[(c ^ b) & 0xff] ^ (c >> 8)
    return c ^ 0xffffffff

def sort_utf8(items, key):
    return sorted(items, key=lambda x: key(x).encode('utf-8'))

def reason_sort(codes):
    return sorted(set(codes), key=lambda s: s.encode('utf-8'))

def normalize_text(s: str) -> str:
    s = unicodedata.normalize('NFKC', s).lower()
    return ' '.join(s.split())

def parse_time(s: Any):
    if not isinstance(s, str):
        return None
    m = TIME_RE.fullmatch(s)
    if not m:
        return None
    base, frac, off = m.groups()
    try:
        # strptime validates calendar/date/time ranges.
        dt = datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
        micros = int((frac or '').ljust(3, '0')) * 1000
        dt = dt.replace(microsecond=micros)
        if off == 'Z':
            tz = timezone.utc
        else:
            sign = 1 if off[0] == '+' else -1
            hh, mm = map(int, off[1:].split(':'))
            if hh > 14 or mm > 59 or (hh == 14 and mm != 0):
                return None
            tz = timezone(sign * timedelta(hours=hh, minutes=mm))
        dt = dt.replace(tzinfo=tz).astimezone(timezone.utc)
        return dt
    except ValueError:
        return None

def canon_time(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{dt.microsecond // 1000:03d}Z'

def json_compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

def safe_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 9007199254740991

def word_set(s: str):
    # A word is a maximal run of Unicode letters/numbers; everything else separates words.
    words, cur = [], []
    for ch in s.lower():
        cat = unicodedata.category(ch)
        if cat[0] in ('L', 'N'):
            cur.append(ch)
        elif cur:
            words.append(''.join(cur)); cur = []
    if cur:
        words.append(''.join(cur))
    return set(words)

def jaccard(a, b):
    if not a and not b:
        return 1.0
    u = a | b
    return len(a & b) / len(u) if u else 1.0

def digest(rows):
    data = ''.join(json_compact(r) + '\n' for r in rows).encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def row_sort_key(r):
    return (r['id'].encode('utf-8'), json_compact(r).encode('utf-8'))

def canonical_row(row):
    return {
        'id': row['id'],
        'entity': normalize_text(row['entity']),
        'eventTime': canon_time(parse_time(row['eventTime'])),
        'revision': row['revision'],
        'text': normalize_text(row['text']),
    }

def add_reject(d, code):
    d.setdefault('reasonCodes', []).append(code)

def object_shape_ok(obj):
    # Top-level request object itself is not specified beyond these fields; all supplied fields are checked.
    return isinstance(obj, dict)

def validate_row_shape(row):
    if not isinstance(row, dict) or set(row.keys()) != {'id','entity','eventTime','revision','text'}:
        return False
    return (isinstance(row['id'], str) and isinstance(row['entity'], str) and
            isinstance(row['eventTime'], str) and isinstance(row['text'], str) and
            safe_int(row['revision']) and parse_time(row['eventTime']) is not None)

def process(payload):
    policy = payload.get('policy')
    objects = payload.get('objects')
    if not isinstance(policy, dict) or not isinstance(objects, list):
        raise ValueError('INVALID_INPUT')
    # Policy validity: exact timestamp format + threshold finite in [0,1]. Missing fields are invalid.
    min_dt = parse_time(policy.get('minTime'))
    max_dt = parse_time(policy.get('maxTime'))
    th = policy.get('contaminationThreshold')
    policy_valid = (min_dt is not None and max_dt is not None and isinstance(th, (int,float)) and
                    not isinstance(th, bool) and math.isfinite(th) and 0 <= th <= 1 and min_dt <= max_dt)

    rejected_objects = []
    rejected_rows = []
    lineage = []
    candidates = []

    for obj in objects:
        uri = obj.get('uri') if isinstance(obj, dict) else None
        oc = []
        uri_ok = isinstance(uri, str) and URI_RE.fullmatch(uri) is not None
        if not uri_ok: oc.append('URI_INVALID')

        gen = obj.get('generation') if isinstance(obj, dict) else None
        fgen = obj.get('fetchedGeneration') if isinstance(obj, dict) else None
        gen_ok = isinstance(gen, str) and GEN_RE.fullmatch(gen) is not None
        fgen_ok = isinstance(fgen, str) and GEN_RE.fullmatch(fgen) is not None
        if not gen_ok or not fgen_ok: oc.append('GENERATION_INVALID')
        if isinstance(gen, str) and isinstance(fgen, str) and gen_ok and fgen_ok and gen != fgen:
            oc.append('GENERATION_MISMATCH')

        crc = obj.get('crc32c') if isinstance(obj, dict) else None
        crc_ok = isinstance(crc, str) and CRC_RE.fullmatch(crc) is not None
        if not crc_ok: oc.append('CRC32C_INVALID')

        schema = obj.get('schemaId') if isinstance(obj, dict) else None
        content = obj.get('content') if isinstance(obj, dict) else None
        if schema != 'training-v1' or not isinstance(content, str):
            oc.append('SCHEMA_INVALID')

        parsed_rows = None
        if isinstance(content, str):
            parsed_rows = []
            try:
                for line in content.splitlines():
                    if not line.strip():
                        continue
                    parsed_rows.append(json.loads(line))
                if not parsed_rows:
                    oc.append('SCHEMA_INVALID')
                elif any(not validate_row_shape(r) for r in parsed_rows):
                    oc.append('SCHEMA_INVALID')
            except Exception:
                oc.append('JSONL_INVALID')
        # CRC mismatch only for string content and syntactically valid CRC.
        if isinstance(content, str) and crc_ok:
            actual = f'{crc32c(content.encode("utf-8")):08x}'
            if actual != crc:
                oc.append('CRC32C_MISMATCH')

        oc = reason_sort(oc)
        if oc:
            rejected_objects.append({'uri': uri if isinstance(uri, str) else None, 'reasonCodes': oc})
            continue

        lineage.append({'uri': uri, 'generation': gen, 'crc32c': crc, 'schemaId': schema})
        for r in parsed_rows:
            candidates.append((r, uri))

    # Deduplicate globally by canonical tuple.
    groups = {}
    for raw, uri in candidates:
        cr = canonical_row(raw)
        key = (cr['entity'], cr['eventTime'], cr['text'])
        groups.setdefault(key, []).append((cr, uri))
    retained = []
    for vals in groups.values():
        vals.sort(key=lambda x: (-x[0]['revision'], x[0]['id'].encode('utf-8'), json_compact(x[0]).encode('utf-8')))
        winner = vals[0]
        retained.append(winner[0])
        for loser, _ in vals[1:]:
            rejected_rows.append({'id': loser['id'], 'reasonCodes': ['DUPLICATE']})

    # Policy/window.
    post_policy = []
    for r in retained:
        if not policy_valid:
            rejected_rows.append({'id': r['id'], 'reasonCodes': ['POLICY_INVALID']})
        else:
            dt = parse_time(r['eventTime'])
            if dt < min_dt or dt > max_dt:
                rejected_rows.append({'id': r['id'], 'reasonCodes': ['OUT_OF_WINDOW']})
            else:
                post_policy.append(r)

    splits = {'train': [], 'validation': [], 'test': []}
    for r in post_policy:
        bucket = hashlib.sha256(r['entity'].encode('utf-8')).digest()[0] % 10
        split = 'train' if bucket <= 5 else ('validation' if bucket <= 7 else 'test')
        splits[split].append(r)
    train_sets = [word_set(r['entity'] + ' ' + r['text']) for r in splits['train']]
    for split in ('validation','test'):
        kept = []
        for r in splits[split]:
            rs = word_set(r['entity'] + ' ' + r['text'])
            if any(jaccard(rs, ts) >= th for ts in train_sets):
                rejected_rows.append({'id': r['id'], 'reasonCodes': ['TRAIN_CONTAMINATION']})
            else:
                kept.append(r)
        splits[split] = kept

    for s in splits:
        splits[s].sort(key=row_sort_key)
    rejected_objects.sort(key=lambda x: (x['uri'] is not None, (x['uri'] or '').encode('utf-8'), json_compact(x).encode('utf-8')))
    # Merge reasons for same rejected row ID and sort deterministically.
    merged = {}
    for x in rejected_rows:
        merged.setdefault(x['id'], set()).update(x['reasonCodes'])
    rejected_rows = [{'id': k, 'reasonCodes': reason_sort(v)} for k,v in merged.items()]
    rejected_rows.sort(key=lambda x: (x['id'].encode('utf-8'), json_compact(x).encode('utf-8')))
    lineage.sort(key=lambda x: (x['uri'].encode('utf-8'), json_compact(x).encode('utf-8')))

    return {
        'splits': splits,
        'rejectedObjects': rejected_objects,
        'rejectedRows': rejected_rows,
        'digests': {s: digest(splits[s]) for s in ('train','validation','test')},
        'lineage': lineage,
    }

@app.post('/build-corpus')
async def build_corpus(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({'error':'INVALID_INPUT'}, status_code=400)
    try:
        return JSONResponse(process(payload))
    except ValueError as e:
        if str(e) == 'INVALID_INPUT':
            return JSONResponse({'error':'INVALID_INPUT'}, status_code=400)
        raise
    except Exception:
        # Unexpected malformed request: preserve required input contract rather than exposing internals.
        return JSONResponse({'error':'INVALID_INPUT'}, status_code=400)

@app.get('/')
def root():
    return {'service':'deterministic-jsonl-corpus','endpoint':'POST /build-corpus'}
