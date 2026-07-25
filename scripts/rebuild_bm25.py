"""
仅重建 BM25 索引（不重建 Chroma 向量库）
用于更新分词词典或修复 BM25 索引时使用
"""
import sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.processors.document_loaders import load_documents_from_directory
from app.processors.chunker import TextChunker
from app.retrievers.bm25_retriever import build_bm25_retriever, save_bm25_retriever
from app.utils.logger import setup_logger


def main():
    setup_logger(debug=True)
    settings = get_settings()

    data_dir = Path(__file__).parent.parent / "data" / "processed"
    if not data_dir.exists():
        data_dir = Path(__file__).parent.parent / "data" / "raw"

    logger.info(f"加载数据目录: {data_dir}")
    documents = load_documents_from_directory(str(data_dir))
    logger.info(f"加载完成: {len(documents)}个Document")

    logger.info("文本切片...")
    chunker = TextChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    chunks = chunker.split_documents(documents)
    logger.info(f"切片完成: {len(chunks)}个切片")

    logger.info("构建BM25索引...")
    build_bm25_retriever(chunks)

    bm25_path = Path(settings.BM25_INDEX_PATH)
    bm25_path.parent.mkdir(parents=True, exist_ok=True)

    from app.retrievers.bm25_retriever import get_bm25_retriever
    bm25_retriever = get_bm25_retriever()
    if bm25_retriever:
        save_bm25_retriever(bm25_retriever, str(bm25_path))
        logger.info(f"BM25索引已保存: {bm25_path}")


if __name__ == "__main__":
    main()
