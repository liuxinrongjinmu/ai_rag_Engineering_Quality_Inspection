"""
Embeddings工厂模块
使用DashScopeEmbeddings创建Embedding实例，带自动重试和限流处理
"""
import time
from typing import Optional, List, TYPE_CHECKING, Any
from loguru import logger

from app.config import get_settings

if TYPE_CHECKING:
    from langchain_community.embeddings import DashScopeEmbeddings

_embeddings_instance: Optional["DashScopeEmbeddings"] = None


class RetryableEmbeddings:
    """
    带重试的 Embeddings 包装器
    在 API 限流或临时故障时自动重试，避免批量入库中断
    """

    def __init__(self, base_embeddings: "DashScopeEmbeddings", max_retries: int = 3, base_delay: float = 2.0):
        """
        初始化

        :param base_embeddings: 底层 Embeddings 实例
        :param max_retries: 最大重试次数
        :param base_delay: 基础重试间隔（秒），指数退避
        """
        self._base = base_embeddings
        self._max_retries = max_retries
        self._base_delay = base_delay

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        带重试的文档嵌入

        :param texts: 文本列表
        :return: 向量列表
        """
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._base.embed_documents(texts)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._base_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding调用失败(attempt {attempt+1}/{self._max_retries+1}): {e}, "
                        f"{delay:.0f}s后重试..."
                    )
                    time.sleep(delay)
        raise last_error

    def embed_query(self, text: str) -> List[float]:
        """
        带重试的查询嵌入

        :param text: 查询文本
        :return: 向量
        """
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._base.embed_query(text)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = self._base_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding查询失败(attempt {attempt+1}): {e}, {delay:.0f}s后重试..."
                    )
                    time.sleep(delay)
        raise last_error

    def __getattr__(self, name: str) -> Any:
        """代理其他属性到基础实例"""
        return getattr(self._base, name)


def get_embeddings() -> "RetryableEmbeddings":
    """
    获取带重试的 Embeddings 单例

    :return: RetryableEmbeddings 实例
    """
    global _embeddings_instance

    if _embeddings_instance is None:
        from langchain_community.embeddings import DashScopeEmbeddings

        settings = get_settings()
        base = DashScopeEmbeddings(
            model=settings.EMBEDDING_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
        )
        _embeddings_instance = RetryableEmbeddings(base, max_retries=3, base_delay=2.0)
        logger.info(f"DashScopeEmbeddings初始化成功: model={settings.EMBEDDING_MODEL} (带重试)")

    return _embeddings_instance
