"""
Embeddings工厂模块
使用DashScopeEmbeddings创建Embedding实例
"""
from typing import Optional
from loguru import logger

from app.config import get_settings


_embeddings_instance: Optional[object] = None


def get_embeddings() -> object:
    """
    获取DashScopeEmbeddings单例

    :return: DashScopeEmbeddings实例
    """
    global _embeddings_instance

    if _embeddings_instance is None:
        from langchain_community.embeddings import DashScopeEmbeddings

        settings = get_settings()
        _embeddings_instance = DashScopeEmbeddings(
            model=settings.EMBEDDING_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
        )
        logger.info(f"DashScopeEmbeddings初始化成功: model={settings.EMBEDDING_MODEL}")

    return _embeddings_instance
