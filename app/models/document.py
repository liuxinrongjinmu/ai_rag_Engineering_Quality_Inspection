"""
文档数据模型
定义文档和切片的数据结构
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SourceType(str, Enum):
    """
    数据来源类型
    """
    LOCAL = "local"
    WEB = "web"


class DocumentType(str, Enum):
    """
    文档类型
    """
    PDF = "pdf"
    EXCEL = "excel"


class Document(BaseModel):
    """
    文档模型
    """
    doc_id: str = Field(..., description="文档唯一标识")
    doc_name: str = Field(..., description="文档名称")
    doc_type: DocumentType = Field(..., description="文档类型")
    file_path: str = Field(..., description="文件路径")
    total_pages: Optional[int] = Field(None, description="总页数")
    total_chunks: int = Field(default=0, description="切片数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: dict = Field(default_factory=dict, description="元数据")


class Chunk(BaseModel):
    """
    文本切片模型
    """
    chunk_id: str = Field(..., description="切片唯一标识")
    doc_id: str = Field(..., description="所属文档ID")
    doc_name: str = Field(..., description="文档名称")
    content: str = Field(..., description="切片内容")
    page: Optional[int] = Field(None, description="页码")
    section: Optional[str] = Field(None, description="章节")
    source_type: SourceType = Field(default=SourceType.LOCAL, description="来源类型")
    metadata: dict = Field(default_factory=dict, description="额外元数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "chunk_001",
                "doc_id": "JTG_F80-1-2017",
                "doc_name": "公路工程质量检验评定标准",
                "content": "土方路基压实度检测频率...",
                "page": 15,
                "section": "4.2.2",
                "source_type": "local",
                "metadata": {}
            }
        }


class SearchResult(BaseModel):
    """
    检索结果模型
    """
    chunk: Chunk = Field(..., description="切片内容")
    score: float = Field(..., description="相似度分数")
    source_url: Optional[str] = Field(None, description="来源URL(网络检索)")


class WebSearchResult(BaseModel):
    """
    网络检索结果模型
    """
    title: str = Field(..., description="标题")
    content: str = Field(..., description="内容")
    url: str = Field(..., description="来源URL")
    score: Optional[float] = Field(None, description="相关度分数")
