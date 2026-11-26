"""Render the submission report solely from measured JSON/CSV evidence."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'reports'
def read(name):
    return json.loads((R/name).read_text())
def flag(value):
    return 'PASS' if value else 'FAIL'
def percent(value):
    return f'{value*100:.2f}%'
def scalar(metrics,name):
    result=metrics['queries'][name]['result']
    return float(result[0]['value'][1]) if result else float('nan')
def locust(count):
    rows=list(csv.DictReader((ROOT/f'benchmark-results/scale_{count}_stats.csv').open()))
    return next(row for row in rows if row['Name']=='/ask')

def main():
    env=read('environment.json')
    meta=read('benchmark-run.json')
    deployed=(R/'public-deployment.json').exists()
    missing_cloud=[name for name in ('dashboard.png','running.png','test.png')
                   if not (ROOT/'screenshots'/name).exists()]
    cloud_note=('còn thiếu '+', '.join('screenshots/'+name for name in missing_cloud)
                if missing_cloud else 'đã có đủ ba ảnh cloud')
    deployment_note=('Agent Part 6 đã deploy Render; bốn kết quả public nằm trong reports/public-deployment.json; '+cloud_note+'.'
                     if deployed else 'Deploy Render đang chờ chủ repo.')
    local_time=datetime.fromisoformat(meta['started_utc']).astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
    v1,v2,fixed=[read(name) for name in ['eval_v1.json','eval_v2.json','eval_v2_fixed.json']]
    ab=read('chaos-AB.json')
    remaining=read('chaos-remaining.json')
    traces=read('trace-evidence.json')
    metrics=read('dashboard-metrics.json')
    rows=[]
    for c in [1,10,50,100]:
        result=read(f'load_v2_c{c}.json')
        lat=result['latency_ms']
        rows.append(f"| {c} | {result['rps']} | {lat['p50']} | {lat['p95']} | {lat['p99']} | {percent(result['error_rate'])} | {flag(result['slo']['passed'])} |")
    tail=[]
    for slow in ['0','0.03','0.1']:
        result=read(f'load_v2_slow_{slow}.json')
        lat=result['latency_ms']
        tail.append(f"| {slow} | {lat['avg']} | {lat['p95']} | {lat['p99']} |")
    text=f'''# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyễn Đình Minh
**Ngày chạy:** {local_time.strftime('%d/%m/%Y %H:%M')} (GMT+7; timestamp gốc UTC trong JSON).
**Môi trường:** {env['host_cpu']}, RAM {env['host_memory_bytes']/1024**3:.0f} GiB; {env['platform']}; Python {env['python'].split()[0]}. Docker Desktop {env['docker']['ServerVersion']}, {env['docker']['NCPU']} CPU / {env['docker']['MemTotal']/1024**3:.2f} GiB RAM cho VM. Agent observability giới hạn 0.5 CPU / 256 MiB mỗi container, một worker/container.

Mọi số trong bảng được sinh từ JSON/CSV đính kèm bởi `scripts/generate_benchmark_report.py`. Chi phí là chi phí mô phỏng, không phải hóa đơn API. Bảng local dùng lượt cuối trên code có đầy đủ histogram độ dài câu hỏi, sau khi dừng stack Docker gây tải; lượt đầu chạy trong lúc build Docker được giữ nguyên ở `reports/initial-benchmark/` để thấy ảnh hưởng môi trường, không trộn số hai lượt. Đo trên máy dùng chung, một lượt mỗi cấu hình; không coi đây là cam kết capacity hoặc bằng chứng latency của LLM thật. {deployment_note} Part 7 là stack chạy local độc lập với Part 6.

## 1. SLO của agent

| SLI | SLO | Lý do |
|---|---|---|
| p95 `/ask` | ≤ 500 ms | Giữ trải nghiệm phần lớn request nhanh, thấy được queue/tail khi tăng tải |
| Error rate `/ask` | ≤ 2% | Có dư địa cho mock upstream lỗi ngẫu nhiên mặc định 1% |
| Accuracy cuối trên golden dataset | 100% (23/23), không regression | Mục tiêu hoàn thành CP7; không suy rộng ra mọi câu hỏi ngoài dataset |

`load_test.py` mặc định kiểm ≤, nên báo cáo dùng cùng phép so sánh. Ngưỡng alert (error >5%, p95 >1s) lỏng hơn ngưỡng SLO và có `for` để hạn chế nhiễu.

## 2. Benchmark hiệu năng local

### 2.1 Concurrency vs latency — v2, KB baseline

300 request/lượt, model small, `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`; warm-up không tính vào report. Latency của công cụ chỉ thống kê response thành công; error rate tính mọi request.

| Concurrency | RPS | p50 ms | p95 ms | p99 ms | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
'''+ '\n'.join(rows)+'''

RPS không tăng tuyến tính vì còn giới hạn scheduling, connection pool, CPU, logging, retrieval và provider latency. Concurrency quá cao tạo hàng đợi, làm percentile tăng; cần đọc đồng thời RPS và p95 thay vì chọn cấu hình có nhiều request song song nhất. Số đo và exit code từng lượt: `reports/benchmark-run.json`, `reports/load_v2_c*.json` và các file TXT tương ứng. Không sửa số để ép SLO PASS.

### 2.2 Tail latency — cùng 300 request, concurrency 20

| MOCK_SLOW_RATE | avg ms | p95 ms | p99 ms |
|---|---:|---:|---:|
'''+ '\n'.join(tail)+'''

Average trộn phần lớn request nhanh với số ít request chậm nên che giấu trải nghiệm phần đuôi. Khi tỷ lệ chậm khoảng 3%, p99 thường nhạy hơn p95; khi tăng tới 10%, p95 cũng nằm trong nhóm chậm. SLO nên theo p95/p99 kết hợp error rate. Mẫu chỉ 300 request và lỗi/jitter ngẫu nhiên làm các percentile dao động; không dùng 23 câu eval để kết luận latency.

### 2.3 Instrumentation — Exercise 7.1

Đã thêm Histogram `agent_question_length_chars` (bucket 20/50/100/200/500/1000/2000) ở bản develop và production, observe độ dài câu hỏi trước gọi agent. Không dùng độ dài làm label. `reports/develop-metrics.txt` có sample thật và phép thử URL lạ được gom về `route="unmatched"`.

Counter: `http_requests_total`, `llm_tokens_total`, `llm_cost_usd_total`; Gauge: `agent_in_flight_requests`; Histogram: `http_request_duration_seconds`, `agent_question_length_chars`. Dùng `route.path` template tránh tạo series mới cho mỗi ID/URL bot quét. Cardinality tăng theo tích các label values; không gắn user_id, request_id hoặc nội dung câu hỏi vào metric.

## 3. Benchmark chất lượng

| Chỉ số | v1 | v2 baseline | v2 đã sửa KB |
|---|---:|---:|---:|
'''
    for label,key in [('Accuracy','accuracy'),('Avg tokens/câu','avg_tokens'),('Tổng cost USD','total_cost_usd'),('Cost/câu đúng USD','cost_per_correct_usd')]:
        values=[percent(x[key]) if key=='accuracy' else str(x[key]) for x in [v1,v2,fixed]]
        text+='| '+label+' | '+' | '.join(values)+' |\n'
    text+='| Quality gate | '+' | '.join(flag(x['quality_gate']['passed']) for x in [v1,v2,fixed])+' |\n'
    text+='''
Baseline giữ KB gốc qua `MOCK_KB_PATCHES=0`; mặc định `1` bật hai mục bổ sung. Hai bản mock develop/production có cùng sửa đổi. Không sửa golden dataset hoặc script eval.

| ID sai ban đầu | Keyword thiếu (từ report) | Cách sửa |
|---|---|---|
'''
    for item in v2['results']:
        if not item['passed']:
            fix={'security-02':'Bổ sung tài liệu JWT/API key: token, hết hạn, chữ ký',
                 'scaling-03':'Bổ sung tài liệu HPA: CPU, memory, custom metrics'}.get(item['id'],'Xem KB và report')
            text+=f"| {item['id']} | {', '.join(item.get('missing_keywords',[]))} | {fix} |\n"
    text+=f'''
V2 sau sửa đạt **{fixed['passed']}/{fixed['total']}**, regressions: **{len(fixed['quality_gate']['regressions'])}**. V2 thêm context nên token/câu tăng; cần so cost/câu đúng bên cạnh cost/câu. Tỷ lệ v1/v2 về cost/câu đúng trong lần đo là {(v1['cost_per_correct_usd']/fixed['cost_per_correct_usd']):.2f} lần.

Chấm keyword chỉ yêu cầu ≥60% keyword/câu; đây là phép kiểm thử cố định của lab, không phải đánh giá semantic đầy đủ. Với production cần dataset lớn/đại diện hơn, đánh giá an toàn và theo dõi chất lượng sau deploy.

### Quality gate trong CI

Workflow `.github/workflows/eval.yml` khởi động candidate v2, tắt lỗi/chậm ngẫu nhiên để đánh giá chất lượng ổn định, yêu cầu accuracy 100% và không regression với baseline đã lưu. Ngưỡng này chặt hơn yêu cầu 85% của Exercise 7.3. Chạy cố ý v1 với baseline v2 fixed trả exit code 1, có {len(read('eval_regression.json')['quality_gate']['regressions'])} regressions (`reports/eval_regression.json`). Muốn chặn merge thực sự phải bật required status check trong branch protection; chưa tuyên bố workflow đã chạy trên GitHub.

## 4. Observability stack

### 4.1 Bằng chứng

- [Grafana có tải](screenshots/grafana-dashboard.png)
- [Jaeger trace chậm](screenshots/jaeger-slow-trace.png)
- [Jaeger trace lỗi](screenshots/jaeger-error-trace.png)
- [Prometheus: ≥2 alert cùng firing](screenshots/prometheus-alert-firing.png)

Prometheus pull `/metrics` trực tiếp từ từng agent qua Docker DNS, Grafana query Prometheus; OpenTelemetry gửi traces qua OTLP/HTTP tới Jaeger. Agent JSON log chứa trace_id. `/metrics` qua Nginx trả **{metrics['external_metrics_status']}** để không public thông tin vận hành.

### 4.2 Đọc dashboard — Exercise 7.4

Snapshot PromQL ở `reports/dashboard-metrics.json`, thời điểm {metrics['captured_utc']}:

- p95 = **{scalar(metrics,'p95_seconds')*1000:.2f} ms**; avg = **{scalar(metrics,'avg_seconds')*1000:.2f} ms**. Khoảng cách phản ánh tail latency; histogram quantile là ước lượng bucket và không trùng hoàn toàn percentile client-side của Locust.
- Số instance up = **{scalar(metrics,'instances_up'):.0f}**. RPS từng instance:

| Instance | req/s |
|---|---:|
'''
    for item in metrics['queries']['rps_by_instance']['result']:
        text+=f"| {item['metric'].get('instance','?')} | {float(item['value'][1]):.2f} |\n"
    text+=f'''
Đọc sự phân phối trên các instance thay vì giả định round-robin luôn cho số request bằng hệt nhau; connection reuse và cửa sổ rate gây chênh lệch. Input token rate **{scalar(metrics,'input_tokens_per_second'):.2f}/s**, output **{scalar(metrics,'output_tokens_per_second'):.2f}/s**. Input gồm system prompt, câu hỏi và context retrieval; output là câu trả lời ngắn nên input có thể lớn hơn output. Local benchmark dùng 3 instance theo K5 thay vì cố định 2 của ví dụ dashboard.

### 4.3 Thí nghiệm gây lỗi

Locust 30 users, ramp-up 5 users/s. A và B được bật đồng thời để giữ cả hai alert cùng firing trong một ảnh; phép đo này kiểm chứng lỗi/chậm đồng thời, không suy diễn chúng là hai thí nghiệm cô lập. Mốc đo tính từ lúc bắt đầu áp dụng cấu hình, bao gồm thời gian recreate/DNS/scrape/evaluation; polling mỗi 5 giây.

| Thí nghiệm | Cấu hình/thao tác | Alert | Giây đến firing |
|---|---|---|---:|
| A | MOCK_ERROR_RATE=0.2 | AgentHighErrorRate | {ab['firing_seconds']['AgentHighErrorRate']} |
| B | MOCK_SLOW_RATE=0.3 | AgentHighLatencyP95 | {ab['firing_seconds']['AgentHighLatencyP95']} |
| C | LLM_MODEL=mock-llm-large | LLMCostBurnRateHigh | {remaining['C']['LLMCostBurnRateHigh']} |
| D | Pause 1 container đang còn trong DNS | AgentInstanceDown | {remaining['D']['AgentInstanceDown']} |
| E | AGENT_VERSION=v1 | Quality gate thay vì alert chất lượng | eval exit {remaining['E']['quality_gate_exit_code']} |

A làm panel error rate tăng, B làm p95/p99 tăng và xuất hiện span LLM chậm; C tăng chi phí mô phỏng theo model, D làm target up=0. Sau khi lưu ảnh/JSON của AB, evaluator Prometheus được tạo lại với storage tạm mới trước C để cảnh báo chi phí từ lượt tải cao trước đó không bị gán nhầm cho model lớn; điều này được ghi trong chaos-remaining.json. Rule có for nên đi qua inactive → pending → firing; for không bao gồm toàn bộ thời gian scrape và cửa sổ rate. Promtool unit tests đã SUCCESS (`reports/prometheus-rule-tests.txt`).

E làm mất retrieval và chất lượng giảm. Metric hạ tầng không đo tính đúng của câu trả lời; cần eval, canary quality checks hoặc feedback người dùng. Các alert vận hành có thể còn tồn tại tạm thời từ C/D vì cửa sổ rate và sự cố trước đó; snapshot được lưu nguyên trong `reports/chaos-remaining.json`, không gán chúng cho lỗi chất lượng của v1. Eval production v1 thực tế: {read('eval_production_v1.json')['passed']}/{read('eval_production_v1.json')['total']} câu đúng.

### 4.4 Debug trace và log

'''
    for kind,title in [('slow','Trace chậm'),('error','Trace lỗi')]:
        evidence=traces[kind]
        spans=evidence['spans']
        duration=max(s['duration_ms'] for s in spans)
        chat=max((s for s in spans if s['name'].startswith('chat ')),key=lambda s:s['duration_ms'])
        text+=f"**{title}:** `{evidence['trace_id']}`. Tổng {duration:.3f} ms; span LLM `{chat['name']}` {chat['duration_ms']:.3f} ms ({chat['duration_ms']/duration*100:.2f}% tổng).\n\n"
        text+='| Span | ms |\n|---|---:|\n'
        for span in spans:
            text+=f"| {span['name']} | {span['duration_ms']:.3f} |\n"
        log=next((x for x in evidence['logs'] if x['event']==('llm_error' if kind=='error' else 'llm_call')),evidence['logs'][0])
        text+='\nLog JSON có cùng trace_id:\n\n```json\n'+json.dumps(log,ensure_ascii=False,indent=2)+'\n```\n\n'
    text+='''Trường `llm_ms` trong log dùng delay do mock tính trước; span đo thời gian thực tế nên còn có scheduling/instrumentation overhead. Không yêu cầu hai số bằng nhau. Trace AB giải thích request trong thí nghiệm đó, không đủ để kết luận mọi request của lượt scale 100 users có cùng nút thắt.

Trace được xuất qua [API v3 chính thức của Jaeger](https://www.jaegertracing.io/docs/2.23/architecture/apis/). Hai file `reports/jaeger-slow-trace.json`, `reports/jaeger-error-trace.json` có summary chuẩn hóa và giữ nguyên OTLP span trong field `otlp`; toàn bộ phản hồi query trong `reports/jaeger-query-otlp.json`, mapping trace/log trong `reports/trace-evidence.json`. Trace chậm được chọn là trace có thời lượng lớn nhất trong tập trả về với searchDepth=200 lúc thu bằng chứng; searchDepth là gợi ý cho backend, không bảo đảm giới hạn chính xác và không chứng minh lớn nhất mọi traffic.

## 5. Benchmark scaling — Locust headless

100 users, ramp-up 10 users/s, 2 phút/lượt. Dùng `--no-deps` khi chạy Locust để Compose không đổi số replica về mặc định. `reports/scaling-run.json` xác nhận số container trước/sau lượt đo. Bảng đọc dòng **POST /ask** trong CSV; file cũng có dòng `/health` và Aggregated.

| Instance | RPS /ask | p50 ms | p95 ms | p99 ms | Failures / requests |
|---|---:|---:|---:|---:|---|
'''
    scaling=[locust(1),locust(3)]
    for count,row in zip([1,3],scaling):
        text+=f"| {count} | {float(row['Requests/s']):.2f} | {row['50%']} | {row['95%']} | {row['99%']} | {row['Failure Count']} / {row['Request Count']} |\n"
    ratio=float(scaling[1]['Requests/s'])/float(scaling[0]['Requests/s'])
    text+=f'''
Trong lần đo, RPS 3/1 instance = **{ratio:.2f} lần**; p95 đổi từ **{scaling[0]['95%']}** sang **{scaling[1]['95%']} ms**. Scale bổ sung CPU/worker để giảm queue nhưng không loại bỏ latency giả lập bên trong LLM. Khi model/LLM là nút thắt, tăng instance không bảo đảm p95 giảm tuyến tính. Locust còn có think time 0.5–2 giây giữa request, nên RPS không phải công suất cực đại của API. Một phần lỗi là upstream 503 mô phỏng; xem file failures/CSV gốc để phân biệt lỗi kết nối và mã HTTP.

## 6. Kết luận và giới hạn

1. Đo hiệu năng và chất lượng là hai việc riêng: hạ tầng xanh không bảo đảm câu trả lời đúng.
2. Percentile, error rate và trace bổ trợ nhau; trace/log giải thích request cụ thể sau khi metrics phát hiện bất thường.
3. Scale phải được kiểm đếm thực tế; không dùng nhãn file scale_1/scale_3 để suy ra số container đang chạy.

Nếu triển khai thật sẽ bổ sung quality canary, timeout/retry có giới hạn, dependency latency, budget burn theo tenant, queue saturation và cảnh báo mất telemetry. Prometheus label giữ cardinality thấp; sampling tracing có thể giảm tài nguyên nhưng giảm cơ hội giữ được request hiếm. Stack lab Grafana anonymous/admin mặc định chỉ dùng local.

Các lỗi mẫu đã sửa để tái chạy được: handler SIGTERM của ví dụ Part 5 nuốt signal khi import qua CLI; Dockerfile Part 7 copy dependencies sang home khác với HOME của user. Không sửa script chấm hoặc golden dataset. Trạng thái deploy thật xem `DEPLOYMENT.md` và `reports/public-deployment.json`; các phép đo Part 7 ở đây vẫn là local. Kết quả CI trên GitHub chưa được xác minh trong báo cáo này.
'''
    (ROOT/'BENCHMARK_REPORT.md').write_text(text)
    print('Generated BENCHMARK_REPORT.md from measured evidence.')

if __name__=='__main__':
    main()
