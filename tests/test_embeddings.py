"""
Embeddings 重试机制 (RetryableEmbeddings) 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest


class FakeEmbeddings:
    """
    模拟 Embeddings 实现，用于测试重试逻辑
    """
    def __init__(self, fail_count: int = 0):
        self.call_count = 0
        self.fail_count = fail_count

    def embed_documents(self, texts):
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise ConnectionError("模拟 API 连接失败")
        return [[0.1] * 10 for _ in texts]

    def embed_query(self, text):
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise TimeoutError("模拟 API 超时")
        return [0.1] * 10


class TestRetryableEmbeddings:
    """RetryableEmbeddings 单元测试"""

    def test_embed_documents_success_first_attempt(self):
        """
        测试：首次调用成功，不触发重试
        """
        from app.infrastructure.embeddings import RetryableEmbeddings

        fake = FakeEmbeddings(fail_count=0)
        retryable = RetryableEmbeddings(fake, max_retries=2, base_delay=0.01)

        result = retryable.embed_documents(["测试文本1", "测试文本2"])
        assert len(result) == 2, "应返回2个向量"
        assert fake.call_count == 1, "只应调用1次"

    def test_embed_documents_with_retry(self):
        """
        测试：首次失败后自动重试，最终成功
        """
        from app.infrastructure.embeddings import RetryableEmbeddings

        fake = FakeEmbeddings(fail_count=1)
        retryable = RetryableEmbeddings(fake, max_retries=2, base_delay=0.01)

        result = retryable.embed_documents(["测试文本"])
        assert len(result) == 1, "重试后应成功返回结果"
        assert fake.call_count == 2, "应调用2次（1次失败 + 1次重试成功）"

    def test_embed_documents_exhaust_retries(self):
        """
        测试：超过最大重试次数后，抛出最后一个异常
        """
        from app.infrastructure.embeddings import RetryableEmbeddings

        fake = FakeEmbeddings(fail_count=5)
        retryable = RetryableEmbeddings(fake, max_retries=2, base_delay=0.01)

        with pytest.raises(ConnectionError, match="模拟 API 连接失败"):
            retryable.embed_documents(["测试文本"])
        assert fake.call_count == 3, "应调用 max_retries+1=3 次"

    def test_embed_query_with_retry(self):
        """
        测试：embed_query 也支持重试
        """
        from app.infrastructure.embeddings import RetryableEmbeddings

        fake = FakeEmbeddings(fail_count=1)
        retryable = RetryableEmbeddings(fake, max_retries=2, base_delay=0.01)

        result = retryable.embed_query("测试查询")
        assert len(result) == 10, "embed_query 应返回正确维度的向量"
        assert fake.call_count == 2, "应重试1次后成功"

    def test_attribute_proxy(self):
        """
        测试：未定义的属性代理到基础实例
        """
        from app.infrastructure.embeddings import RetryableEmbeddings

        fake = FakeEmbeddings(fail_count=0)
        retryable = RetryableEmbeddings(fake, max_retries=2)

        # 访问 fake 上的原生属性
        assert retryable.fail_count == 0, "属性应代理到基础实例"
        assert retryable.call_count == 0, "属性应代理到基础实例"
