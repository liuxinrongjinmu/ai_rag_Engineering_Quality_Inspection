"""
网络检索器
基于TavilySearchResults的网络搜索
"""
from typing import List, Optional, TYPE_CHECKING
from loguru import logger

from langchain_core.documents import Document

if TYPE_CHECKING:
    from langchain_community.tools import TavilySearchResults

_web_retriever_instance: Optional["TavilySearchResults"] = None


def get_web_retriever(max_results: int = 5) -> "TavilySearchResults":
    """
    获取Tavily网络检索器单例

    :param max_results: 最大结果数
    :return: TavilySearchResults实例
    """
    global _web_retriever_instance

    if _web_retriever_instance is None:
        from langchain_community.tools import TavilySearchResults
        from app.config import get_settings

        settings = get_settings()
        _web_retriever_instance = TavilySearchResults(
            max_results=max_results,
            tavily_api_key=settings.TAVILY_API_KEY,
        )
        logger.info(f"Tavily网络检索器初始化成功: max_results={max_results}")

    return _web_retriever_instance


def search_web(query: str, max_results: int = 5) -> List[Document]:
    """
    执行网络搜索

    :param query: 查询文本
    :param max_results: 最大结果数
    :return: Document列表
    """
    try:
        retriever = get_web_retriever(max_results)
        results = retriever.invoke(query)

        documents = []
        for result in results:
            if isinstance(result, dict):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")
            else:
                title = ""
                content = str(result)
                url = ""

            if not content.strip():
                continue

            doc = Document(
                page_content=content,
                metadata={
                    "source_type": "web",
                    "doc_name": title,
                    "url": url,
                },
            )
            documents.append(doc)

        logger.info(f"网络检索完成: 查询='{query[:30]}...', 结果数={len(documents)}")
        return documents

    except Exception as e:
        logger.error(f"网络检索失败: {e}")
        return []
