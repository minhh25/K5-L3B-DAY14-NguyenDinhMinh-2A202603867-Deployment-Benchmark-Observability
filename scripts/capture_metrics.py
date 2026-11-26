"""Capture PromQL values backing the dashboard, without using rounded UI text."""
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
queries={
 'p95_seconds':'histogram_quantile(0.95, sum by(le)(rate(http_request_duration_seconds_bucket{job="agent",route="/ask"}[1m])))',
 'avg_seconds':'sum(rate(http_request_duration_seconds_sum{job="agent",route="/ask"}[1m])) / sum(rate(http_request_duration_seconds_count{job="agent",route="/ask"}[1m]))',
 'rps_by_instance':'sum by(instance)(rate(http_requests_total{job="agent",route="/ask"}[1m]))',
 'input_tokens_per_second':'sum(rate(llm_tokens_total{job="agent",type="input"}[1m]))',
 'output_tokens_per_second':'sum(rate(llm_tokens_total{job="agent",type="output"}[1m]))',
 'instances_up':'sum(up{job="agent"})',
 'cost_per_hour':'sum(rate(llm_cost_usd_total{job="agent"}[5m]))*3600',
 'agent_versions':'agent_info{job="agent"}',
}
result={'captured_utc':datetime.now(timezone.utc).isoformat(),'queries':{}}
for key,query in queries.items():
    response=httpx.get('http://127.0.0.1:9090/api/v1/query',params={'query':query},timeout=10)
    response.raise_for_status()
    result['queries'][key]={'promql':query,'result':response.json()['data']['result']}
result['external_metrics_status']=httpx.get('http://127.0.0.1:8080/metrics',timeout=10).status_code
(root/'reports/dashboard-metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps(result,ensure_ascii=False))
