# TODO - 前端界面与后端优化

## 一、已完成的改进

- [x] Vue 3 前端问答界面（SSE流式 + 来源追溯 + Markdown渲染）
- [x] Vue 3 管理界面（文档上传/列表/删除 + 系统状态 + 知识库重建）
- [x] 后端文档管理API（5个接口）
- [x] pytest 单元测试（38个用例，5个核心模块，全部通过）
- [x] 检索并行化（asyncio.gather 并行本地+网络检索）
- [x] Redis缓存（可选降级，不配置则用内存缓存）
- [x] 完整类型注解（0个 `-> object`）
- [x] README文档更新

---

## 二、待配置事项

### 1. 安装前端依赖

```bash
cd frontend
npm install
```

### 2. 安装后端测试依赖

```bash
pip install redis pytest pytest-asyncio pytest-cov
```

### 3. Redis部署（可选）

```bash
# 方式1：Docker启动Redis
docker run -d --name rag-redis -p 6379:6379 redis:7-alpine

# 方式2：docker-compose（含Redis）
docker-compose --profile with-redis up -d

# 方式3：brew安装
brew install redis && brew services start redis
```

配置 `.env`：
```env
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL=3600
```

---

## 三、后续优化建议

### 高优先级

- [ ] **用户认证**：管理后台添加登录/鉴权功能（建议 JWT + 中间件）
- [ ] **多轮对话**：支持上下文记忆的对话模式
- [ ] **查询历史**：保存用户历史查询记录
- [ ] **CI/CD配置**：GitHub Actions / GitLab CI 自动化测试+部署

### 中优先级

- [ ] **E2E测试**：Playwright 或 Cypress 端到端测试
- [ ] **前端错误监控**：Sentry 集成
- [ ] **API限流**：防止滥用（推荐 slowapi）
- [ ] **文档上传进度条**：WebSocket 实时推送入库进度
- [ ] **批量文档导入**：支持一次上传多个文件

### 低优先级

- [ ] **PDF自动转换**：集成 OCR/解析，省去手动 MD 转换
- [ ] **国际化 i18n**：中英文切换
- [ ] **暗色主题**：白天/夜间模式切换
- [ ] **前端代码分割**：优化 bundle 体积（当前1.3MB）
- [ ] **Milvus/Qdrant迁移**：高并发场景下评估分布式向量数据库

---

## 四、已知限制

1. **PDF需手动转MD**：系统不支持直接处理PDF，需用工具转换后放入 `data/processed/`
2. **BM25索引重建**：删除文档后需全量重建BM25索引（影响性能）
3. **网络检索依赖Tavily API**：API不可用时降级为仅本地检索
4. **前端无用户状态**：刷新页面后对话历史丢失

---

## 五、快速启动

```bash
# 1. 后端
pip install -r requirements.txt
cp .env.example .env  # 编辑填入API Key
python scripts/ingest.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 5002

# 2. 前端（新终端）
cd frontend
npm install
npm run dev

# 3. 访问
# 问答界面: http://localhost:3000
# 管理后台: http://localhost:3000/admin
# API文档:  http://localhost:5002/docs

# 4. 测试
.venv-mac/bin/python -m pytest tests/ -v
```

---

**创建时间**：2026-07-21  
**版本**：v2.2.0
