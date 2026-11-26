# Chạy bài Day14 đã hoàn thiện

Code, số đo và bằng chứng local đã được thực hiện trong repo. Việc deploy Render được để lại theo yêu cầu; xem `DEPLOYMENT.md`. Script chấm báo PASS là kiểm tra code/config local, không xác nhận URL cloud.

## 1. Môi trường

Python 3.11 được dùng cho lần đo, Docker Desktop phải đang chạy. Từ gốc repo:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r 06-lab-complete/requirements.txt \
  -r 06-lab-complete/benchmark-observability/develop/requirements.txt
python scripts/setup_local.py
```

`setup_local.py` tạo `.env` với key ngẫu nhiên nếu chưa có; không ghi đè file đang tồn tại và không in key. `.env` bị Git và Docker ignore.

## 2. Agent Part 6

```bash
cd 06-lab-complete
docker compose -p k5-day14-final up -d --build
curl -i http://localhost:8000/health
curl -i http://localhost:8000/ready
```

Đặt `AGENT_API_KEY` trong shell theo `.env` rồi gọi:

```bash
curl -i -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is Docker?"}'
```

Không có/sai key → 401; body không hợp lệ → 422; vượt rate limit → 429 với Retry-After; không đủ budget → 402; Redis lỗi → /ready 503, /health 200 và /ask 503. Rate-limit accounting thực hiện trước kiểm tra budget, nên request đã xác thực nhưng hết budget vẫn được tính vào giới hạn tốc độ.

Chi phí và rate limit được lưu trong Redis, key chứa hash API key. Rate limit dùng Lua atomic và Redis TIME; budget theo ngày UTC dùng Lua reserve chi phí, sau đó đối soát token thực tế. Reservation dùng mức trần output 512 token ước lượng của mock; nếu thay mock bằng LLM thật phải dùng giới hạn max_output_tokens và usage do provider trả về. Nếu process chết sau reserve, phần dự trữ còn lại được giữ theo hướng bảo thủ đến hết ngày.

Redis dùng AOF và `noeviction` để tránh mất state do eviction; persistence của cloud Redis do nền tảng quản lý. Trạng thái ứng dụng là stateless; conversation history không phải yêu cầu Part 6.

```bash
python check_production_ready.py
# Kết quả đã đo: PASS 12/12, 43/43 checks.
docker compose -p k5-day14-final down
```

## 3. Tái chạy ví dụ và benchmark

Từ gốc repo, với virtualenv đã kích hoạt:

```bash
python scripts/run_checkpoints.py
# Build hai image Part 2 trước khi chạy script Docker:
docker build -f 02-docker/develop/Dockerfile -t day14-agent:develop .
docker build -f 02-docker/production/Dockerfile -t day14-agent:advanced .
python scripts/run_docker_checkpoints.py
python scripts/run_benchmarks.py
```

Script Docker dùng project riêng, dừng stack Part 2/5 sau mỗi lượt. Benchmark khởi động/dừng v1 và v2, chạy 300 request ở concurrency 1/10/50/100, ba mức slow rate, eval trước/sau sửa KB và một phép thử regression có chủ ý. Baseline v2 dùng `MOCK_KB_PATCHES=0`; mặc định `1` bật KB đã sửa. Không sửa golden dataset. Kết quả lưu ở `reports/` và bản JSON CP7 ở thư mục develop.

Một lượt load test có thể FAIL SLO do độ trễ/lỗi mô phỏng hoặc tải thực tế; số đo cũ không được dùng làm cam kết tốc độ trên máy khác.

## 4. Observability

Từ gốc repo:

```bash
python scripts/run_observability.py --phase scaling
python scripts/run_observability.py --phase alerts
# Chụp Grafana, Jaeger và Prometheus lúc 2 alert cùng firing.
python scripts/run_observability.py --phase remaining
```

Phase scaling chạy 100 users, ramp-up 10 users/s, 2 phút mỗi mức 1 và 3 instance. Lệnh `compose run --no-deps` giữ nguyên số replica đã cấu hình, tránh việc Compose tự đưa dependency agent về mặc định 2 replicas; script xác nhận số container cả trước và sau lượt đo. Phase alerts tăng error/slow rate đồng thời và để một Locust load generator chạy nền để giữ alert firing khi chụp ảnh. Phase remaining chạy model lớn, pause instance, chuyển v1 và kiểm quality gate, rồi khôi phục v2/dừng load.

| Dịch vụ | Địa chỉ |
|---|---|
| Agent qua Nginx | http://localhost:8080 |
| Grafana | http://localhost:3000 (dashboard provision sẵn; admin/admin chỉ dành cho lab) |
| Prometheus | http://localhost:9090/alerts |
| Jaeger | http://localhost:16686 (service observable-agent) |
| Locust | http://localhost:8089 |

Stack local dùng key mẫu `day14-lab-key`. Nginx chặn `/metrics`; Prometheus scrape agent trực tiếp qua network Docker. Mỗi container agent chạy một worker vì prometheus_client lưu metrics trong memory của process; scale bằng số container.

Script xuất trace theo [API v3 của Jaeger](https://www.jaegertracing.io/docs/2.23/architecture/apis/), giữ OTLP span gốc trong JSON và chuẩn hóa tên/duration để viết báo cáo. Trước thí nghiệm C, sau khi đã lưu ảnh và JSON AB, script tạo lại Prometheus với storage tạm mới để tách cảnh báo chi phí cũ khỏi lần đổi model.

Dùng đúng `-p k5-day14-observability` với mọi lệnh logs/up/down. Sau khi lưu bằng chứng:

```bash
cd 06-lab-complete/benchmark-observability/production
docker compose -p k5-day14-observability down -v
```

## 5. Kiểm thử bổ sung và CI

Từ gốc repo:

```bash
docker run -d --name day14-integration-redis -p 127.0.0.1:16379:6379 redis:7-alpine
cd 06-lab-complete
REDIS_URL=redis://localhost:16379/0 ../.venv/bin/python -m unittest discover -s tests -v
docker rm -f day14-integration-redis
```

Bốn test kiểm tra 40 lần gọi đồng thời chỉ 5 lượt được nhận, dọn request hết hạn, reservation ngân sách đồng thời và đối soát chi phí. Chỉ dùng Redis thử nghiệm; test tự xóa namespace riêng của nó.

Hai workflow GitHub Actions: `production-readiness.yml` kiểm đủ 12 tiêu chí, concurrency guards và promtool; `eval.yml` kiểm candidate đạt 23/23, không regression so với báo cáo baseline đã nộp. Cần bật branch protection yêu cầu hai jobs nếu muốn GitHub thực sự cấm merge khi job đỏ. Workflow đã được tạo; chưa có kết quả chạy trên GitHub trong phiên làm này.
