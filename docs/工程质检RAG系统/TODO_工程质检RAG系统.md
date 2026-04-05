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

### 3. 数据入库

将PDF和Excel文件放入项目根目录或 `data/raw/` 目录，然后执行：

```bash
python scripts/ingest.py
```

### 4. 启动服务

```bash
python -m app.main
```

访问 http://localhost:8000/docs 查看API文档

---

## 二、待优化事项

### 性能优化
- [ ] 添加Redis缓存层，缓存热门查询结果
- [ ] 实现流式输出，提升用户体验
- [ ] 添加批量查询接口

### 功能增强
- [ ] 添加查询历史记录
- [ ] 支持多轮对话
- [ ] 添加文档上传接口
- [ ] 支持更多文档格式（Word、PPT等）

### 工程化
- [ ] 添加Docker部署配置
- [ ] 添加单元测试覆盖
- [ ] 添加CI/CD配置
- [ ] 添加监控告警

---

## 三、已知问题

1. **网络检索依赖Tavily API**：如果API不可用，会降级到仅本地检索
2. **PDF表格提取可能不完整**：部分复杂表格格式可能无法完美识别
3. **Embedding API调用有成本**：大量数据入库时会产生API调用费用

---

## 四、快速验证步骤

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置API Key
# 编辑 .env 文件

# 3. 数据入库
python scripts/ingest.py

# 4. 启动服务
python -m app.main

# 5. 测试接口
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "土方路基压实度检测频率是多少？"}'
```

---

**创建时间**：2026-04-05
