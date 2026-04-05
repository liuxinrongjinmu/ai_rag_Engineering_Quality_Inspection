"""
BM25关键词检索模块
实现基于关键词的检索
"""
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import pickle
import os
import re
import jieba

from rank_bm25 import BM25Okapi
from app.models.document import Chunk, SearchResult, SourceType


class BM25Retriever:
    """
    BM25关键词检索器
    """
    
    def __init__(self):
        """
        初始化BM25检索器
        """
        self._bm25 = None
        self._chunks: List[Chunk] = []
        self._corpus: List[List[str]] = []
        self._initialized = False
        
        # 初始化jieba分词
        jieba.initialize()
        
        # 加载专业词典
        self._load_domain_dict()
    
    def _load_domain_dict(self):
        """
        加载专业领域词典
        """
        domain_words = [
            "压实度", "含水率", "抗压强度", "抗折强度", "坍落度",
            "粉煤灰", "钢绞线", "锚具", "集料", "沥青",
            "路基", "路面", "桥梁", "隧道", "桩基",
            "检测频率", "取样方法", "检测项目",
            "块体密度", "击实试验", "CBR试验", "液限塑限",
            "JTG", "GB", "规范", "标准", "规程"
        ]
        
        for word in domain_words:
            jieba.add_word(word)
    
    def initialize(self, chunks: List[Chunk]) -> bool:
        """
        初始化BM25索引
        
        :param chunks: 切片列表
        :return: 是否成功
        """
        if not chunks:
            logger.warning("切片列表为空，无法初始化BM25")
            return False
        
        self._chunks = chunks
        self._corpus = []
        
        for chunk in chunks:
            tokens = self._tokenize(chunk.content)
            self._corpus.append(tokens)
        
        self._bm25 = BM25Okapi(self._corpus)
        self._initialized = True
        
        logger.info(f"BM25索引初始化完成: {len(chunks)}个切片")
        return True
    
    def _tokenize(self, text: str) -> List[str]:
        """
        分词
        
        :param text: 文本
        :return: 词列表
        """
        # 使用jieba分词
        tokens = list(jieba.cut(text))
        
        # 过滤停用词和标点
        stop_words = set(['的', '了', '和', '是', '在', '有', '对', '为', '与', '及'])
        tokens = [t.strip() for t in tokens if t.strip() and t.strip() not in stop_words]
        tokens = [t for t in tokens if len(t) > 1 or re.match(r'[A-Za-z0-9]', t)]
        
        return tokens
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        :return: 是否已初始化
        """
        return self._initialized and self._bm25 is not None
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        检索相关内容
        
        :param query: 查询文本
        :param top_k: 返回结果数
        :return: 检索结果列表
        """
        if not self.is_initialized():
            logger.warning("BM25检索器未初始化")
            return []
        
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        scores = self._bm25.get_scores(query_tokens)
        
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk = self._chunks[idx]
                # 归一化BM25分数到0-1范围
                normalized_score = min(scores[idx] / 20, 1.0)
                
                results.append(SearchResult(
                    chunk=chunk,
                    score=normalized_score
                ))
        
        logger.info(f"BM25检索完成: 查询='{query[:30]}...', 结果数={len(results)}, 最高分={max([r.score for r in results]) if results else 0:.3f}")
        return results
    
    def save(self, path: str):
        """
        保存BM25索引
        
        :param path: 保存路径
        """
        if not self.is_initialized():
            return
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        data = {
            'chunks': [(c.chunk_id, c.doc_id, c.doc_name, c.content, c.page, c.section, c.source_type, c.metadata) for c in self._chunks],
            'corpus': self._corpus
        }
        
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        
        logger.info(f"BM25索引已保存: {path}")
    
    def load(self, path: str) -> bool:
        """
        加载BM25索引
        
        :param path: 索引路径
        :return: 是否成功
        """
        if not os.path.exists(path):
            logger.warning(f"BM25索引文件不存在: {path}")
            return False
        
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self._chunks = []
            for item in data['chunks']:
                chunk = Chunk(
                    chunk_id=item[0],
                    doc_id=item[1],
                    doc_name=item[2],
                    content=item[3],
                    page=item[4],
                    section=item[5],
                    source_type=item[6],
                    metadata=item[7]
                )
                self._chunks.append(chunk)
            
            self._corpus = data['corpus']
            self._bm25 = BM25Okapi(self._corpus)
            self._initialized = True
            
            logger.info(f"BM25索引已加载: {len(self._chunks)}个切片")
            return True
            
        except Exception as e:
            logger.error(f"BM25索引加载失败: {e}")
            return False


_bm25_retriever_instance: Optional[BM25Retriever] = None


def get_bm25_retriever() -> BM25Retriever:
    """
    获取BM25Retriever单例
    
    :return: BM25Retriever实例
    """
    global _bm25_retriever_instance
    
    if _bm25_retriever_instance is None:
        _bm25_retriever_instance = BM25Retriever()
    
    return _bm25_retriever_instance
