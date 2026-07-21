"""
VectorStore工厂模块
使用Chroma创建向量数据库实例
"""
from typing import Optional, TYPE_CHECKING
from loguru import logger
from pathlib import Path

from app.config import get_settings

if TYPE_CHECKING:
    from langchain_chroma import Chroma

_vectorstore_instance: Optional["Chroma"] = None


def get_vectorstore() -> "Chroma":
    """
    获取Chroma VectorStore单例

    :return: Chroma VectorStore实例
    """
    global _vectorstore_instance

    if _vectorstore_instance is None:
        from langchain_chroma import Chroma
        from app.infrastructure.embeddings import get_embeddings

        settings = get_settings()
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        embeddings = get_embeddings()

        _vectorstore_instance = Chroma(
            collection_name=settings.CHROMA_COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Chroma VectorStore初始化成功: {settings.CHROMA_PERSIST_DIR} (距离度量: cosine)")

    return _vectorstore_instance
