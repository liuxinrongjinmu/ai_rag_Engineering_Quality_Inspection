"""
数据入库脚本
使用LangChain组件解析文档、切片、向量化并存入ChromaDB
同时构建BM25索引
"""
import sys
from pathlib import Path
from loguru import logger
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.processors.document_loaders import load_documents_from_directory
from app.processors.chunker import TextChunker
from app.retrievers.bm25_retriever import build_bm25_retriever, save_bm25_retriever
from app.utils.logger import setup_logger


def main():
    """
    主函数：执行数据入库流程
    """
    setup_logger(debug=True)

    settings = get_settings()
    start_time = time.time()

    data_dir = Path(__file__).parent.parent / "data" / "processed"
    if not data_dir.exists():
        data_dir = Path(__file__).parent.parent / "data" / "raw"

    logger.info(f"开始处理数据目录: {data_dir}")

    # 1. 加载文档
    logger.info("步骤1: 加载文档...")
    documents = load_documents_from_directory(str(data_dir))
    if not documents:
        logger.error("没有找到可处理的数据")
        return

    logger.info(f"加载完成: {len(documents)}个Document")

    # 2. 切片
    logger.info("步骤2: 文本切片...")
    chunker = TextChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    chunks = chunker.split_documents(documents)
    logger.info(f"切片完成: {len(chunks)}个切片")

    # 3. 入库ChromaDB
    logger.info("步骤3: 向量化并写入ChromaDB...")
    from app.infrastructure.vectorstore import get_vectorstore

    MAX_EMBED_LEN = 2000
    safe_chunks = []
    for chunk in chunks:
        if len(chunk.page_content) > MAX_EMBED_LEN:
            chunk.page_content = chunk.page_content[:MAX_EMBED_LEN]
        safe_chunks.append(chunk)

    vectorstore = get_vectorstore()

    batch_size = 50
    all_ids = []
    for i in range(0, len(safe_chunks), batch_size):
        batch = safe_chunks[i:i + batch_size]
        logger.info(f"入库批次 {i // batch_size + 1}/{(len(safe_chunks) + batch_size - 1) // batch_size}...")
        ids = vectorstore.add_documents(batch)
        all_ids.extend(ids)

    logger.info(f"ChromaDB入库完成: {len(all_ids)}个切片")

    # 4. 构建BM25索引
    logger.info("步骤4: 构建BM25索引...")
    build_bm25_retriever(chunks)

    bm25_path = Path(settings.BM25_INDEX_PATH)
    bm25_path.parent.mkdir(parents=True, exist_ok=True)

    from app.retrievers.bm25_retriever import get_bm25_retriever
    bm25_retriever = get_bm25_retriever()
    if bm25_retriever:
        save_bm25_retriever(bm25_retriever, str(bm25_path))

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"入库完成! 共{len(safe_chunks)}个切片, 耗时{elapsed}秒")
    print(f"\n入库统计:")
    print(f"  - 处理文档数: {len(documents)}")
    print(f"  - 总切片数: {len(safe_chunks)}")
    print(f"  - ChromaDB入库: {len(all_ids)}个")
    print(f"  - 处理时间: {elapsed}秒")


if __name__ == "__main__":
    main()
