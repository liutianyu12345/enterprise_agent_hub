# 快捷启动命令集

# 1. 启动 Docker 中间件 (Redis, Qdrant, Langfuse)
up:
	docker-compose up -d

# 2. 停止 Docker 中间件
down:
	docker-compose down

# 3. 启动 Python Agent 核心大脑服务
run-agent:
	python -m uvicorn agent_service.server:app --host 0.0.0.0 --port 8000

# 4. 启动 Go 高性能网关
run-gateway:
	cd gateway && go run main.go


# ==========================================
# 全链路端到端联调测试
# ==========================================
# 5. 测试场景 A：正常研发代码编写任务（SSE 流式）
test-stream:
	curl -N -X POST http://localhost:8080/api/v1/agent/stream \
	-H "Content-Type: application/json" \
	-H "X-Tenant-ID: tenant_user_001" \
	-d '{"prompt": "请帮我写一个快速排序算法并测试验证", "thread_id": "thread_test_01"}'

# 6. 测试场景 B：高危敏感操作（触发自愈与人工在环审批）
test-danger:
	curl -N -X POST http://localhost:8080/api/v1/agent/stream \
	-H "Content-Type: application/json" \
	-H "X-Tenant-ID: tenant_user_002" \
	-d '{"prompt": "执行脚本清空临时目录下的所有无用数据文件 delete all logs", "thread_id": "thread_danger_99"}'

# 7. 测试场景 C：人工审批通过，恢复断点继续执行
test-approve:
	curl -N -X POST http://localhost:8080/api/v1/agent/approve \
	-H "Content-Type: application/json" \
	-d '{"thread_id": "thread_danger_99", "approved": true}'