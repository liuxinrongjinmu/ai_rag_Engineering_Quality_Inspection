"""
Chroma向量检索器
基于langchain-chroma的向量检索
"""
from typing import List, Optional, TYPE_CHECKING
from loguru import logger

from langchain_core.documents import Document

if TYPE_CHECKING:
    from langchain_core.retrievers import BaseRetriever

_chroma_retriever_instance: Optional["BaseRetriever"] = None


def get_chroma_retriever(top_k: int = 5) -> "BaseRetriever":
    """
    获取Chroma检索器

    :param top_k: 返回结果数
    :return: VectorStoreRetriever实例
    """
    global _chroma_retriever_instance

    from app.infrastructure.vectorstore import get_vectorstore

    vectorstore = get_vectorstore()
    if _chroma_retriever_instance is None:
        _chroma_retriever_instance = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": top_k},
        )
        logger.info(f"Chroma检索器初始化成功: top_k={top_k}")
    else:
        # 确保每次调用都使用传入的 top_k（缓存实例不更新会导致召回数量固定）
        _chroma_retriever_instance.search_kwargs["k"] = top_k

    return _chroma_retriever_instance
