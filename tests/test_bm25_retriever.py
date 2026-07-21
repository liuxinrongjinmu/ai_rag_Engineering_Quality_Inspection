"""
BM25 检索器单元测试
测试分词函数、专业词典加载、索引构建、原子保存
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from langchain_core.documents import Document


class TestBM25Tokenizer:
    """BM25 分词器单元测试"""

    @pytest.fixture(autouse=True)
    def _setup_jieba(self):
        """确保 jieba 专业词典已加载"""
        from app.retrievers.bm25_retriever import _init_jieba
        _init_jieba()

    def test_tokenize_chinese_text(self):
        """
        测试：中文文本正确分词，专业词汇被保留
        """
        from app.retrievers.bm25_retriever import _tokenize_func

        tokens = _tokenize_func("路基压实度检测频率是多少")
        assert "压实度" in tokens, "专业词'压实度'应被正确切分"
        assert "多少" in tokens, "'多少'应被切分"
        # jieba 可能将"检测频率"作为一个整体切分
        all_text = " ".join(tokens)
        assert "检测" in all_text, "应包含'检测'相关词"

    def test_tokenize_stop_words_removed(self):
        """
        测试：停用词被过滤
        """
        from app.retrievers.bm25_retriever import _tokenize_func

        tokens = _tokenize_func("压实度的检测方法")
        assert "压实度" in tokens, "专业词应保留"
        assert "的" not in tokens, "停用词'的'应被过滤"
        assert "和" not in tokens, "停用词'和'应被过滤"

    def test_tokenize_domain_words(self):
        """
        测试：专业领域词汇被正确切分
        """
        from app.retrievers.bm25_retriever import _tokenize_func

        test_cases = [
            ("客户投诉", "客户投诉"),
            ("扣分", "扣分"),
            ("检测频率", "检测频率"),
        ]
        for text, expected_word in test_cases:
            tokens = _tokenize_func(text)
            assert expected_word in tokens, f"'{text}' 分词结果应包含 '{expected_word}'，实际: {tokens}"

    def test_tokenize_punctuation(self):
        """
        测试：标点符号和单字符被过滤
        """
        from app.retrievers.bm25_retriever import _tokenize_func

        tokens = _tokenize_func("压实度，检测。")
        for token in tokens:
            assert len(token) > 1 or token.isalnum(), f"单字符 '{token}' 不应出现在结果中"


class TestBM25BuildAndSave:
    """BM25 构建与保存单元测试"""

    def test_build_bm25_retriever(self):
        """
        测试：从 Documents 构建 BM25 检索器
        """
        from app.retrievers.bm25_retriever import build_bm25_retriever, get_bm25_retriever

        docs = [
            Document(page_content="压实度检测采用灌砂法", metadata={"doc_id": "doc1"}),
            Document(page_content="含水率每批次检测2个样", metadata={"doc_id": "doc2"}),
            Document(page_content="混凝土强度28天抗压试验", metadata={"doc_id": "doc3"}),
        ]

        retriever = build_bm25_retriever(docs)
        assert retriever is not None, "应成功构建检索器"
        assert get_bm25_retriever() is not None, "单例应可用"

        # 检索测试
        results = retriever.invoke("压实度怎么检测")
        assert len(results) > 0, "应返回检索结果"
        assert any("压实度" in r.page_content for r in results), "检索结果应包含相关文档"

    def test_save_and_load_bm25(self):
        """
        测试：BM25 索引原子保存与加载
        """
        from app.retrievers.bm25_retriever import (
            build_bm25_retriever, save_bm25_retriever, load_bm25_retriever,
            get_bm25_retriever,
        )

        docs = [
            Document(page_content="压实度检测采用灌砂法", metadata={"doc_id": "doc1"}),
            Document(page_content="含水率每批次检测2个样", metadata={"doc_id": "doc2"}),
        ]

        retriever = build_bm25_retriever(docs)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            tmp_path = f.name

        try:
            save_bm25_retriever(retriever, tmp_path)
            assert os.path.exists(tmp_path), "索引文件应存在"
            # .tmp 文件不应残留
            assert not os.path.exists(tmp_path + ".tmp"), "临时文件应已清理"

            # 加载
            loaded = load_bm25_retriever(tmp_path)
            assert loaded is not None, "应成功加载索引"

            results = loaded.invoke("压实度")
            assert len(results) == 2, "应有2个检索结果"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if os.path.exists(tmp_path + ".tmp"):
                os.unlink(tmp_path + ".tmp")

    def test_load_nonexistent_file(self):
        """
        测试：加载不存在的索引文件返回 None
        """
        from app.retrievers.bm25_retriever import load_bm25_retriever

        result = load_bm25_retriever("/nonexistent/path/bm25.pkl")
        assert result is None, "不存在的文件应返回 None"
