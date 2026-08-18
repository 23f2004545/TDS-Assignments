import json, math, hashlib, re, unicodedata, sqlite3, threading
from datetime import datetime, timezone, timedelta

SAFE_MAX = 9007199254740991
HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def cbytes(obj): return compact(obj).encode('utf-8')
def sha256_hex_bytes(b): return hashlib.sha256(b).hexdigest()
def sha256_hex(obj): return sha256_hex_bytes(cbytes(obj))
def utf8key(s): return str(s).encode('utf-8')
def sort_utf8(xs): return sorted(xs, key=utf8key)
def codes(xs): return sorted(set(xs), key=utf8key)

def safe_int(x, positive=False):
    return isinstance(x,int) and not isinstance(x,bool) and (x > 0 if positive else 0 <= x <= SAFE_MAX)

def finite_num(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def finite_range01(x): return finite_num(x) and 0 <= x <= 1

def norm_text(s):
    s=unicodedata.normalize('NFKC',s).lower().strip()
    return re.sub(r'\s+', ' ', s, flags=re.UNICODE)

def parse_instant(s):
    if not isinstance(s,str): return None
    # exactly YYYY-MM-DDTHH:mm:ss(.1-3 digits)?(Z|+/-HH:mm), offset <=14:00 and 14 only :00
    m=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})',s)
    if not m: return None
    frac=(m.group(2) or '')
    frac=(frac+'000')[:3]
    base=m.group(1)+'.'+frac
    try: dt=datetime.strptime(base,'%Y-%m-%dT%H:%M:%S.%f')
    except ValueError: return None
    off=m.group(3)
    if off=='Z': tz=timezone.utc
    else:
        sign=1 if off[0]=='+' else -1
        hh,mm=map(int,off[1:].split(':'))
        if hh>14 or mm>59 or (hh==14 and mm!=0): return None
        tz=timezone(sign*timedelta(hours=hh,minutes=mm))
    return dt.replace(tzinfo=tz).astimezone(timezone.utc)

def norm_time(s):
    dt=parse_instant(s)
    return None if dt is None else dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:23]+'Z'

def wordset(s):
    s=unicodedata.normalize('NFKC',s).lower()
    out=set(); cur=[]
    for ch in s:
        cat=unicodedata.category(ch)
        if cat and cat[0] in ('L','N'):
            cur.append(ch)
        elif cur:
            out.add(''.join(cur)); cur=[]
    if cur: out.add(''.join(cur))
    return out

def jaccard(a,b):
    if not a and not b:return 1.0
    return len(a&b)/len(a|b) if a|b else 1.0

# CRC32C Castagnoli, reflected polynomial
_CRC_TABLE=None
def crc32c_hex(data):
    global _CRC_TABLE
    if _CRC_TABLE is None:
        poly=0x82F63B78
        _CRC_TABLE=[]
        for i in range(256):
            c=i
            for _ in range(8): c=(c>>1)^poly if c&1 else c>>1
            _CRC_TABLE.append(c)
    crc=0xffffffff
    for b in data:
        crc=_CRC_TABLE[(crc^b)&255]^(crc>>8)
    return f'{crc^0xffffffff:08x}'

class StateDB:
    def __init__(self,path='state.sqlite3'):
        self.conn=sqlite3.connect(path,check_same_thread=False)
        self.conn.row_factory=sqlite3.Row
        self.lock=threading.RLock()
        self.conn.execute('CREATE TABLE IF NOT EXISTS kv (namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(namespace,key))')
        self.conn.commit()
    def get(self,ns,key):
        with self.lock:
            r=self.conn.execute('SELECT value FROM kv WHERE namespace=? AND key=?',(ns,key)).fetchone()
            return json.loads(r['value']) if r else None
    def put(self,ns,key,value):
        with self.lock:
            self.conn.execute('INSERT OR REPLACE INTO kv(namespace,key,value) VALUES(?,?,?)',(ns,key,compact(value)))
            self.conn.commit()
