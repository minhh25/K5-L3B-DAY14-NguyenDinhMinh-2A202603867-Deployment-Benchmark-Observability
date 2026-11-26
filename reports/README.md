# Bằng chứng chạy lab

Các file ở đây là output từ lệnh/API thật trên máy làm bài, không phải số minh họa. Timestamp gốc thường là UTC; báo cáo dùng GMT+7. Xem `../BENCHMARK_REPORT.md` để đọc bảng số liệu và phân tích.

| Nhóm | File chính |
|---|---|
| Môi trường và hash file được bảo vệ | `environment.json` |
| Part 6, script chấm đầy đủ | `production-readiness.txt` — PASS 12/12, 43/43 checks |
| Redis concurrency | `guard-integration-tests.txt` — 4 test |
| Part 1/2/4/5 | `cp1-*.txt`, `cp2-*.txt`, `cp3-*.txt`, `cp4-*.txt`, `docker-image-sizes.json` |
| Benchmark local cuối | `load_v2_c*.json`, `load_v2_slow_*.json`, `benchmark-run.json` |
| Chất lượng | `eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`, `eval_regression.json` |
| Lượt đầu, trước khi dừng các build Docker và hoàn thiện histogram | `initial-benchmark/` (giữ riêng, không trộn vào bảng local cuối) |
| Metrics | `develop-metrics.txt`, `production-metrics.txt`, `dashboard-metrics.json` |
| Số container thực tế khi scale | `scaling-run.json`; CSV ở `../benchmark-results/` |
| Traces | `jaeger-query-otlp.json` (phản hồi gốc), `jaeger-slow-trace.json`, `jaeger-error-trace.json` (summary + OTLP gốc), `trace-evidence.json` (JSON log cùng ID) |
| Alert và thời gian phát hiện | `alerts-AB.json`, `alerts-C.json`, `alerts-D.json`, `chaos-AB.json`, `chaos-remaining.json` |
| Hạ về v1 trong production stack | `eval_production_v1.json` — cố ý fail quality gate |
| Alert rule unit test | `prometheus-rule-tests.txt` |
| Deploy Render | `public-deployment.json` — bốn kết quả, không lưu key |
| Kiểm tra bộ bài nộp | `submission-audit.json` |

Load test/Locust và eval regression có thể trả exit code 1 đúng mục đích thí nghiệm; đây không phải bằng chứng script hỏng. Xem report JSON để phân biệt vi phạm SLO/quality gate với lỗi khởi động. Log observability-alerts có giữ lần xuất trace theo API cũ bị 404 và phần ghi nhận đã khôi phục bằng API v3.

Ảnh thật nằm ở `../screenshots/`. URL Render và bốn kết quả kiểm tra nằm trong `public-deployment.json`; 200 có key là response Swagger do chủ repo cung cấp, ba phép còn lại được assistant kiểm tra trực tiếp. Ảnh gốc Live/log và Postman 200 đã được lưu thành `../screenshots/running.png` và `../screenshots/test.png`; còn `../screenshots/dashboard.png`. CI YAML đã có; trạng thái chạy trên GitHub chưa được xác minh trong bộ bằng chứng này.
