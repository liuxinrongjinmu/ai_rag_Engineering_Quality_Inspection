"""
混合检索器
整合向量检索、BM25检索和查询重写
"""
from typing import List, Dict, Any, Optional
from loguru import logger
from collections import defaultdict

from app.config import get_settings
from app.retrievers.local_retriever import LocalRetriever, get_local_retriever
from app.retrievers.bm25_retriever import BM25Retriever, get_bm25_retriever
from app.retrievers.web_retriever import WebRetriever, get_web_retriever
from app.retrievers.reranker import Reranker, get_reranker
from app.processors.query_rewriter import QueryRewriter, get_query_rewriter
from app.models.document import SearchResult, WebSearchResult, Chunk, SourceType


class HybridRetriever:
    """
    混合检索器
    整合向量检索、BM25检索和查询重写
    """
    
    LOCAL_THRESHOLD = 0.5
    
    # 混合检索权重
    VECTOR_WEIGHT = 0.6
    BM25_WEIGHT = 0.4
    
    def __init__(
        self,
        vector_retriever: Optional[LocalRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        web_retriever: Optional[WebRetriever] = None,
        query_rewriter: Optional[QueryRewriter] = None,
        reranker: Optional[Reranker] = None,
        top_k: int = 5,
        use_web_search: bool = True
    ):
        """
        初始化混合检索器
        
        :param vector_retriever: 向量检索器
        :param bm25_retriever: BM25检索器
        :param web_retriever: 网络检索器
        :param query_rewriter: 查询重写器
        :param reranker: 重排序器
        :param top_k: 返回结果数
        :param use_web_search: 是否启用网络检索
        """
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.web_retriever = web_retriever
        self.query_rewriter = query_rewriter
        self.reranker = reranker
        self.top_k = top_k
        self.use_web_search = use_web_search
    
    def initialize(self) -> bool:
        """
        初始化组件
        
        :return: 是否成功
        """
        settings = get_settings()
        
        if self.vector_retriever is None:
            self.vector_retriever = get_local_retriever(top_k=self.top_k * 2)
        
        if self.bm25_retriever is None:
            self.bm25_retriever = get_bm25_retriever()
        
        if self.query_rewriter is None:
            self.query_rewriter = get_query_rewriter(api_key=settings.DASHSCOPE_API_KEY)
        
        if self.web_retriever is None and self.use_web_search:
            self.web_retriever = get_web_retriever(
                api_key=settings.TAVILY_API_KEY,
                max_results=self.top_k
            )
        
        if self.reranker is None:
            self.reranker = get_reranker()
        
        return True
    
    def retrieve(
        self,
        query: str,
        use_web_search: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        执行混合检索
        
        :param query: 查询文本
        :param use_web_search: 是否使用网络检索
        :return: 检索结果
        """
        self.initialize()
        
        use_web = use_web_search if use_web_search is not None else self.use_web_search
        
        # 1. 查询重写
        rewritten_query = self.query_rewriter.rewrite(query)
        queries = [query]
        if rewritten_query != query:
            queries.append(rewritten_query)
        
        # 2. 向量检索
        vector_results = []
        for q in queries:
            results = self.vector_retriever.retrieve(q, top_k=self.top_k * 2)
            vector_results.extend(results)
        
        # 3. BM25检索
        bm25_results = []
        if self.bm25_retriever.is_initialized():
            for q in queries:
                results = self.bm25_retriever.retrieve(q, top_k=self.top_k * 2)
                bm25_results.extend(results)
        
        # 4. 融合向量检索和BM25检索结果
        fused_results = self._fuse_results(vector_results, bm25_results)
        
        # 5. 判断是否需要网络检索
        web_results: List[WebSearchResult] = []
        used_web_search = False
        
        should_search_web = use_web and self._should_search_web(fused_results)
        
        if should_search_web:
            try:
                web_results = self.web_retriever.search_sync(query)
                used_web_search = len(web_results) > 0
            except Exception as e:
                logger.warning(f"网络检索失败: {e}")
        
        # 6. 重排序
        final_results = self.reranker.rerank(
            local_results=fused_results[:self.top_k],
            web_results=web_results,
            top_k=self.top_k
        )
        
        return {
            "results": final_results,
            "used_web_search": used_web_search,
            "local_count": len(fused_results),
            "web_count": len(web_results),
            "rewritten_query": rewritten_query if rewritten_query != query else None
        }
    
    def _fuse_results(
        self,
        vector_results: List[SearchResult],
        bm25_results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        融合向量检索和BM25检索结果
        
        :param vector_results: 向量检索结果
        :param bm25_results: BM25检索结果
        :return: 融合后的结果
        """
        # 按chunk_id聚合分数
        chunk_scores = defaultdict(lambda: {'vector': 0.0, 'bm25': 0.0, 'chunk': None})
        
        for result in vector_results:
            chunk_id = result.chunk.chunk_id
            chunk_scores[chunk_id]['vector'] = max(chunk_scores[chunk_id]['vector'], result.score)
            if chunk_scores[chunk_id]['chunk'] is None:
                chunk_scores[chunk_id]['chunk'] = result.chunk
        
        for result in bm25_results:
            chunk_id = result.chunk.chunk_id
            chunk_scores[chunk_id]['bm25'] = max(chunk_scores[chunk_id]['bm25'], result.score)
            if chunk_scores[chunk_id]['chunk'] is None:
                chunk_scores[chunk_id]['chunk'] = result.chunk
        
        # 计算融合分数
        fused_results = []
        for chunk_id, scores in chunk_scores.items():
            # 加权融合
            fused_score = (
                scores['vector'] * self.VECTOR_WEIGHT +
                scores['bm25'] * self.BM25_WEIGHT
            )
            
            # 如果两种检索都有结果，给予奖励
            if scores['vector'] > 0 and scores['bm25'] > 0:
                fused_score = min(fused_score * 1.2, 1.0)
            
            fused_results.append(SearchResult(
                chunk=scores['chunk'],
                score=fused_score
            ))
        
        # 按分数排序
        fused_results.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"结果融合完成: 向量{len(vector_results)}个 + BM25{len(bm25_results)}个 -> 融合{len(fused_results)}个")
        
        return fused_results
    
    def _should_search_web(self, local_results: List[SearchResult]) -> bool:
        """
        判断是否需要网络检索
        
        :param local_results: 本地检索结果
        :return: 是否需要网络检索
        """
        if not local_results:
            return True
        
        top_score = max(r.score for r in local_results)
        
        return top_score < self.LOCAL_THRESHOLD
    
    def initialize_bm25(self, chunks: List[Chunk]) -> bool:
        """
        初始化BM25索引
        
        :param chunks: 切片列表
        :return: 是否成功
        """
        return self.bm25_retriever.initialize(chunks)


_hybrid_retriever_instance: Optional[HybridRetriever] = None


def get_hybrid_retriever(
    top_k: int = 5,
    use_web_search: bool = True
) -> HybridRetriever:
    """
    获取HybridRetriever单例
    
    :param top_k: 返回结果数
    :param use_web_search: 是否启用网络检索
    :return: HybridRetriever实例
    """
    global _hybrid_retriever_instance
    
    if _hybrid_retriever_instance is None:
        _hybrid_retriever_instance = HybridRetriever(
            top_k=top_k,
            use_web_search=use_web_search
        )
    
    return _hybrid_retriever_instance
