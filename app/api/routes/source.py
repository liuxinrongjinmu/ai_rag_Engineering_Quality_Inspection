"""
来源追溯接口
"""
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models.response import (
    SourceResponse,
    SourceDetail,
    ErrorResponse
)
from app.core.orchestrator import get_orchestrator

router = APIRouter(prefix="/source", tags=["来源追溯"])


@router.get(
    "/{chunk_id}",
    response_model=SourceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "切片不存在"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    },
    summary="来源追溯接口",
    description="根据切片ID获取详细的来源信息"
)
async def get_source(chunk_id: str):
    """
    来源追溯接口
    
    - **chunk_id**: 切片唯一标识
    """
    try:
        orchestrator = get_orchestrator()
        
        detail = orchestrator.get_source_detail(chunk_id)
        
        if not detail:
            raise HTTPException(
                status_code=404,
                detail=f"切片不存在: {chunk_id}"
            )
        
        source_detail = SourceDetail(**detail)
        
        return SourceResponse(
            code=0,
            message="success",
            data=source_detail
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取来源详情失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取来源详情失败: {str(e)}"
        )
