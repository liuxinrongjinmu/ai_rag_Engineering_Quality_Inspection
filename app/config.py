"""
配置管理模块
使用pydantic-settings管理环境变量配置
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from functools import lru_cache


class Settings(BaseSettings):
    """
    应用配置类
    所有配置项从环境变量读取，支持.env文件
    """

    DASHSCOPE_API_KEY: str = Field(..., description="通义千问API Key（同时用于LLM和Embedding）")

    TAVILY_API_KEY: str = Field(..., description="Tavily搜索API Key")

    # LLM配置
    LLM_MODEL: str = Field(default="qwen-turbo", description="LLM模型名称")
    LLM_TEMPERATURE: float = Field(default=0.1, description="LLM生成温度")
    LLM_MAX_TOKENS: int = Field(default=1000, description="LLM最大生成token数")

    # Embedding配置
    EMBEDDING_MODEL: str = Field(default="text-embedding-v2", description="Embedding模型名称")
    EMBEDDING_DIM: int = Field(default=1536, description="向量维度")

    # ChromaDB配置
    CHROMA_PERSIST_DIR: str = Field(
        default="./data/vectordb/chroma",
        description="ChromaDB数据持久化目录"
    )

    CHROMA_COLLECTION_NAME: str = Field(
        default="engineering_qa",
        description="ChromaDB集合名称"
    )

    # BM25索引存储路径
    BM25_INDEX_PATH: str = Field(
        default="./data/vectordb/bm25_index.pkl",
        description="BM25索引存储路径"
    )

    # 切片配置
    CHUNK_SIZE: int = Field(default=1000, description="文本切片大小")
    CHUNK_OVERLAP: int = Field(default=200, description="切片重叠字符数")
    TOP_K_RESULTS: int = Field(default=5, description="检索返回结果数")

    # 混合检索权重
    VECTOR_WEIGHT: float = Field(default=0.6, description="向量检索权重")
    BM25_WEIGHT: float = Field(default=0.4, description="BM25检索权重")
    LOCAL_WEIGHT: float = Field(default=0.7, description="本地结果重排序权重")
    WEB_WEIGHT: float = Field(default=0.3, description="网络结果重排序权重")
    LOCAL_THRESHOLD: float = Field(default=0.5, description="触发网络检索的本地结果阈值")

    # RAG配置
    MAX_CONTEXT_LENGTH: int = Field(default=6000, description="上下文最大字符数")

    # API配置
    API_HOST: str = Field(default="0.0.0.0", description="API服务主机")
    API_PORT: int = Field(default=5002, description="API服务端口")
    DEBUG: bool = Field(default=True, description="调试模式")

    # CORS配置
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
        description="允许的跨域来源列表，生产环境应设置为具体域名"
    )

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
