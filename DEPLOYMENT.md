# Deployment — Day 14

**Trạng thái:** agent Part 6 đã deploy lên Render. Health, readiness và chặn request thiếu key đã được kiểm tra trực tiếp; chủ repo đã cung cấp kết quả Swagger có key trả 200. Bằng chứng đã che secret: [public-deployment.json](reports/public-deployment.json). Còn bổ sung ba ảnh cloud để hoàn tất bài nộp.

## Cấu hình Render

Đã chuẩn bị Blueprint tại `06-lab-complete/render.yaml`. Trong Render, kết nối repo này và chọn Blueprint path đó. File đặt `rootDir: 06-lab-complete`; Dockerfile và Docker build context tính tương đối từ rootDir.

Nếu tạo Web Service bằng tay:

| Trường | Giá trị |
|---|---|
| Runtime | Docker |
| Root Directory | `06-lab-complete` |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context | `.` |
| Health Check Path | `/health` |

Tạo Redis/Render Key Value trong cùng vùng với web service, lấy Internal Redis URL và đặt `REDIS_URL` cho agent. Chọn plan theo tài khoản của bạn; repo không tự tạo tài nguyên cloud hoặc cam kết chi phí. Không dùng `localhost` hoặc tên service Docker `redis` làm hostname Redis trên Render.

| Biến | Cách đặt |
|---|---|
| `AGENT_API_KEY` | Blueprint sinh ngẫu nhiên bằng `generateValue`; nếu tạo tay thì đặt secret riêng |
| `REDIS_URL` | Internal URL của Redis, nhập ở Render (`sync: false`) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` (ngân sách mô phỏng của lab) |
| `LOG_LEVEL` | `INFO` |
| `PORT` | Dùng giá trị nền tảng cấp; CMD đọc biến này |

`OPENAI_API_KEY` không cần thiết: agent dùng mock LLM. Không ghi API key/Redis credentials vào tài liệu hoặc commit.

## URL public

[Agent Day14 trên Render](https://k5-l3b-day14-nguyendinhminh-2a202603867.onrender.com).

| Request public | HTTP | Nguồn bằng chứng |
|---|---:|---|
| GET /health | 200 | Assistant kiểm tra trực tiếp |
| GET /ready | 200 | Assistant kiểm tra trực tiếp, ready=true |
| POST /ask thiếu key | 401 | Assistant kiểm tra trực tiếp |
| POST /ask có key | 200 | Chủ repo chạy Swagger, 26/11/2026 15:04:58 GMT+7 |

Response có key chứa answer về Docker và usage; API key được loại khỏi bản lưu.

## Tự kiểm tra sau deploy

Đặt `BASE` là URL của service, đặt `AGENT_API_KEY` trong shell bằng giá trị secret trên Render. Các lệnh sau chỉ in HTTP status, không in key:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

Kết quả mong đợi lần lượt: **200, 200, 401, 200**. Nếu `/ready` trả 503, kiểm tra URL, vùng, quyền kết nối Redis và log. `/health` vẫn 200 khi Redis không kết nối được để phân biệt liveness/readiness.

Sau khi thành công, bổ sung `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` từ Render và các phép thử thật. Service đã deploy; ba ảnh này vẫn chờ chủ repo bổ sung. Khi chụp Swagger, ẩn phần Curl hoặc che giá trị X-API-Key. Không commit ảnh Environment có secret.

## Railway và Cloud Run

`06-lab-complete/railway.toml` là cấu hình thay thế: đặt service root directory là `06-lab-complete`, builder Dockerfile, healthcheck `/health`; vẫn cần Redis và env vars. Render Blueprint mô tả service bằng YAML, có rootDir và khai báo env/secret; Railway dùng TOML tách `[build]`/`[deploy]`.

Pipeline mẫu Cloud Run ở `03-cloud-deployment/production-cloud-run/`: chạy pytest, build Docker image với tag commit, push registry rồi deploy lên Cloud Run. `service.yaml` mô tả CPU/memory, concurrency, min/max instance, env/secret và probes. Theo K5 chỉ cần đọc và giải thích, không triển khai GCP.
