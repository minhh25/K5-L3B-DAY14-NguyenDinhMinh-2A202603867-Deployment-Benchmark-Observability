"""CP2 and CP4 Docker evidence, isolated Compose projects and cleanup."""
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'

def run(args, cwd=ROOT, timeout=900):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr

def wait(url, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError('Not ready: ' + url)

sizes={}
for tag in ('day14-agent:develop', 'day14-agent:advanced'):
    sizes[tag]=int(run(['docker','image','inspect','--format','{{.Size}}',tag]).strip())
sizes['reduction_pct']=round((1-sizes['day14-agent:advanced']/sizes['day14-agent:develop'])*100,2)
(REPORTS/'docker-image-sizes.json').write_text(json.dumps(sizes,indent=2))
try:
    run(['docker','run','-d','--name','day14-cp2-develop','-p','127.0.0.1:18000:8000','day14-agent:develop'])
    wait('http://127.0.0.1:18000/health')
    output=run(['curl','-sS','-i','-X','POST','http://127.0.0.1:18000/ask?question=What%20is%20Docker'])
    assert '200 OK' in output
    (REPORTS/'cp2-container-http.txt').write_text(output)
finally:
    run(['docker','rm','-f','day14-cp2-develop'])
for folder,project,url in (
    ('02-docker/production','k5-day14-docker','http://127.0.0.1/health'),
    ('05-scaling-reliability/production','k5-day14-scaling','http://127.0.0.1:8080/health'),
):
    cwd=ROOT/folder
    (cwd/'.env.local').touch(exist_ok=True)
    base=['docker','compose','-p',project]
    try:
        args=base+['up','-d','--build']
        if 'scaling' in project:
            args+=['--scale','agent=3']
        (REPORTS/f'{project}-startup.txt').write_text(run(args,cwd))
        wait(url)
        if 'scaling' in project:
            output=run([sys.executable,'test_stateless.py'],cwd)
            assert 'Total messages: 10' in output
            (REPORTS/'cp4-stateless.txt').write_text(output)
        else:
            output=run(['curl','-sS','-i','-X','POST','http://127.0.0.1/ask',
                        '-H','Content-Type: application/json','-d','{"question":"Explain microservices"}'])
            assert '200 OK' in output
            (REPORTS/'cp2-nginx-http.txt').write_text(output)
    finally:
        run(base+['down'],cwd)
print(json.dumps(sizes))
print('CP2 Docker and CP4 scaling verified.')
