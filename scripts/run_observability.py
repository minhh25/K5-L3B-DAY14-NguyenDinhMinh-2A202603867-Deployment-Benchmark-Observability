"""CP8: actual Locust CSV, traces, alerts and fault-injection timings.
Run --phase scaling, then --phase alerts, capture screenshots, then --phase remaining.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]
STACK=ROOT/'06-lab-complete/benchmark-observability/production'
REPORTS=ROOT/'reports'
RESULTS=ROOT/'benchmark-results'
REPORTS.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)
BASE=['docker','compose','-p','k5-day14-observability']
DEFAULT={'AGENT_VERSION':'v2','LLM_MODEL':'mock-llm-small','AGENT_API_KEY':'day14-lab-key',
         'MOCK_LATENCY_MS':'120','MOCK_SLOW_RATE':'0.03','MOCK_ERROR_RATE':'0.01','MOCK_KB_PATCHES':'1'}


def command(args, config=None, timeout=600):
    p=subprocess.run(BASE+args,cwd=STACK,env={**os.environ,**DEFAULT,**(config or {})},
                     capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stdout+p.stderr)
    return p.stdout+p.stderr


def request(path, base='http://127.0.0.1:9090'):
    response=httpx.get(base+path,timeout=15)
    response.raise_for_status()
    return response.json()


def wait_ready():
    for _ in range(100):
        try:
            if httpx.get('http://127.0.0.1:8080/health',timeout=2).status_code==200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError('Nginx/agent not ready')


def configure(**config):
    started=time.monotonic()
    output=command(['up','-d','--scale','agent=3'],config)
    wait_ready()
    return started


def start_load():
    # Known lab-only key; no personal credentials are sent to this local stack.
    args=BASE+['run','--no-deps','-d','--name','day14-observability-load','locust','-f','/mnt/locust/locustfile.py',
               '--host','http://nginx','--headless','-u','30','-r','5','-t','30m']
    p=subprocess.run(args,cwd=STACK,env={**os.environ,**DEFAULT},capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(p.stdout+p.stderr)


def poll_alerts(names, started, label):
    found={}
    deadline=started+360
    while time.monotonic()<deadline:
        alerts=request('/api/v1/alerts')['data']['alerts']
        firing={a['labels']['alertname'] for a in alerts if a['state']=='firing'}
        for name in names:
            if name in firing and name not in found:
                found[name]=round(time.monotonic()-started,1)
                print(label,name,'firing after',found[name],'seconds',flush=True)
        if all(name in firing for name in names):
            (REPORTS/f'alerts-{label}.json').write_text(json.dumps({
                'captured_utc':datetime.now(timezone.utc).isoformat(),
                'seconds_from_configuration':found,'alerts':alerts},indent=2,ensure_ascii=False))
            return found
        time.sleep(5)
    raise RuntimeError(f'Alerts not firing: {names}; found={found}')


def collect_traces():
    # Jaeger 2.23 exposes the supported OTLP-based v3 query API; decode its
    # streaming JSON envelopes and retain original OTLP spans alongside summaries.
    response=httpx.get('http://127.0.0.1:16686/api/v3/traces',params={
        'query.serviceName':'observable-agent',
        'query.startTimeMin':datetime.fromtimestamp(time.time()-3600,timezone.utc).isoformat(),
        'query.startTimeMax':datetime.now(timezone.utc).isoformat(),
        'query.searchDepth':200},timeout=30)
    response.raise_for_status()
    chunks=[json.loads(line) for line in response.text.splitlines() if line.strip()]
    (REPORTS/'jaeger-query-otlp.json').write_text(json.dumps(chunks,indent=2,ensure_ascii=False))
    grouped={}
    for chunk in chunks:
        for resource in chunk['result'].get('resourceSpans',[]):
            for scope in resource.get('scopeSpans',[]):
                for span in scope.get('spans',[]):
                    tid=span['traceId']
                    tags=[{'key':a['key'],'value':next(iter(a['value'].values()))}
                          for a in span.get('attributes',[])]
                    if span.get('status',{}).get('code') in (2,'STATUS_CODE_ERROR'):
                        tags.append({'key':'error','value':True})
                    normalized={'operationName':span['name'],
                        'duration':(int(span['endTimeUnixNano'])-int(span['startTimeUnixNano']))/1000,
                        'tags':tags,'events':span.get('events',[]),'otlp':span}
                    grouped.setdefault(tid,{'traceID':tid,'spans':[]})['spans'].append(normalized)
    data=[t for t in grouped.values() if len(t['spans'])>=4]
    if not data:
        raise RuntimeError('No Jaeger traces')
    errors=[t for t in data if any(any(tag['key']=='error' and tag['value'] is True
              for tag in s.get('tags',[])) for s in t['spans'])]
    slow=max(data,key=lambda t:max(s['duration'] for s in t['spans']))
    if not errors:
        raise RuntimeError('No error trace')
    error=errors[0]
    logs=command(['logs','--no-color','agent'])
    evidence={}
    for kind,trace in [('slow',slow),('error',error)]:
        tid=trace['traceID']
        matching=[]
        for line in logs.splitlines():
            if tid in line and '{' in line:
                try:
                    matching.append(json.loads(line[line.index('{'):]))
                except json.JSONDecodeError:
                    pass
        if not matching:
            raise RuntimeError('Trace has no matching JSON log: '+tid)
        (REPORTS/f'jaeger-{kind}-trace.json').write_text(json.dumps(trace,indent=2,ensure_ascii=False))
        evidence[kind]={'trace_id':tid,'logs':matching,
                        'spans':[{'name':s['operationName'],'duration_ms':s['duration']/1000}
                                 for s in trace['spans']]}
    (REPORTS/'trace-evidence.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False))
    print('Trace evidence saved:',{k:v['trace_id'] for k,v in evidence.items()},flush=True)


def scaling():
    print(command(['up','-d','--build','--scale','agent=1']),flush=True)
    wait_ready()
    results=[]
    for count in (1,3):
        if count==3:
            command(['up','-d','--scale','agent=3'])
            time.sleep(12)  # Docker DNS refresh; keep comparison free of topology transition errors.
        before=command(['ps','-q','agent']).splitlines()
        assert len(before)==count, f'Expected {count} agents, got {len(before)}'
        args=BASE+['run','--no-deps','--rm','locust','-f','/mnt/locust/locustfile.py','--host','http://nginx',
                   '--headless','-u','100','-r','10','-t','2m','--csv',f'/mnt/results/scale_{count}']
        p=subprocess.run(args,cwd=STACK,env={**os.environ,**DEFAULT},capture_output=True,text=True,timeout=180)
        (REPORTS/f'locust-scale-{count}.txt').write_text(p.stdout+p.stderr)
        if p.returncode not in (0,1):
            raise RuntimeError(p.stdout+p.stderr)
        after=command(['ps','-q','agent']).splitlines()
        assert len(after)==count, f'Locust changed topology: {len(after)} agents'
        results.append({'replicas':count,'verified_container_count':len(after),
                        'users':100,'spawn_rate':10,'duration':'2m','exit_code':p.returncode})
        for path in (STACK/'benchmark-results').glob(f'scale_{count}*.csv'):
            shutil.copy2(path,RESULTS/path.name)
        print('Completed scale',count,'exit code',p.returncode,flush=True)
    (REPORTS/'scaling-run.json').write_text(json.dumps(results,indent=2))


def alerts():
    started=configure(MOCK_ERROR_RATE='0.2',MOCK_SLOW_RATE='0.3')
    start_load()
    timing=poll_alerts(['AgentHighErrorRate','AgentHighLatencyP95'],started,'AB')
    collect_traces()
    (REPORTS/'chaos-AB.json').write_text(json.dumps({'config':{'MOCK_ERROR_RATE':.2,'MOCK_SLOW_RATE':.3},
        'firing_seconds':timing},indent=2))
    print('READY FOR SCREENSHOTS: keep load running, capture Grafana, both Jaeger traces and Prometheus Alerts.',flush=True)


def remaining():
    # AB screenshots/raw snapshots have been saved. Start a fresh evaluator so
    # a cost alert left firing by the high-load baseline is not misattributed to C.
    command(['up','-d','--no-deps','--force-recreate','--renew-anon-volumes','prometheus'])
    for _ in range(30):
        try:
            if httpx.get('http://127.0.0.1:9090/-/ready',timeout=2).status_code==200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    started=configure(LLM_MODEL='mock-llm-large')
    c=poll_alerts(['LLMCostBurnRateHigh'],started,'C')
    command(['up','-d','--scale','agent=3'])  # restore small model before outage experiment
    time.sleep(15)
    container=command(['ps','-q','agent']).splitlines()[0]
    started=time.monotonic()
    subprocess.run(['docker','pause',container],check=True,capture_output=True)
    try:
        d=poll_alerts(['AgentInstanceDown'],started,'D')
    finally:
        subprocess.run(['docker','unpause',container],check=True,capture_output=True)
    configure(AGENT_VERSION='v1')
    time.sleep(65)
    p=subprocess.run([sys.executable,'eval/run_eval.py','--url','http://127.0.0.1:8080',
        '--api-key',DEFAULT['AGENT_API_KEY'],'--baseline',str(REPORTS/'eval_v2_fixed.json'),
        '--out',str(REPORTS/'eval_production_v1.json')],
        cwd=ROOT/'06-lab-complete/benchmark-observability/develop',capture_output=True,text=True)
    (REPORTS/'eval_production_v1.txt').write_text(p.stdout+p.stderr)
    assert p.returncode==1,'Regression should fail the quality gate'
    (REPORTS/'chaos-remaining.json').write_text(json.dumps({'prometheus_reset_before_C':True,'C':c,'D':d,'E':{
        'config':{'AGENT_VERSION':'v1'},'quality_gate_exit_code':p.returncode,
        'alerts_snapshot':request('/api/v1/alerts')['data']['alerts']}},indent=2,ensure_ascii=False))
    command(['up','-d','--scale','agent=3'])
    subprocess.run(['docker','rm','-f','day14-observability-load'],check=True,capture_output=True)
    # Preserve final logs; cleanup is a separate user-visible step after screenshots.
    (REPORTS/'observability-agent.log').write_text(command(['logs','--no-color','agent']))
    print('Experiments C, D, E verified and default v2 restored.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--phase',choices=['scaling','alerts','remaining'],required=True)
    globals()[p.parse_args().phase]()
