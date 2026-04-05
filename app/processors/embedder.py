"""
向量化模块
使用阿里云DashScope Embedding API进行文本向量化
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import numpy as np
import httpx
import os


class Embedder:
    """
    文本向量化器
    使用DashScope Embedding API
    """
    
    DASHSCOPE_EMBEDDING_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    EMBEDDING_DIM = 1536
    MAX_TEXT_LENGTH = 8000
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-v2"
    ):
        """
        初始化向量化器
        
        :param api_key: DashScope API Key
        :param model: Embedding模型名称
        """
        self.api_key = api_key
        self.model = model
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化
        
        :return: 是否成功初始化
        """
        if not self.api_key:
            logger.error("DashScope API Key未配置")
            return False
        
        self._initialized = True
        logger.info(f"Embedding API初始化成功, 模型: {self.model}, 向量维度: {self.EMBEDDING_DIM}")
        return True
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        :return: 是否已初始化
        """
        return self._initialized and bool(self.api_key)
    
    def get_embedding_dim(self) -> int:
        """
        获取向量维度
        
        :return: 向量维度
        """
        return self.EMBEDDING_DIM
    
    def _truncate_text(self, text: str, max_length: int = None) -> str:
        """
        截断文本到最大长度
        
        :param text: 原始文本
        :param max_length: 最大长度
        :return: 截断后的文本
        """
        max_length = max_length or self.MAX_TEXT_LENGTH
        if len(text) <= max_length:
            return text
        
        truncated = text[:max_length]
        last_period = truncated.rfind('。')
        last_newline = truncated.rfind('\n')
        cut_pos = max(last_period, last_newline)
        
        if cut_pos > max_length * 0.7:
            truncated = truncated[:cut_pos + 1]
        
        return truncated.strip()
    
    def _embed_request_api(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        调用DashScope Embedding API
        
        :param texts: 文本列表
        :return: 向量列表
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": {
                "texts": texts
            },
            "parameters": {
                "text_type": "document"
            }
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    self.DASHSCOPE_EMBEDDING_URL,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
            
            if "output" in data and "embeddings" in data["output"]:
                embeddings = [item["embedding"] for item in data["output"]["embeddings"]]
                return embeddings
            else:
                logger.error(f"Embedding API响应格式错误: {data}")
                return None
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding API请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"Embedding API调用失败: {e}")
            return None
    
    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """
        单文本向量化
        
        :param text: 输入文本
        :return: 向量
        """
        if not self.is_initialized():
            logger.warning("Embedder未初始化")
            return None
        
        if not text or not text.strip():
            return None
        
        try:
            truncated_text = self._truncate_text(text.strip())
            embeddings = self._embed_request_api([truncated_text])
            if embeddings and len(embeddings) > 0:
                return np.array(embeddings[0])
            return None
                
        except Exception as e:
            logger.error(f"文本向量化失败: {e}")
            return None
    
    def embed_texts(
        self,
        texts: List[str],
        batch_size: int = 25,
        show_progress: bool = True
    ) -> Optional[np.ndarray]:
        """
        批量文本向量化
        
        :param texts: 文本列表
        :param batch_size: 批次大小
        :param show_progress: 是否显示进度
        :return: 向量数组
        """
        if not self.is_initialized():
            logger.warning("Embedder未初始化")
            return None
        
        valid_texts = [self._truncate_text(t.strip()) for t in texts if t and t.strip()]
        if not valid_texts:
            return None
        
        all_embeddings = []
        total_batches = (len(valid_texts) + batch_size - 1) // batch_size
        
        for i in range(0, len(valid_texts), batch_size):
            batch = valid_texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            if show_progress:
                logger.info(f"正在向量化批次 {batch_num}/{total_batches}...")
            
            embeddings = self._embed_request_api(batch)
            if embeddings:
                all_embeddings.extend(embeddings)
            else:
                logger.warning(f"批次 {batch_num} 向量化失败")
                all_embeddings.extend([None] * len(batch))
        
        valid_embeddings = [e for e in all_embeddings if e is not None]
        if len(valid_embeddings) != len(valid_texts):
            logger.warning(f"部分文本向量化失败: {len(valid_embeddings)}/{len(valid_texts)}")
        
        logger.info(f"批量向量化完成: {len(valid_embeddings)}条文本")
        return np.array(valid_embeddings) if valid_embeddings else None
    
    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 25
    ) -> List[Dict[str, Any]]:
        """
        切片向量化
        
        :param chunks: 切片列表
        :param batch_size: 批次大小
        :return: 带向量的切片列表
        """
        if not self.is_initialized():
            logger.warning("Embedder未初始化")
            return chunks
        
        texts = [chunk.get("content", "") for chunk in chunks]
        embeddings = self.embed_texts(texts, batch_size)
        
        if embeddings is None:
            logger.warning("向量化失败，返回原始切片")
            return chunks
        
        for i, chunk in enumerate(chunks):
            if i < len(embeddings):
                chunk["embedding"] = embeddings[i].tolist()
        
        logger.info(f"切片向量化完成: {len(chunks)}个切片")
        return chunks
    
    def similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        计算向量相似度（余弦相似度）
        
        :param embedding1: 向量1
        :param embedding2: 向量2
        :return: 相似度分数
        """
        if embedding1 is None or embedding2 is None:
            return 0.0
        
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )
        return float(similarity)


_embedder_instance: Optional[Embedder] = None


def get_embedder(api_key: Optional[str] = None) -> Embedder:
    """
    获取Embedder单例
    
    :param api_key: DashScope API Key
    :return: Embedder实例
    """
    global _embedder_instance
    
    if _embedder_instance is None:
        if api_key is None:
            from app.config import get_settings
            settings = get_settings()
            api_key = settings.DASHSCOPE_API_KEY
        
        _embedder_instance = Embedder(api_key=api_key)
        _embedder_instance.initialize()
    
    return _embedder_instance
