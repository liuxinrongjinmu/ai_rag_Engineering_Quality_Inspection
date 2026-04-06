"""
向量数据库模块
使用Milvus进行向量存储和检索
"""
from typing import List, Dict, Any, Optional
from loguru import logger
from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility
)
from pathlib import Path
import json


class VectorStore:
    """
    向量数据库封装类 - Milvus实现
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection_name: str = "engineering_qa",
        embedding_dim: int = 1536
    ):
        """
        初始化向量数据库
        
        :param host: Milvus服务地址
        :param port: Milvus服务端口
        :param collection_name: 集合名称
        :param embedding_dim: 向量维度
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        
        self.collection: Optional[Collection] = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化数据库连接
        
        :return: 是否成功初始化
        """
        try:
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            
            if utility.has_collection(self.collection_name):
                self.collection = Collection(self.collection_name)
            else:
                self.collection = self._create_collection()
            
            self.collection.load()
            self._initialized = True
            logger.info(f"Milvus连接成功: {self.host}:{self.port}, 集合: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Milvus连接失败: {e}")
            return False
    
    def _create_collection(self) -> Collection:
        """
        创建集合
        
        :return: Collection对象
        """
        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True, auto_id=False),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="doc_name", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="page", dtype=DataType.INT64),
            FieldSchema(name="section", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=32)
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="工程质检知识库向量存储"
        )
        
        collection = Collection(
            name=self.collection_name,
            schema=schema
        )
        
        index_params = {
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        collection.create_index(
            field_name="embedding",
            index_params=index_params
        )
        
        logger.info(f"创建Milvus集合: {self.collection_name}")
        return collection
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        :return: 是否已初始化
        """
        return self._initialized and self.collection is not None
    
    def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        添加切片到向量数据库
        
        :param chunks: 切片列表（需包含embedding）
        :param batch_size: 批次大小
        :return: 成功添加的数量
        """
        if not self.is_initialized():
            logger.warning("向量数据库未初始化")
            return 0
        
        added_count = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            chunk_ids = []
            embeddings = []
            contents = []
            doc_ids = []
            doc_names = []
            pages = []
            sections = []
            source_types = []
            
            for chunk in batch:
                if "embedding" not in chunk:
                    continue
                
                chunk_ids.append(chunk["chunk_id"])
                embeddings.append(chunk["embedding"])
                
                content_val = chunk.get("content", "") or ""
                contents.append(content_val[:65535] if len(content_val) > 65535 else content_val)
                
                doc_ids.append(chunk.get("doc_id", "") or "")
                
                doc_name_val = chunk.get("doc_name", "") or ""
                doc_names.append(doc_name_val[:512] if len(doc_name_val) > 512 else doc_name_val)
                
                page_val = chunk.get("page")
                pages.append(page_val if page_val else 0)
                
                section_val = chunk.get("section", "") or ""
                sections.append(section_val[:256] if len(section_val) > 256 else section_val)
                
                source_types.append(chunk.get("source_type", "local") or "local")
            
            if chunk_ids:
                try:
                    self.collection.insert([
                        chunk_ids,
                        embeddings,
                        contents,
                        doc_ids,
                        doc_names,
                        pages,
                        sections,
                        source_types
                    ])
                    added_count += len(chunk_ids)
                except Exception as e:
                    logger.error(f"添加切片失败: {e}")
        
        self.collection.flush()
        logger.info(f"添加切片完成: {added_count}个")
        return added_count
    
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        向量检索
        
        :param query_embedding: 查询向量
        :param top_k: 返回数量
        :param where: 元数据过滤条件（暂不支持）
        :return: 检索结果
        """
        if not self.is_initialized():
            logger.warning("向量数据库未初始化")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        
        try:
            search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
            
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "doc_id", "doc_name", "page", "section", "source_type"]
            )
            
            ids = []
            documents = []
            metadatas = []
            distances = []
            
            for hits in results:
                for hit in hits:
                    ids.append(hit.id)
                    distances.append(1 - hit.distance)
                    
                    entity = hit.entity
                    documents.append(entity.get("content", ""))
                    metadatas.append({
                        "doc_id": entity.get("doc_id", ""),
                        "doc_name": entity.get("doc_name", ""),
                        "page": entity.get("page", 0),
                        "section": entity.get("section", ""),
                        "source_type": entity.get("source_type", "local")
                    })
            
            return {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "distances": distances
            }
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
    
    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取切片
        
        :param chunk_id: 切片ID
        :return: 切片数据
        """
        if not self.is_initialized():
            return None
        
        try:
            results = self.collection.query(
                expr=f'chunk_id == "{chunk_id}"',
                output_fields=["content", "doc_id", "doc_name", "page", "section", "source_type", "embedding"]
            )
            
            if results:
                result = results[0]
                return {
                    "chunk_id": chunk_id,
                    "content": result.get("content", ""),
                    "metadata": {
                        "doc_id": result.get("doc_id", ""),
                        "doc_name": result.get("doc_name", ""),
                        "page": result.get("page", 0),
                        "section": result.get("section", ""),
                        "source_type": result.get("source_type", "local")
                    },
                    "embedding": result.get("embedding")
                }
            return None
        except Exception as e:
            logger.error(f"获取切片失败: {e}")
            return None
    
    def delete_by_doc_id(self, doc_id: str) -> bool:
        """
        根据文档ID删除切片
        
        :param doc_id: 文档ID
        :return: 是否成功
        """
        if not self.is_initialized():
            return False
        
        try:
            self.collection.delete(expr=f'doc_id == "{doc_id}"')
            self.collection.flush()
            logger.info(f"删除文档切片: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"删除切片失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        :return: 统计信息
        """
        if not self.is_initialized():
            return {"total_chunks": 0, "total_docs": 0}
        
        try:
            self.collection.flush()
            stats = self.collection.num_entities
            
            results = self.collection.query(
                expr="chunk_id != ''",
                output_fields=["doc_id"]
            )
            
            doc_ids = set()
            for result in results:
                if result.get("doc_id"):
                    doc_ids.add(result.get("doc_id"))
            
            return {
                "total_chunks": stats,
                "total_docs": len(doc_ids),
                "doc_ids": list(doc_ids)
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"total_chunks": 0, "total_docs": 0}
    
    def reset(self) -> bool:
        """
        重置集合
        
        :return: 是否成功
        """
        if not self.is_initialized():
            return False
        
        try:
            utility.drop_collection(self.collection_name)
            self.collection = self._create_collection()
            self.collection.load()
            logger.info(f"集合已重置: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"重置集合失败: {e}")
            return False


_vectorstore_instance: Optional[VectorStore] = None


def get_vectorstore(
    host: str = "localhost",
    port: int = 19530,
    collection_name: str = "engineering_qa",
    embedding_dim: int = 1536
) -> VectorStore:
    """
    获取VectorStore单例
    
    :param host: Milvus服务地址
    :param port: Milvus服务端口
    :param collection_name: 集合名称
    :param embedding_dim: 向量维度
    :return: VectorStore实例
    """
    global _vectorstore_instance
    
    if _vectorstore_instance is None:
        _vectorstore_instance = VectorStore(host, port, collection_name, embedding_dim)
        _vectorstore_instance.initialize()
    
    return _vectorstore_instance
