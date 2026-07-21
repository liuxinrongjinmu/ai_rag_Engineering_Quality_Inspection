"""
健康检查接口
"""
from fastapi import APIRouter
from loguru import logger

from app.models.response import HealthResponse

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="健康检查接口",
    description="检查系统各组件状态"
)
async def health_check():
    """
    健康检查接口

    返回系统各组件的健康状态和统计信息
    """
    components = {
        "vectordb": "unknown",
        "llm": "unknown",
        "embedder": "unknown"
    }

    stats = {
        "total_chunks": 0,
        "total_docs": 0
    }

    try:
        from app.infrastructure.vectorstore import get_vectorstore
        vectorstore = get_vectorstore()
        collection = vectorstore._collection
        count = collection.count()

        metadatas = collection.get(include=["metadatas"])["metadatas"]
        doc_ids = set()
        for m in (metadatas or []):
            if m.get("doc_id"):
                doc_ids.add(m["doc_id"])

        components["vectordb"] = "ok"
        stats = {
            "total_chunks": count,
            "total_docs": len(doc_ids),
        }
    except Exception as e:
        logger.warning(f"向量数据库检查失败: {e}")
        components["vectordb"] = "error"

    try:
        from app.infrastructure.embeddings import get_embeddings
        embeddings = get_embeddings()
        if embeddings:
            components["embedder"] = "ok"
        else:
            components["embedder"] = "error"
    except Exception as e:
        logger.warning(f"Embedder检查失败: {e}")
        components["embedder"] = "error"

    try:
        from app.config import get_settings
        settings = get_settings()
        if settings.DASHSCOPE_API_KEY:
            components["llm"] = "ok"
        else:
            components["llm"] = "error"
    except Exception as e:
        logger.warning(f"LLM检查失败: {e}")
        components["llm"] = "error"

    all_ok = all(v == "ok" for v in components.values())
    overall_status = "healthy" if all_ok else "degraded"

    return HealthResponse(
        status=overall_status,
        components=components,
        stats=stats
    )
