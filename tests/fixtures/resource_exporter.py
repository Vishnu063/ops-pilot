"""CI-only cgroup exporter: real bounded pressure projected into node-style series.

This is a fault fixture, not a replacement production node exporter.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time

limit=int(Path('/sys/fs/cgroup/memory.max').read_text())
quota,period=Path('/sys/fs/cgroup/cpu.max').read_text().split()
cores=int(quota)/int(period)
memory=bytearray(80*1024**2)
disk_full=False
try:
    with Path('/data/owned-pressure').open('wb') as output:
        while True:output.write(b'x'*65536)
except OSError as error:
    if error.errno!=errno.ENOSPC:raise
    disk_full=True
def burn():
    block=b'x'*4096
    while True:hashlib.sha256(block).digest()
threading.Thread(target=burn,daemon=True).start()
started=time.monotonic()
def usage():return int(dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())['usage_usec'])/1e6
cpu_start=usage()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/health':raw=json.dumps({'healthy':True,'disk_enospc':disk_full}).encode()
        else:
            elapsed=time.monotonic()-started
            idle=max(0,elapsed-(usage()-cpu_start)/cores)
            current=int(Path('/sys/fs/cgroup/memory.current').read_text())
            disk=shutil.disk_usage('/data')
            raw=('node_cpu_seconds_total{mode="idle",service="owned-demo"} '+str(idle)+'\n'+
                 'node_memory_MemAvailable_bytes{service="owned-demo"} '+str(max(0,limit-current))+'\n'+
                 'node_memory_MemTotal_bytes{service="owned-demo"} '+str(limit)+'\n'+
                 'node_filesystem_avail_bytes{service="owned-demo",mountpoint="/data"} '+str(disk.free)+'\n'+
                 'node_filesystem_size_bytes{service="owned-demo",mountpoint="/data"} '+str(disk.total)+'\n').encode()
        self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/health' else 'text/plain');self.end_headers();self.wfile.write(raw)
HTTPServer(('127.0.0.1',int(os.environ['FIXTURE_PORT'])),Handler).serve_forever()
