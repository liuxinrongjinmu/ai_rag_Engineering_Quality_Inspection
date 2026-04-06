"""
配置管理模块
使用pydantic-settings管理环境变量配置
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """
    应用配置类
    所有配置项从环境变量读取，支持.env文件
    """
    
    DASHSCOPE_API_KEY: str = Field(..., description="通义千问API Key（同时用于LLM和Embedding）")
    
    TAVILY_API_KEY: str = Field(..., description="Tavily搜索API Key")
    
    # ChromaDB配置
    CHROMA_PERSIST_DIR: str = Field(
        default="./data/vectordb/chroma",
        description="ChromaDB数据持久化目录"
    )
    
    CHROMA_COLLECTION_NAME: str = Field(
        default="engineering_qa",
        description="ChromaDB集合名称"
    )
    
    # 向量维度（DashScope text-embedding-v2 输出1536维）
    EMBEDDING_DIM: int = Field(
        default=1536,
        description="向量维度"
    )
    
    # BM25索引存储路径
    BM25_INDEX_PATH: str = Field(
        default="./data/vectordb/bm25_index.pkl",
        description="BM25索引存储路径"
    )
    
    CHUNK_SIZE: int = Field(default=1000, description="文本切片大小")
    CHUNK_OVERLAP: int = Field(default=200, description="切片重叠字符数")
    TOP_K_RESULTS: int = Field(default=5, description="检索返回结果数")
    
    API_HOST: str = Field(default="0.0.0.0", description="API服务主机")
    API_PORT: int = Field(default=5002, description="API服务端口")
    DEBUG: bool = Field(default=True, description="调试模式")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    使用lru_cache确保配置只加载一次
    """
    return Settings()
