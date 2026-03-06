# AGENTS.md

本文件为 AI Agent 提供项目指南。

## 项目概述

**Collège Saint-Louis RAG Chatbot** - 基于检索增强生成 (RAG) 的多语言文档问答系统，使用 ZhipuAI GLM 模型。

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15, React 18, TypeScript, Tailwind CSS |
| 后端 | Python, FastAPI, Milvus |
| LLM | ZhipuAI GLM-4.7 |
| 向量嵌入 | sentence-transformers (BAAI/bge-m3) |

## 项目结构

```
chatbot/
├── backend/              # Python RAG 后端
│   ├── src/             # 核心模块
│   ├── tests/           # pytest 测试
│   ├── data/            # 向量数据库和输入文档
│   ├── api_server.py    # FastAPI 服务 (端口 8086)
│   └── requirements.txt # Python 依赖
├── frontend/            # Next.js Web 界面
│   ├── app/            # Next.js App Router
│   ├── components/     # React 组件
│   ├── lib/            # 工具函数
│   └── package.json    # Node 依赖
├── data/               # 共享数据目录
├── .env.example        # 环境变量模板
├── start.sh            # 启动服务
└── stop.sh             # 停止服务
```

## 核心模块

### 后端模块 (backend/src/)

| 模块 | 功能 |
|------|------|
| `milvus_rag.py` | RAG 流程编排 (Milvus 版) |
| `milvus_store.py` | Milvus 向量存储接口 |
| `milvus_indexer.py` | Milvus 索引管理 |
| `hybrid_retriever.py` | BM25 + Milvus 混合检索 |
| `query_expander.py` | 查询扩展 |
| `query_classifier.py` | 查询分类 |
| `confidence_scorer.py` | 置信度评分 |
| `semantic_chunker.py` | 语义分块 |
| `translation_service.py` | 翻译服务 |
| `school_terms.py` | 学期日期处理 |
| `temporal_search.py` | 时间搜索增强 |
| `document_registry.py` | 文档追踪和版本管理 |
| `embedding.py` | BGE-M3 嵌入客户端 |
| `zhipuai_llm.py` | ZhipuAI GLM 客户端 |

### API 端点

- `POST /api/chat` - 问答接口
- `GET /api/admin/performance-metrics` - 性能指标
- `GET /api/admin/scrape-status` - 爬取状态
- `POST /api/admin/scrape-config` - 爬取配置
- `POST /api/upload-data` - 上传文档

## 开发规范

### 语言
- 注释和解释使用 **中文**
- 技术术语 (函数名、API 等) 保持原样

### 测试
- 修改 RAG 逻辑前先写测试
- 运行 `pytest backend/tests/` 验证后端
- 运行 `npm test` 验证前端

### 代码质量
- Python: 遵循 PEP 8，使用类型提示
- TypeScript: 严格模式，避免 `any` 类型
- 保持函数简洁，复杂函数添加文档字符串

## 常用命令

```bash
# 启动服务
./start.sh

# 停止服务
./stop.sh

# 后端测试
cd backend && pytest

# 前端测试
cd frontend && npm test

# CLI 查询
python3 run.py query --question "..."
```

## 配置

环境变量 (`.env`):

| 变量 | 描述 |
|------|------|
| `AI_API_KEY` | ZhipuAI API 密钥 (必需) |
| `AI_BASE_URL` | ZhipuAI API 地址 |
| `AI_MODEL` | GLM 模型 (默认: GLM-4.7) |
| `MILVUS_HOST` | Milvus 主机 (默认: localhost) |
| `MILVUS_PORT` | Milvus 端口 (默认: 19530) |
| `MILVUS_COLLECTION` | Milvus 集合名称 (默认: documents) |
| `TOP_K` | 检索数量 (默认: 10) |
| `API_PORT` | 后端 API 端口 (默认: 8086) |

## 故障排除

### Milvus 问题
- 服务连接失败 → 检查 Milvus 是否在运行（端口 19530）
- 集合未找到 → 运行索引重建命令
- 查询缓慢 → 检查 TOP_K 和 MILVUS_HOST 配置

### LLM 问题
- 限流 → 切换到 `glm-4-flash`
- API 错误 → 验证 API 密钥

### 前端问题
- 构建错误 → 删除 `frontend/.next` 重新构建
- API 连接失败 → 确保后端在 8000 端口运行
