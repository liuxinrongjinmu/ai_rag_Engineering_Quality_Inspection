"""
问答接口
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
import json
import time

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
        use_cache = True

        if request.options:
            use_web_search = request.options.use_web_search
            top_k = request.options.top_k
            use_cache = getattr(request.options, 'use_cache', True)

        result = orchestrator.process_query(
            question=request.question,
            use_web_search=use_web_search,
            top_k=top_k,
            use_cache=use_cache
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


@router.post(
    "/stream",
    summary="流式问答接口",
    description="提交问题，流式返回答案（SSE格式）"
)
async def query_stream(request: QueryRequest):
    """
    流式问答接口（Server-Sent Events）
    """
    async def event_generator():
        start_time = time.time()

        try:
            orchestrator = get_orchestrator()

            use_web_search = True
            top_k = 5

            if request.options:
                use_web_search = request.options.use_web_search
                top_k = request.options.top_k

            from app.utils.cache import get_query_cache
            cache = get_query_cache()
            cached_result = cache.get(request.question, use_web_search)

            if cached_result:
                yield f"event: message\ndata: {json.dumps({'type': 'answer', 'content': cached_result['answer']}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'sources': cached_result.get('sources', []), 'query_time_ms': int((time.time() - start_time) * 1000), 'cached': True}, ensure_ascii=False)}\n\n"
                return

            # 获取流式生成器、来源信息和网络检索标记
            stream_gen, sources, used_web_search = orchestrator.process_query_stream(
                question=request.question,
                use_web_search=use_web_search,
                top_k=top_k,
            )

            full_answer = ""
            for chunk in stream_gen:
                full_answer += chunk
                yield f"event: message\ndata: {json.dumps({'type': 'answer', 'content': chunk}, ensure_ascii=False)}\n\n"

            query_time_ms = int((time.time() - start_time) * 1000)

            # 缓存完整结果（包含sources）
            sources_data = [s.model_dump() for s in sources]
            cache.set(
                question=request.question,
                data={
                    'answer': full_answer,
                    'sources': sources_data,
                    'used_web_search': used_web_search,
                },
                use_web_search=use_web_search,
            )

            yield f"event: done\ndata: {json.dumps({'sources': sources_data, 'query_time_ms': query_time_ms, 'used_web_search': used_web_search}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"流式查询失败: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
