# TODO - 工程质检RAG系统

## 一、必须完成的配置

### 1. API Key配置

编辑 `.env` 文件，填入以下API Key：

```env
# 通义千问API Key（必须，同时用于LLM和Embedding）
DASHSCOPE_API_KEY=your_actual_dashscope_api_key

# Tavily搜索API Key（必须，用于网络检索）
TAVILY_API_KEY=your_actual_tavily_api_key
```

**获取方式：**
- 通义千问/DashScope：https://dashscope.console.aliyun.com/
- Tavily：https://tavily.com/

**说明：**
- LLM和Embedding共用同一个DashScope API Key
- 无需本地部署模型，完全云端调用

### 2. 依赖安装

```bash
pip install -r requirements.txt
```

### 3. 启动Milvus

```bash
docker-compose up -d
```

等待Milvus完全启动（约30秒）。

### 4. 数据入库

将Markdown和Excel文件放入 `data/processed/` 目录，然后执行：

```bash
python scripts/ingest.py
```

**入库流程：**
1. 扫描 `data/processed/` 目录下的文件
2. 解析Markdown和Excel文件
3. 文本切片（1000字符/块）
4. 向量化并写入Milvus
5. 构建BM25索引

### 5. 启动服务

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 5001
```

访问 http://localhost:5001/docs 查看API文档

---

## 二、已完成优化事项

### 性能优化
- [x] 添加内存缓存层，缓存热门查询结果（命中时<100ms响应）
- [x] 实现流式输出（SSE），提升用户体验
- [x] 实现并行检索，向量检索和BM25同时执行

### 功能增强
- [x] 来源信息显示唯一文档名称
- [x] 支持网络检索来源URL显示
- [x] 向量数据库迁移到Milvus（分布式架构）

---

## 三、待优化事项

### 性能优化
- [ ] 添加Redis缓存层替代内存缓存（生产环境）
- [ ] 添加批量查询接口
- [ ] 优化大文档处理性能

### 功能增强
- [ ] 添加查询历史记录
- [ ] 支持多轮对话
- [ ] 添加文档上传接口
- [ ] 支持更多文档格式（Word、PPT等）
- [ ] 添加前端界面

### 工程化
- [ ] 添加单元测试覆盖
- [ ] 添加CI/CD配置
- [ ] 添加监控告警

---

## 四、已知问题

1. **网络检索依赖Tavily API**：如果API不可用，会降级到仅本地检索
2. **Markdown文件需要手动准备**：PDF需用户自行转换为Markdown格式
3. **Embedding API调用有成本**：大量数据入库时会产生API调用费用

---

## 五、快速验证步骤

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动Milvus
docker-compose up -d

# 3. 配置API Key
# 编辑 .env 文件

# 4. 数据入库
python scripts/ingest.py

# 5. 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 5001

# 6. 测试接口
python test_api.py
```

---

**创建时间**：2026-04-05
**更新时间**：2026-04-06
