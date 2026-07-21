"""
管理接口
提供文档管理、知识库重建和统计功能
"""
import asyncio
import threading
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from app.models.response import ErrorResponse

router = APIRouter(prefix="/admin", tags=["管理"])

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".xls", ".xlsx"}

# 最大文件大小 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# 数据目录
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "processed"

# BM25 重建锁（防止并发竞态）
_bm25_rebuild_lock = threading.Lock()


def _load_single_file(file_path: str) -> List[Any]:
    """
    加载单个文件为Document列表
    根据文件扩展名选择对应的加载器

    :param file_path: 文件路径
    :return: Document列表
    """
    from app.processors.document_loaders import (
        MarkdownLoader, ExcelLoader, TxtLoader, PDFLoader, WordLoader,
    )

    suffix = Path(file_path).suffix.lower()
    if suffix == ".md":
        loader = MarkdownLoader(file_path)
    elif suffix == ".txt":
        loader = TxtLoader(file_path)
    elif suffix == ".pdf":
        loader = PDFLoader(file_path)
    elif suffix == ".docx":
        loader = WordLoader(file_path)
    elif suffix in (".xls", ".xlsx"):
        loader = ExcelLoader(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")

    return loader.load()


def _ingest_documents(documents: List[Any]) -> int:
    """
    将Document列表切片、向量化并存入ChromaDB，同时重建BM25索引

    :param documents: Document列表
    :return: 入库的切片数量
    """
    from app.config import get_settings
    from app.processors.chunker import TextChunker
    from app.infrastructure.vectorstore import get_vectorstore

    settings = get_settings()

    # 1. 切片
    chunker = TextChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    chunks = chunker.split_documents(documents)

    if not chunks:
        logger.warning("文档切片结果为空")
        return 0

    # 1.5 统计每个文档的切片总数，为小文档加权做准备
    doc_chunk_counts: dict = {}
    for chunk in chunks:
        doc_id = chunk.metadata.get("doc_id", "?")
        doc_chunk_counts[doc_id] = doc_chunk_counts.get(doc_id, 0) + 1
    for chunk in chunks:
        doc_id = chunk.metadata.get("doc_id", "?")
        chunk.metadata["doc_total_chunks"] = doc_chunk_counts.get(doc_id, 0)

    # 2. 截断过长内容并警告
    max_embed_len = getattr(settings, 'MAX_EMBEDDING_LENGTH', 2000)
    for chunk in chunks:
        if len(chunk.page_content) > max_embed_len:
            truncated_len = len(chunk.page_content) - max_embed_len
            doc_name = chunk.metadata.get('doc_name', '?')
            chunk_idx = chunk.metadata.get('chunk_index', '?')
            logger.warning(
                f"切片内容过长被截断: doc={doc_name} idx={chunk_idx} "
                f"原始={len(chunk.page_content)} 截断={max_embed_len} 丢失={truncated_len}字符"
            )
            chunk.page_content = chunk.page_content[:max_embed_len]

    # 3. 写入ChromaDB
    vectorstore = get_vectorstore()
    batch_size = 50
    all_ids = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        ids = vectorstore.add_documents(batch)
        all_ids.extend(ids)

    logger.info(f"入库完成: {len(chunks)}个切片 -> ChromaDB")

    # 4. 重建BM25索引
    _rebuild_bm25_from_chromadb()

    return len(chunks)


def _rebuild_bm25_from_chromadb():
    """
    从ChromaDB读取所有切片并重建BM25索引（带锁，防止并发竞态）
    """
    if not _bm25_rebuild_lock.acquire(blocking=False):
        logger.info("BM25重建正在进行中，跳过本次重建")
        return

    try:
        from langchain_core.documents import Document
        from app.infrastructure.vectorstore import get_vectorstore
        from app.retrievers.bm25_retriever import build_bm25_retriever, save_bm25_retriever
        from app.config import get_settings

        settings = get_settings()

        vectorstore = get_vectorstore()
        collection = vectorstore._collection

        # 获取所有切片
        results = collection.get(include=["documents", "metadatas"])
        if not results or not results.get("ids"):
            logger.warning("ChromaDB中没有数据，跳过BM25重建")
            return

        docs = []
        for i in range(len(results["ids"])):
            doc = Document(
                page_content=results["documents"][i],
                metadata=results["metadatas"][i] if results.get("metadatas") else {},
            )
            docs.append(doc)

        build_bm25_retriever(docs)

        bm25_path = Path(settings.BM25_INDEX_PATH)
        bm25_path.parent.mkdir(parents=True, exist_ok=True)

        from app.retrievers.bm25_retriever import get_bm25_retriever
        bm25_retriever = get_bm25_retriever()
        if bm25_retriever:
            save_bm25_retriever(bm25_retriever, str(bm25_path))

        logger.info(f"BM25索引重建完成: {len(docs)}个切片")
    except Exception as e:
        logger.error(f"BM25索引重建失败: {e}")
    finally:
        _bm25_rebuild_lock.release()


# =================== 响应模型 ===================

class UploadResponse(BaseModel):
    """
    上传文档响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Dict[str, Any] = Field(..., description="上传结果")


class DocumentItem(BaseModel):
    """
    文档信息
    """
    doc_id: str = Field(..., description="文档ID")
    doc_name: str = Field(..., description="文档名称")
    doc_type: str = Field(..., description="文档类型")
    chunk_count: int = Field(..., description="切片数量")


class DocumentListResponse(BaseModel):
    """
    文档列表响应（分页）
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: List[DocumentItem] = Field(default_factory=list, description="文档列表")
    total: int = Field(default=0, description="文档总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页数量")


class DeleteResponse(BaseModel):
    """
    删除文档响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="删除结果")


class RebuildResponse(BaseModel):
    """
    知识库重建响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Dict[str, Any] = Field(default_factory=dict, description="重建结果")


class DocStatItem(BaseModel):
    """
    文档级别统计
    """
    doc_id: str = Field(..., description="文档ID")
    doc_name: str = Field(..., description="文档名称")
    doc_type: str = Field(..., description="文档类型")
    chunk_count: int = Field(..., description="切片数量")


class StatsResponse(BaseModel):
    """
    统计信息响应
    """
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Dict[str, Any] = Field(..., description="统计信息")


# =================== 接口实现 ===================

@router.post(
    "/documents/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "文件格式不支持"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    },
    summary="上传文档",
    description="上传MD/PDF/Word/TXT/XLS/XLSX文件，保存到data/processed/目录，然后入库到ChromaDB",
)
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档接口

    - 支持 .md / .txt / .pdf / .docx / .xls / .xlsx 文件
    - 文件保存到 data/processed/ 目录
    - 自动切片、向量化、写入ChromaDB
    - 自动重建BM25索引
    """
    # 1. 校验文件扩展名
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 2. 校验文件大小
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大: 最大支持 {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # 3. 确保目标目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 4. 保存文件到 data/processed/
    file_path = DATA_DIR / file.filename
    try:
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"文件已保存: {file_path}")
    except Exception as e:
        logger.error(f"文件保存失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 5. 加载文档，获取 doc_id
    try:
        documents = await asyncio.to_thread(_load_single_file, str(file_path))
        if not documents:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=400, detail="文件内容为空，无法提取任何有效数据")

        new_doc_id = documents[0].metadata.get("doc_id", "")

        # 6. 检查是否有同名文档，先清理旧切片和缓存
        if new_doc_id:
            from app.infrastructure.vectorstore import get_vectorstore

            vectorstore = get_vectorstore()
            collection = vectorstore._collection
            existing = collection.get(where={"doc_id": new_doc_id}, include=["metadatas"])
            if existing and existing.get("ids"):
                old_count = len(existing["ids"])
                collection.delete(ids=existing["ids"])
                logger.info(f"覆盖上传: 已清理旧切片 {old_count} 个 (doc_id={new_doc_id})")

                # 清除查询缓存
                from app.utils.cache import get_query_cache
                get_query_cache().clear()
                logger.info("查询缓存已清除（覆盖上传）")

        # 7. 入库
        chunk_count = await asyncio.to_thread(_ingest_documents, documents)

        doc_id = new_doc_id
        doc_name = documents[0].metadata.get("doc_name", "")
        doc_type = documents[0].metadata.get("doc_type", "")

        return UploadResponse(
            code=0,
            message="文档上传并入库成功",
            data={
                "file_name": file.filename,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "chunk_count": chunk_count,
            },
        )

    except HTTPException:
        # 入库失败时清理孤儿文件
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"入库失败，已清理孤儿文件: {file_path}")
            except Exception:
                pass
        raise
    except Exception as e:
        logger.error(f"文档入库失败: {e}")
        # 入库失败时清理孤儿文件
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"入库失败，已清理孤儿文件: {file_path}")
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"文档入库失败: {str(e)}")


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="文档列表",
    description="获取已入库文档列表及每个文档的切片数量，支持分页",
)
async def list_documents(page: int = 1, page_size: int = 20):
    """
    文档列表接口（分页）

    从ChromaDB元数据中聚合去重文档名和切片数量

    :param page: 页码（从1开始）
    :param page_size: 每页数量（默认20）
    """
    try:
        from app.infrastructure.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        collection = vectorstore._collection

        # 获取所有切片的元数据
        results = collection.get(include=["metadatas"])
        metadatas = results.get("metadatas") or []

        # 按 doc_id 聚合统计
        doc_stats: Dict[str, Dict[str, Any]] = {}
        for meta in metadatas:
            doc_id = meta.get("doc_id", "")
            if not doc_id:
                continue
            if doc_id not in doc_stats:
                doc_stats[doc_id] = {
                    "doc_id": doc_id,
                    "doc_name": meta.get("doc_name", ""),
                    "doc_type": meta.get("doc_type", ""),
                    "chunk_count": 0,
                }
            doc_stats[doc_id]["chunk_count"] += 1

        all_docs = [DocumentItem(**v) for v in doc_stats.values()]
        total = len(all_docs)

        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        paged_docs = all_docs[start:end]

        return DocumentListResponse(
            code=0,
            message="success",
            data=paged_docs,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@router.delete(
    "/documents/{doc_id}",
    response_model=DeleteResponse,
    responses={
        404: {"model": ErrorResponse, "description": "文档不存在"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    },
    summary="删除文档",
    description="删除指定文档及其所有切片，然后重建BM25索引",
)
async def delete_document(doc_id: str):
    """
    删除文档接口

    - 从ChromaDB删除指定doc_id的所有切片
    - 同步删除 data/processed/ 中的源文件
    - 自动重建BM25索引
    """
    try:
        from app.infrastructure.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        collection = vectorstore._collection

        # 先查询该文档的切片数量
        existing = collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )

        if not existing or not existing.get("ids"):
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")

        deleted_count = len(existing["ids"])
        doc_name = ""
        if existing.get("metadatas"):
            doc_name = existing["metadatas"][0].get("doc_name", "")

        # 从ChromaDB删除
        collection.delete(where={"doc_id": doc_id})
        logger.info(f"已从ChromaDB删除文档: doc_id={doc_id}, 删除{deleted_count}个切片")

        # 同步删除 data/processed/ 下的源文件，避免重建知识库时再次出现
        if doc_name:
            source_path = DATA_DIR / doc_name
            try:
                if source_path.exists() and source_path.is_file():
                    source_path.unlink()
                    logger.info(f"已删除源文件: {source_path}")
            except Exception as file_error:
                logger.warning(f"删除源文件失败: {source_path}, 错误: {file_error}")

        # 重建BM25索引
        await asyncio.to_thread(_rebuild_bm25_from_chromadb)

        # 清除查询缓存
        from app.utils.cache import get_query_cache
        await asyncio.to_thread(get_query_cache().clear)
        logger.info("查询缓存已清除（文档删除）")

        return DeleteResponse(
            code=0,
            message=f"文档已删除: {doc_name or doc_id}",
            data={
                "doc_id": doc_id,
                "doc_name": doc_name,
                "deleted_chunks": deleted_count,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@router.post(
    "/knowledge/rebuild",
    response_model=RebuildResponse,
    responses={
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    },
    summary="重建知识库",
    description="扫描data/processed/目录，重新切片、向量化、入库",
)
async def rebuild_knowledge():
    """
    知识库重建接口

    扫描 data/processed/ 目录中的所有文件，
    重新执行完整的入库流程：加载 → 切片 → 向量化 → 写入ChromaDB → 构建BM25索引
    """
    try:
        from app.processors.document_loaders import load_documents_from_directory

        if not DATA_DIR.exists():
            raise HTTPException(status_code=400, detail=f"数据目录不存在: {DATA_DIR}")

        # 1. 加载文档
        documents = await asyncio.to_thread(load_documents_from_directory, str(DATA_DIR))

        if not documents:
            raise HTTPException(status_code=400, detail="数据目录中没有可处理的文件")

        logger.info(f"重建知识库: 加载{len(documents)}个文档")

        # 2. 清空现有ChromaDB集合
        from app.infrastructure.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        collection = vectorstore._collection

        old_count = collection.count()
        if old_count > 0:
            # 获取所有ID并删除
            all_ids = collection.get()["ids"]
            if all_ids:
                collection.delete(ids=all_ids)
            logger.info(f"已清空ChromaDB集合: 删除{old_count}个切片")

        # 3. 切片 → 向量化 → 入库 → BM25
        chunk_count = await asyncio.to_thread(_ingest_documents, documents)

        # 4. 清除查询缓存（知识库数据已更新，缓存过期）
        from app.utils.cache import get_query_cache
        await asyncio.to_thread(get_query_cache().clear)
        logger.info("查询缓存已清除（知识库重建）")

        return RebuildResponse(
            code=0,
            message="知识库重建完成",
            data={
                "doc_count": len(documents),
                "chunk_count": chunk_count,
                "old_chunk_count": old_count,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"知识库重建失败: {e}")
        raise HTTPException(status_code=500, detail=f"知识库重建失败: {str(e)}")


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="知识库统计",
    description="获取知识库统计信息：文档数、切片数、每个文档的切片数",
)
async def get_stats():
    """
    知识库统计接口

    返回总切片数、总文档数以及每个文档级别的切片统计
    """
    try:
        from app.infrastructure.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        collection = vectorstore._collection

        total_chunks = collection.count()

        # 获取所有切片的元数据
        results = collection.get(include=["metadatas"])
        metadatas = results.get("metadatas") or []

        # 按 doc_id 聚合统计
        doc_stats: Dict[str, Dict[str, Any]] = {}
        for meta in metadatas:
            doc_id = meta.get("doc_id", "")
            if not doc_id:
                continue
            if doc_id not in doc_stats:
                doc_stats[doc_id] = {
                    "doc_id": doc_id,
                    "doc_name": meta.get("doc_name", ""),
                    "doc_type": meta.get("doc_type", ""),
                    "chunk_count": 0,
                }
            doc_stats[doc_id]["chunk_count"] += 1

        # 计算平均切片数
        total_docs = len(doc_stats)
        avg_chunks = round(total_chunks / total_docs, 2) if total_docs > 0 else 0

        return StatsResponse(
            code=0,
            message="success",
            data={
                "total_chunks": total_chunks,
                "total_docs": total_docs,
                "avg_chunks_per_doc": avg_chunks,
                "docs": [DocStatItem(**v) for v in doc_stats.values()],
            },
        )

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")
