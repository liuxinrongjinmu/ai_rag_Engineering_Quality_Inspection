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
    
    返回格式：
    event: message
    data: {"type": "answer", "content": "答案片段"}
    
    event: done
    data: {"sources": [...], "query_time_ms": 1234}
    """
    async def event_generator():
        start_time = time.time()
        
        try:
            orchestrator = get_orchestrator()
            orchestrator.initialize()
            
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
                yield f"event: done\ndata: {json.dumps({'sources': cached_result['sources'], 'query_time_ms': int((time.time() - start_time) * 1000), 'cached': True}, ensure_ascii=False)}\n\n"
                return
            
            from app.core.hybrid_retriever import get_hybrid_retriever
            from app.core.rag_engine import get_rag_engine
            
            hybrid_retriever = get_hybrid_retriever(top_k=top_k, use_web_search=use_web_search)
            rag_engine = get_rag_engine()
            
            retrieval_result = hybrid_retriever.retrieve(
                query=request.question,
                use_web_search=use_web_search
            )
            
            results = retrieval_result["results"]
            used_web_search = retrieval_result["used_web_search"]
            
            if not results:
                yield f"event: message\ndata: {json.dumps({'type': 'answer', 'content': '抱歉，没有找到相关的信息来回答您的问题。'}, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'sources': [], 'query_time_ms': int((time.time() - start_time) * 1000)}, ensure_ascii=False)}\n\n"
                return
            
            full_answer = ""
            for chunk in rag_engine.stream_generate(request.question, results):
                full_answer += chunk
                yield f"event: message\ndata: {json.dumps({'type': 'answer', 'content': chunk}, ensure_ascii=False)}\n\n"
            
            sources = rag_engine.extract_sources(results)
            query_time_ms = int((time.time() - start_time) * 1000)
            
            cache.set(
                question=request.question,
                data={
                    'answer': full_answer,
                    'sources': [s.model_dump() for s in sources],
                    'used_web_search': used_web_search
                },
                use_web_search=use_web_search
            )
            
            yield f"event: done\ndata: {json.dumps({'sources': [s.model_dump() for s in sources], 'query_time_ms': query_time_ms, 'used_web_search': used_web_search}, ensure_ascii=False)}\n\n"
            
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
