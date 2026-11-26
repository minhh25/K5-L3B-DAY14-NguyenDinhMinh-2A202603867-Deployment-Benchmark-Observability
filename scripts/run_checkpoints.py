"""Capture real CP1/CP3/CP4 HTTP evidence without writing credentials to reports."""
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
REPORTS = ROOT / 'reports'
RUNTIME.mkdir(exist_ok=True)
REPORTS.mkdir(exist_ok=True)

@contextmanager
def server(folder, port, probe='/health', **env):
    with (RUNTIME / f'checkpoint-{port}.log').open('w') as log:
        p = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(port)],
                             cwd=ROOT / folder, env={**os.environ, **env}, stdout=log, stderr=log)
        try:
            for _ in range(150):
                if p.poll() is not None:
                    raise RuntimeError(Path(log.name).read_text())
                try:
                    with urlopen(f'http://127.0.0.1:{port}{probe}', timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Startup timeout')
            yield p
        finally:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(15)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()

def curl(url, data=None, headers=None):
    args = ['curl', '--silent', '--show-error', '-i', url]
    if data is not None:
        args += ['-X', 'POST', '-H', 'Content-Type: application/json', '-d', json.dumps(data)]
    for key, value in (headers or {}).items():
        args += ['-H', f'{key}: {value}']
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout

result = {}
with server('01-localhost-vs-production/develop', 18101, probe='/'):
    output = subprocess.check_output(['curl', '-sS', '-i', '-X', 'POST',
                                      'http://127.0.0.1:18101/ask?question=Hello'], text=True)
    (REPORTS / 'cp1-develop-http.txt').write_text(output)
    assert '200 OK' in output
with server('01-localhost-vs-production/production', 18102):
    output = curl('http://127.0.0.1:18102/ask', {'question': 'What is deployment?'})
    (REPORTS / 'cp1-production-http.txt').write_text(output)
    assert '200 OK' in output
key = secrets.token_urlsafe(24)
with server('04-api-gateway/develop', 18103, AGENT_API_KEY=key):
    denied = curl('http://127.0.0.1:18103/ask', {'question': 'Hello'})
    accepted = curl('http://127.0.0.1:18103/ask', {'question': 'Hello'}, {'X-API-Key': key})
    assert '401 Unauthorized' in denied and '200 OK' in accepted
    (REPORTS / 'cp3-api-key-http.txt').write_text('NO KEY\n' + denied + '\nVALID KEY (redacted)\n' + accepted)
with server('04-api-gateway/production', 18104, JWT_SECRET=secrets.token_urlsafe(32)):
    login = subprocess.check_output(['curl', '-sS', '-X', 'POST', 'http://127.0.0.1:18104/auth/token',
                                     '-H', 'Content-Type: application/json',
                                     '-d', '{"username":"student","password":"demo123"}'], text=True)
    token = json.loads(login)['access_token']
    output = ['POST /auth/token -> 200; token omitted\n']
    output.append(curl('http://127.0.0.1:18104/ask', {'question': 'Hello'}))
    for i in range(12):
        output.append(f'\nREQUEST {i+1}\n' + curl('http://127.0.0.1:18104/ask', {'question': 'Test'},
                                                  {'Authorization': 'Bearer ' + token}))
    joined = '\n'.join(output)
    assert '401 Unauthorized' in joined and '200 OK' in joined and '429 Too Many Requests' in joined
    (REPORTS / 'cp3-jwt-rate-http.txt').write_text(joined)
with server('05-scaling-reliability/develop', 18105) as p:
    probes = curl('http://127.0.0.1:18105/health') + '\n' + curl('http://127.0.0.1:18105/ready')
    response = {}
    def in_flight():
        response['output'] = subprocess.check_output(['curl', '-sS', '-i', '-X', 'POST',
            'http://127.0.0.1:18105/ask?question=Hello'], text=True)
    thread = threading.Thread(target=in_flight)
    thread.start()
    time.sleep(.05)
    p.send_signal(signal.SIGTERM)
    thread.join(15)
    p.wait(15)
    assert '200 OK' in response['output']
    (REPORTS / 'cp4-graceful-http.txt').write_text(probes + '\nIN-FLIGHT REQUEST\n' + response['output'] +
                                                f'\nProcess exit code: {p.returncode}\n')
print('CP1, CP3 and CP4 local examples verified; credentials omitted.')
