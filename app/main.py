"""
FastAPI应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.utils.logger import setup_logger
from app.api.routes import query, source, health

settings = get_settings()

setup_logger(debug=settings.DEBUG)

app = FastAPI(
    title="工程质检RAG系统",
    description="公路工程质量检测智能问答系统API（基于LangChain）",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router, prefix="/api/v1")
app.include_router(source.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """
    应用启动事件
    """
    logger.info("工程质检RAG系统启动中...")

    try:
        from app.infrastructure.vectorstore import get_vectorstore
        vectorstore = get_vectorstore()
        collection = vectorstore._collection
        count = collection.count()
        logger.info(f"向量数据库状态: {count}个切片")
    except Exception as e:
        logger.warning(f"向量数据库初始化警告: {e}")

    try:
        from app.retrievers.bm25_retriever import load_bm25_retriever
        from pathlib import Path
        bm25_path = Path(settings.BM25_INDEX_PATH)
        if bm25_path.exists():
            load_bm25_retriever(str(bm25_path))
    except Exception as e:
        logger.warning(f"BM25索引加载警告: {e}")

    logger.info("工程质检RAG系统启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭事件
    """
    logger.info("工程质检RAG系统关闭")


@app.get("/", tags=["根路径"])
async def root():
    """
    根路径
    """
    return {
        "name": "工程质检RAG系统",
        "version": "2.0.0",
        "framework": "LangChain",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
