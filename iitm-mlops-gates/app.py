from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from shared.common import StateDB
from services import corpus,bqml,promote,adapt,quantize,pipeline,verify_bundle

app=FastAPI(title='IITM MLOps Gates',version='1.0.0')
db=StateDB()

@app.get('/')
def root():
    return {'service':'iitm-mlops-gates','endpoints':['/build-corpus','/bqml','/promote','/adapt','/quantize','/pipeline','/verify-bundle']}

async def body(request):
    try:return await request.json()
    except:return None

@app.post('/build-corpus')
async def build_corpus(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=corpus.build(x); return JSONResponse(r if r is not None else {'error':'INVALID_INPUT'},status_code=s)

@app.post('/bqml')
async def bqml_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=bqml.process(x,db);return JSONResponse(r if r is not None else {'error':'INVALID_INPUT'},status_code=s)

@app.post('/promote')
async def promote_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=promote.process(x);return JSONResponse(r,status_code=s)

@app.post('/adapt')
async def adapt_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=adapt.process(x);return JSONResponse(r,status_code=s)

@app.post('/quantize')
async def quantize_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=quantize.process(x,db);return JSONResponse(r,status_code=s)

@app.post('/pipeline')
async def pipeline_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_REQUEST'},status_code=409)
    r,s=pipeline.process(x,db);return JSONResponse(r,status_code=s)

@app.post('/verify-bundle')
async def verify_bundle_ep(request:Request):
    x=await body(request)
    if x is None:return JSONResponse({'error':'INVALID_INPUT'},status_code=400)
    r,s=verify_bundle.process(x);return JSONResponse(r,status_code=s)
