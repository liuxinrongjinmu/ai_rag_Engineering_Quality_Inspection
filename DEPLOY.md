# 工程质检RAG系统 — 部署运维手册

> 版本 v2.3.0 | 适用于运维人员快速部署和维护

---

## 1. 系统架构

```
用户浏览器 → Nginx(:80) → rag-app(:5002) → ChromaDB + 通义千问API
```

| 组件 | 端口 | 说明 |
|------|------|------|
| Nginx | 80 | 前端静态文件 + API反向代理 |
| rag-app | 5002 | FastAPI + gunicorn 4 workers |
| ChromaDB | 本地文件 | `./data/vectordb/chroma/` |
| BM25 索引 | 本地文件 | `./data/vectordb/bm25_index.pkl` |

---

## 2. 环境要求

| 依赖 | 最低版本 |
|------|----------|
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| 磁盘空间 | ≥ 2GB（向量数据 + 前端产物） |
| 内存 | ≥ 4GB（4 workers 运行） |

---

## 3. 快速部署（3 步）

### 步骤 1：配置 API Key

```bash
cp .env.example .env
vim .env
```

修改两行：
```ini
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx    # 必填，通义千问API密钥
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx     # 可选，网络检索用
```

### 步骤 2：构建前端（如已有 dist/ 可跳过）

```bash
cd frontend && npm install && npm run build && cd ..
```

### 步骤 3：启动服务

```bash
docker-compose up -d
```

### 验证

```bash
# 健康检查
curl http://localhost:5002/api/v1/health

# 预期返回：
# {"status":"healthy","components":{"vectordb":"ok","llm":"ok","embedder":"ok"},...}

# 前端页面
open http://localhost
```

---

## 4. 首次数据入库

部署完成后需将知识文档入库：

```bash
# 将 MD/XLS/XLSX/PDF 文件放入 data/processed/
cp your_docs/*.md data/processed/

# 执行入库（容器内已配置启动自动执行，也可手动触发）
docker exec rag-app python scripts/ingest.py
```

或通过管理后台 Web 页面上传文档。

---

## 5. 常用运维命令

### 服务管理

```bash
docker-compose up -d          # 启动
docker-compose down           # 停止
docker-compose restart        # 重启
docker-compose logs -f        # 实时日志
docker-compose logs rag-app   # 仅后端日志
docker-compose logs nginx     # 仅 Nginx 日志
```

### 重建知识库

```bash
# 1. 更换 data/processed/ 下的文档
# 2. 重建（会自动清空旧数据后重新入库）
docker exec rag-app python scripts/ingest.py

# 3. 清空查询缓存（避免返回旧答案）
docker exec rag-app python -c "
from app.utils.cache import get_query_cache
get_query_cache().clear()
print('缓存已清空')
"
```

### 查看状态

```bash
# 容器状态
docker-compose ps

# 后端健康
curl http://localhost:5002/api/v1/health

# 知识库统计
curl http://localhost:5002/api/v1/admin/stats
```

---

## 6. 配置参考

完整环境变量见 [.env.example](file:///Users/jinmu/Desktop/金木/my-project/工程质检RAG系统/.env.example)，关键参数：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | `qwen-plus` | 推荐，精度高幻觉少 |
| `VECTOR_WEIGHT` | 0.5 | 向量检索权重 |
| `BM25_WEIGHT` | 0.5 | 关键词检索权重 |
| `USE_SEMANTIC_RERANK` | false | 语义重排序（API需支持gte-rerank） |
| `DEBUG` | true | 调试模式，生产建议 false |

修改配置后需重启：`docker-compose restart rag-app`

---

## 7. 数据备份与恢复

### 备份

```bash
# 备份整个数据目录
tar -czf rag-backup-$(date +%Y%m%d).tar.gz data/
```

### 恢复

```bash
tar -xzf rag-backup-20260721.tar.gz
docker-compose restart rag-app
```

---

## 8. 故障排查

| 现象 | 检查步骤 |
|------|----------|
| 页面打不开 | `docker-compose ps` 确认容器都在 running |
| 问答无回复 | `docker logs rag-app --tail 50` 查看错误日志 |
| 回答不准确 | 执行知识库重建 + 清空缓存 |
| ChromaDB 报错 | 删除 `data/vectordb/chroma/` 后重新入库 |
| 端口冲突 | 修改 `docker-compose.yml` 中的端口映射 |
| 容器启动失败 | 检查 `.env` 中 `DASHSCOPE_API_KEY` 是否有效 |

### 日志位置

- 容器日志：`docker-compose logs`
- 应用日志：容器内 `/app/logs/`
- Nginx 日志：`docker logs rag-nginx`

---

## 9. 升级流程

```bash
# 1. 备份数据
tar -czf rag-backup-$(date +%Y%m%d).tar.gz data/

# 2. 拉取新代码
git pull

# 3. 重建前端
cd frontend && npm run build && cd ..

# 4. 重建镜像并重启
docker-compose down
docker-compose build --no-cache rag-app
docker-compose up -d

# 5. 如文档有变更，重建知识库
docker exec rag-app python scripts/ingest.py
```
