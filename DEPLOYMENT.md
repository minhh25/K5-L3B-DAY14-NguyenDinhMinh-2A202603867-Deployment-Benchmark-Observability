# Deployment — Day 14

**Trạng thái:** code và cấu hình local đã hoàn thiện. Chưa deploy Render theo yêu cầu của chủ repo; chưa có URL public hoặc ảnh cloud. Không coi kiểm tra cấu hình deploy trong `PASS 12/12` là bằng chứng đã chạy trên cloud.

## Render: cấu hình sau

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

**Chờ điền sau khi Render deploy:** `<RENDER_PUBLIC_URL>`.

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

Sau khi thành công, bổ sung `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` từ Render và các phép thử thật. Các ảnh này hiện chưa được tạo vì chưa deploy.

## Railway và Cloud Run

`06-lab-complete/railway.toml` là cấu hình thay thế: đặt service root directory là `06-lab-complete`, builder Dockerfile, healthcheck `/health`; vẫn cần Redis và env vars. Render Blueprint mô tả service bằng YAML, có rootDir và khai báo env/secret; Railway dùng TOML tách `[build]`/`[deploy]`.

Pipeline mẫu Cloud Run ở `03-cloud-deployment/production-cloud-run/`: chạy pytest, build Docker image với tag commit, push registry rồi deploy lên Cloud Run. `service.yaml` mô tả CPU/memory, concurrency, min/max instance, env/secret và probes. Theo K5 chỉ cần đọc và giải thích, không triển khai GCP.
