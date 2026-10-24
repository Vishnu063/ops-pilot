"""Optional explicitly selected installed Ollama model. Untrusted advice, no tools."""
import hashlib
import json
from urllib.request import Request, build_opener, ProxyHandler
from .deployment_lab import NoRedirect


class Advisor:
    def __init__(self, workspace):
        self.ws = workspace
        with workspace.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS advice (key TEXT PRIMARY KEY, output TEXT, elapsed REAL)')

    def advise(self, prompt, model):
        import re
        import time
        if not isinstance(prompt,str) or not 1 <= len(prompt) <= 4000 or not re.fullmatch(r'[a-zA-Z0-9._:/-]{1,100}',model):
            raise ValueError('Bounded prompt and explicit installed model required')
        opener = build_opener(NoRedirect,ProxyHandler({}))
        def request(path, data=None):
            req = Request('http://127.0.0.1:11434'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=30) as response:
                raw = response.read(65537)
                if len(raw)>65536: raise ValueError('Model response exceeded limit')
                return json.loads(raw)
        key = hashlib.sha256(json.dumps([prompt,model,'requirements-v1']).encode()).hexdigest()
        with self.ws.lock, self.ws.connect() as db:
            cached = db.execute('SELECT output,elapsed FROM advice WHERE key=?',(key,)).fetchone()
            if cached: return dict(text=cached[0],elapsed=cached[1],cached=True,executed=False)
            if model not in [x['name'] for x in request('/api/tags')['models']]:
                raise ValueError('Model is not installed; no download attempted')
            start = time.monotonic()
            response = request('/api/generate',dict(model=model,stream=False,keep_alive=0,
                system='Identify missing requirements and risks for one stateless Docker HTTP app. Return advice only. No commands, tools, credentials or promises.',
                prompt=prompt,options=dict(num_ctx=2048,num_predict=256,temperature=0)))
            output = str(response.get('response',''))[:8000]; elapsed = time.monotonic()-start
            db.execute('INSERT INTO advice VALUES (?,?,?)',(key,output,elapsed))
        return dict(text=output,elapsed=elapsed,cached=False,executed=False,source='untrusted local model advice')
