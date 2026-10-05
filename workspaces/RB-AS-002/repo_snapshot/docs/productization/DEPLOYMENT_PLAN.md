# AgentShield V3 部署方案

## 部署架构

```
                    ┌─────────────────────────────────────┐
                    │           Load Balancer              │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────┐
                    │         AgentShield API              │
                    │         (FastAPI + Uvicorn)          │
                    │         Port: 8090                   │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     ┌────────┴────────┐  ┌───────┴───────┐  ┌────────┴────────┐
     │  Risk Engine    │  │  Audit Logger │  │  Benchmark      │
     │  (贝叶斯网络)   │  │  (链路追踪)   │  │  (评测引擎)     │
     └────────┬────────┘  └───────┬───────┘  └────────┬────────┘
              │                    │                    │
     ┌────────┴────────────────────┴────────────────────┴────────┐
     │                    Storage Layer                           │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
     │  │ SQLite/  │  │  Redis   │  │  File    │                │
     │  │ Postgres │  │  (缓存)  │  │  Storage │                │
     │  └──────────┘  └──────────┘  └──────────┘                │
     └──────────────────────────────────────────────────────────┘
```

## 部署方式

### 方式一：Docker Compose（推荐）

```yaml
# docker-compose.yml
version: '3.8'

services:
  agentshield:
    build: .
    ports:
      - "8090:8090"
    environment:
      - DATABASE_URL=sqlite:///data/agentshield.db
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=INFO
      - AUTH_ENABLED=true
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  dashboard:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://agentshield:8090
    depends_on:
      - agentshield
    restart: unless-stopped

volumes:
  redis_data:
```

启动命令：
```bash
docker-compose up -d
```

### 方式二：裸机部署

```bash
# 1. 环境准备
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置
export DATABASE_URL=sqlite:///data/agentshield.db
export REDIS_URL=localhost:6379
export LOG_LEVEL=INFO

# 3. 初始化数据库
python -c "from backend.app.database import init_db; init_db()"

# 4. 启动
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8090
```

### 方式三：Kubernetes

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentshield
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agentshield
  template:
    metadata:
      labels:
        app: agentshield
    spec:
      containers:
      - name: agentshield
        image: agentshield:v3.1
        ports:
        - containerPort: 8090
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: agentshield-secrets
              key: database-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| DATABASE_URL | 否 | sqlite:///data/agentshield.db | 数据库连接 |
| REDIS_URL | 否 | localhost:6379 | Redis连接 |
| LOG_LEVEL | 否 | INFO | 日志级别 |
| AUTH_ENABLED | 否 | false | 是否启用认证 |
| API_KEY | 否 | - | API密钥（启用认证时必填） |
| CORS_ORIGINS | 否 | * | 允许的跨域来源 |

## 硬件要求

| 环境 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 开发/测试 | 2核 | 4GB | 10GB |
| 生产（小规模） | 4核 | 8GB | 50GB |
| 生产（大规模） | 8核+ | 16GB+ | 100GB+ |

## 监控

- 健康检查: `GET /health`
- 指标暴露: `GET /metrics`（Prometheus格式）
- 日志: 结构化JSON日志，输出到stdout或文件

## 备份

```bash
# 数据库备份
cp data/agentshield.db backup/agentshield_$(date +%Y%m%d).db

# 日志归档
tar -czf logs/archive_$(date +%Y%m%d).tar.gz logs/
```

## 升级流程

1. 拉取最新代码
2. 运行数据库迁移（如有）
3. 重启服务
4. 验证健康检查
