"""
重排序器
对检索结果进行重排序和合并
"""
from typing import List, Dict, Any, Optional
from loguru import logger

from app.models.document import SearchResult, WebSearchResult, Chunk, SourceType


class Reranker:
    """
    检索结果重排序器
    """
    
    LOCAL_WEIGHT = 0.7
    WEB_WEIGHT = 0.3
    
    def __init__(
        self,
        local_weight: float = 0.7,
        web_weight: float = 0.3
    ):
        """
        初始化重排序器
        
        :param local_weight: 本地结果权重
        :param web_weight: 网络结果权重
        """
        self.local_weight = local_weight
        self.web_weight = web_weight
    
    def rerank(
        self,
        local_results: List[SearchResult],
        web_results: List[WebSearchResult],
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        重排序并合并结果
        
        :param local_results: 本地检索结果
        :param web_results: 网络检索结果
        :param top_k: 返回数量
        :return: 重排序后的结果
        """
        all_results = []
        
        for result in local_results:
            weighted_score = result.score * self.local_weight
            all_results.append(SearchResult(
                chunk=result.chunk,
                score=weighted_score,
                source_url=None
            ))
        
        for web_result in web_results:
            chunk = Chunk(
                chunk_id=f"web_{hash(web_result.url) % 1000000:06d}",
                doc_id="web",
                doc_name=web_result.title,
                content=web_result.content,
                page=None,
                section=None,
                source_type=SourceType.WEB,
                metadata={"url": web_result.url}
            )
            
            base_score = web_result.score if web_result.score else 0.5
            weighted_score = base_score * self.web_weight
            
            all_results.append(SearchResult(
                chunk=chunk,
                score=weighted_score,
                source_url=web_result.url
            ))
        
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        final_results = all_results[:top_k]
        
        logger.info(f"重排序完成: 本地{len(local_results)}条, 网络{len(web_results)}条, 最终{len(final_results)}条")
        
        return final_results
    
    def merge_and_deduplicate(
        self,
        results_list: List[List[SearchResult]]
    ) -> List[SearchResult]:
        """
        合并并去重
        
        :param results_list: 结果列表
        :return: 合并后的结果
        """
        seen = set()
        merged = []
        
        for results in results_list:
            for result in results:
                key = result.chunk.chunk_id
                if key not in seen:
                    seen.add(key)
                    merged.append(result)
        
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged


_reranker_instance: Optional[Reranker] = None


def get_reranker(
    local_weight: float = 0.7,
    web_weight: float = 0.3
) -> Reranker:
    """
    获取Reranker单例
    
    :param local_weight: 本地结果权重
    :param web_weight: 网络结果权重
    :return: Reranker实例
    """
    global _reranker_instance
    
    if _reranker_instance is None:
        _reranker_instance = Reranker(local_weight, web_weight)
    
    return _reranker_instance
