"""
网络检索器
使用Tavily API进行网络搜索
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import httpx

from app.models.document import WebSearchResult


class WebRetriever:
    """
    网络检索器
    使用Tavily API
    """
    
    TAVILY_API_URL = "https://api.tavily.com/search"
    
    AUTHORITY_DOMAINS = [
        "mot.gov.cn",
        "mohurd.gov.cn",
        "std.samr.gov.cn",
        "openstd.samr.gov.cn",
        "cnki.net",
        "wanfangdata.com.cn"
    ]
    
    def __init__(
        self,
        api_key: str,
        max_results: int = 5,
        timeout: int = 30
    ):
        """
        初始化网络检索器
        
        :param api_key: Tavily API Key
        :param max_results: 最大结果数
        :param timeout: 超时时间
        """
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
    
    def search_sync(
        self,
        query: str,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[WebSearchResult]:
        """
        同步网络搜索
        
        :param query: 查询文本
        :param include_domains: 包含的域名
        :param exclude_domains: 排除的域名
        :return: 搜索结果列表
        """
        if not self.api_key:
            logger.warning("Tavily API Key未配置")
            return []
        
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": self.max_results,
            "include_answer": True,
            "include_raw_content": False
        }
        
        if include_domains:
            payload["include_domains"] = include_domains
        else:
            payload["include_domains"] = self.AUTHORITY_DOMAINS
        
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.TAVILY_API_URL,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
            
            results = []
            
            if "results" in data:
                for item in data["results"]:
                    results.append(WebSearchResult(
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        url=item.get("url", ""),
                        score=item.get("score")
                    ))
            
            logger.info(f"网络检索完成: 查询='{query[:30]}...', 结果数={len(results)}")
            return results
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily API请求失败: {e}")
            return []
        except Exception as e:
            logger.error(f"网络检索失败: {e}")
            return []
    
    def is_authority_source(self, url: str) -> bool:
        """
        检查是否为权威来源
        
        :param url: URL
        :return: 是否权威
        """
        for domain in self.AUTHORITY_DOMAINS:
            if domain in url:
                return True
        return False


_web_retriever_instance: Optional[WebRetriever] = None


def get_web_retriever(api_key: str, max_results: int = 5) -> WebRetriever:
    """
    获取WebRetriever单例
    
    :param api_key: Tavily API Key
    :param max_results: 最大结果数
    :return: WebRetriever实例
    """
    global _web_retriever_instance
    
    if _web_retriever_instance is None:
        _web_retriever_instance = WebRetriever(api_key, max_results)
    
    return _web_retriever_instance
