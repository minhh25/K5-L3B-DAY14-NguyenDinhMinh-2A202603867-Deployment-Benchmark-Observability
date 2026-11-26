"""Validate submission evidence, cloud check provenance and protected files."""
import hashlib
import json
import subprocess
from pathlib import Path
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
def read(path):
    return json.loads((root/path).read_text())
checks=[]
def require(condition,label):
    checks.append({'check':label,'passed':bool(condition)})
    if not condition:
        raise AssertionError(label)

for path in ['06-lab-complete/check_production_ready.py',
             '06-lab-complete/benchmark-observability/develop/eval/golden_dataset.jsonl']:
    original=subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=root)
    require(hashlib.sha256(original).digest()==hashlib.sha256((root/path).read_bytes()).digest(),
            'Protected file unchanged: '+path)
for c in [1,10,50,100]:
    r=read(f'reports/load_v2_c{c}.json')
    require(r['concurrency']==c and r['total_requests']==300 and
            sum(r['status_codes'].values())==300,f'300 requests, concurrency {c}')
for slow in ['0','0.03','0.1']:
    require(read(f'reports/load_v2_slow_{slow}.json')['total_requests']==300,'Slow-rate evidence '+slow)
r=read('reports/eval_v2_fixed.json')
require(r['passed']==r['total']==23 and r['quality_gate']['passed'] and
        not r['quality_gate']['regressions'],'Fixed KB: 23/23, no regression')
require(not read('reports/eval_regression.json')['quality_gate']['passed'],'Regression fails gate')
require('PASS 12/12' in (root/'reports/production-readiness.txt').read_text(),'Full production check PASS 12/12')
require('Ran 4 tests' in (root/'reports/guard-integration-tests.txt').read_text(),'Four guard integration tests')
require('SUCCESS' in (root/'reports/prometheus-rule-tests.txt').read_text(),'Promtool SUCCESS')
require([r['verified_container_count'] for r in read('reports/scaling-run.json')]==[1,3],
        'Scaling actually used 1 and 3 containers')
alerts=read('reports/alerts-AB.json')['alerts']
names={x['labels']['alertname'] for x in alerts if x['state']=='firing'}
require({'AgentHighErrorRate','AgentHighLatencyP95'} <= names,'Two simultaneous firing alerts')
for kind,evidence in read('reports/trace-evidence.json').items():
    require(any(log['trace_id']==evidence['trace_id'] for log in evidence['logs']),kind+' trace/log correlation')
for name in ['grafana-dashboard','jaeger-slow-trace','jaeger-error-trace','prometheus-alert-firing']:
    image=root/f'screenshots/{name}.png'
    require(image.exists() and image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Actual PNG screenshot: '+name)
for name in ['MISSION_ANSWERS.md','DEPLOYMENT.md','BENCHMARK_REPORT.md','RUN_LAB.md']:
    require((root/name).exists(),'Document: '+name)
key=dotenv_values(root/'06-lab-complete/.env').get('AGENT_API_KEY','')
paths=set(subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines())
paths.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines())
if key:
    for name in paths:
        path=root/name
        if path.is_file() and path.suffix in ['.md','.json','.txt','.py','.yaml','.yml','.toml','.csv','.log']:
            require(key not in path.read_text(errors='ignore'),'No local key in '+name)
ignored=subprocess.run(['git','check-ignore','06-lab-complete/.env'],cwd=root,capture_output=True).returncode==0
require(ignored,'Local secret .env ignored by Git')
subprocess.run(['git','diff','--check'],cwd=root,check=True)
deployment_path=root/'reports/public-deployment.json'
deployed=deployment_path.exists()
cloud_images=['dashboard.png','running.png','test.png']
for name in cloud_images:
    image=root/'screenshots'/name
    if image.exists():
        require(image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'Cloud PNG: '+name)
if deployed:
    deployment=read('reports/public-deployment.json')
    codes={item['name']:item['status'] for item in deployment['checks']}
    require(codes=={'health':200,'ready':200,'ask_without_key':401,'ask_with_key':200},
            'Cloud: health 200, ready 200, missing key 401, authenticated 200')
(root/'reports/submission-audit.json').write_text(json.dumps({
    'checks':checks,'local_lab_complete':True,'render_deployment':'deployed' if deployed else 'deferred by user',
    'public_url_verified':deployed,
    'authenticated_check_source':'user_supplied_swagger_response' if deployed else None,
    'cloud_screenshots_complete':all((root/'screenshots'/name).exists() for name in cloud_images),
    'cloud_screenshots_pending':['screenshots/'+name for name in cloud_images
                                 if not (root/'screenshots'/name).exists()],
    'github_workflows_status_verified':False},indent=2,ensure_ascii=False))
print(f'{len(checks)} audit checks passed. Render deployed: {deployed}; see cloud screenshot status in JSON.')
