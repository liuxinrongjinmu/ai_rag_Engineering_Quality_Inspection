"""
问答接口
"""
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models.response import (
    QueryRequest,
    QueryResponse,
    QueryData,
    ErrorResponse
)
from app.core.orchestrator import get_orchestrator

router = APIRouter(prefix="/query", tags=["问答"])


@router.post(
    "",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="问答接口",
    description="提交问题，返回答案和来源信息"
)
async def query(request: QueryRequest):
    """
    问答接口
    
    - **question**: 用户问题
    - **options**: 查询选项（可选）
    """
    try:
        orchestrator = get_orchestrator()
        
        use_web_search = True
        top_k = 5
        
        if request.options:
            use_web_search = request.options.use_web_search
            top_k = request.options.top_k
        
        result = orchestrator.process_query(
            question=request.question,
            use_web_search=use_web_search,
            top_k=top_k
        )
        
        return QueryResponse(
            code=0,
            message="success",
            data=result
        )
        
    except Exception as e:
        logger.error(f"查询处理失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"查询处理失败: {str(e)}"
        )
