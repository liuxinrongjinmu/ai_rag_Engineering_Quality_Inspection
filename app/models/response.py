"""
API响应模型
定义API接口的请求和响应结构
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from app.models.document import SourceType


class QueryOptions(BaseModel):
    """
    查询选项
    """
    use_web_search: bool = Field(default=True, description="是否启用网络检索")
    top_k: int = Field(default=5, description="返回结果数量")
    include_source: bool = Field(default=True, description="是否包含来源信息")


class QueryRequest(BaseModel):
    """
    问答请求
    """
    question: str = Field(..., description="用户问题", min_length=1, max_length=1000)
    options: Optional[QueryOptions] = Field(default=None, description="查询选项")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "土方路基压实度检测频率是多少？",
                "options": {
                    "use_web_search": True,
                    "top_k": 5,
                    "include_source": True
                }
            }
        }


class SourceInfo(BaseModel):
    """
    来源信息
    """
    chunk_id: str = Field(..., description="切片ID")
    doc_id: str = Field(..., description="文档ID")
    doc_name: str = Field(..., description="文档名称")
    page: Optional[int] = Field(None, description="页码")
    section: Optional[str] = Field(None, description="章节")
    content: str = Field(..., description="原文内容")
    source_type: SourceType = Field(..., description="来源类型")
    url: Optional[str] = Field(None, description="URL(网络来源)")


class QueryResponse(BaseModel):
    """
    问答响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: "QueryData" = Field(..., description="响应数据")


class QueryData(BaseModel):
    """
    问答数据
    """
    answer: str = Field(..., description="生成的答案")
    sources: List[SourceInfo] = Field(default_factory=list, description="来源列表")
    query_time_ms: int = Field(..., description="查询耗时(毫秒)")
    used_web_search: bool = Field(default=False, description="是否使用了网络检索")


class SourceDetail(BaseModel):
    """
    来源详情
    """
    chunk_id: str = Field(..., description="切片ID")
    doc_id: str = Field(..., description="文档ID")
    doc_name: str = Field(..., description="文档名称")
    page: Optional[int] = Field(None, description="页码")
    section: Optional[str] = Field(None, description="章节")
    full_content: str = Field(..., description="完整内容")
    context_before: Optional[str] = Field(None, description="前文上下文")
    context_after: Optional[str] = Field(None, description="后文上下文")


class SourceResponse(BaseModel):
    """
    来源追溯响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: SourceDetail = Field(..., description="来源详情")


class HealthStatus(BaseModel):
    """
    健康状态
    """
    status: str = Field(..., description="状态")
    components: dict = Field(..., description="组件状态")
    stats: dict = Field(..., description="统计信息")


class HealthResponse(BaseModel):
    """
    健康检查响应
    """
    status: str = Field(..., description="整体状态")
    components: dict = Field(..., description="组件状态")
    stats: dict = Field(..., description="统计信息")


class ErrorResponse(BaseModel):
    """
    错误响应
    """
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细信息")


QueryResponse.model_rebuild()
