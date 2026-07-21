"""
缓存模块（MemoryCacheBackend & QueryCache）单元测试
仅测试内存后端，不依赖 Redis
"""
import sys
import os
import time

# 将项目根目录加入 sys.path，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from app.utils.cache import MemoryCacheBackend, QueryCache


class TestMemoryCacheBackend:
    """MemoryCacheBackend 单元测试"""

    def test_cache_hit(self):
        """
        测试：set 后 get 能拿到相同数据
        """
        backend = MemoryCacheBackend(max_size=100)

        test_data = {"answer": "路基压实度检测方法为灌砂法和环刀法", "sources": ["doc1", "doc2"]}
        backend.set(key="query:001", data=test_data, ttl_seconds=3600)

        result = backend.get("query:001")
        assert result is not None, "缓存命中应返回数据"
        assert result["answer"] == test_data["answer"], "返回的 answer 应一致"
        assert result["sources"] == test_data["sources"], "返回的 sources 应一致"

    def test_cache_miss(self):
        """
        测试：get 不存在的 key 返回 None
        """
        backend = MemoryCacheBackend(max_size=100)

        result = backend.get("non_existent_key")
        assert result is None, "不存在的 key 应返回 None"

    def test_cache_expiry(self):
        """
        测试：设置短暂 TTL，过期后 get 返回 None
        """
        backend = MemoryCacheBackend(max_size=100)

        test_data = {"answer": "临时缓存数据"}
        backend.set(key="expire_test", data=test_data, ttl_seconds=1)

        # 立即获取应命中
        result1 = backend.get("expire_test")
        assert result1 is not None, "刚写入的数据应该能取到"

        # 等待 TTL 过期
        time.sleep(1.1)

        result2 = backend.get("expire_test")
        assert result2 is None, "过期的缓存应返回 None"

    def test_cache_clear(self):
        """
        测试：clear 后所有条目被移除
        """
        backend = MemoryCacheBackend(max_size=100)

        # 写入多条数据
        for i in range(5):
            backend.set(key=f"key_{i}", data={"value": i}, ttl_seconds=3600)

        # 验证数据存在
        for i in range(5):
            assert backend.get(f"key_{i}") is not None, f"key_{i} 应该存在"

        # 清空缓存
        backend.clear()

        # 验证全部不存在
        for i in range(5):
            assert backend.get(f"key_{i}") is None, f"clear 后 key_{i} 应不存在"

    def test_cache_eviction(self):
        """
        测试：当缓存数量超过 max_size，最旧的条目被淘汰
        """
        backend = MemoryCacheBackend(max_size=3)

        # 写入 3 条数据（逐步写入以产生时间差）
        backend.set(key="oldest", data={"val": "oldest"}, ttl_seconds=3600)
        time.sleep(0.01)
        backend.set(key="mid", data={"val": "mid"}, ttl_seconds=3600)
        time.sleep(0.01)
        backend.set(key="newest", data={"val": "newest"}, ttl_seconds=3600)

        # 此时缓存中有 3 条
        stats = backend.get_stats()
        assert stats["total_entries"] == 3, "应该有 3 条缓存"

        # 再写入一条，超过 max_size，应淘汰最旧的 "oldest"
        backend.set(key="overflow", data={"val": "overflow"}, ttl_seconds=3600)

        # "oldest" 应被淘汰
        assert backend.get("oldest") is None, "最旧的条目 'oldest' 应被淘汰"

        # 其他条目应仍存在
        assert backend.get("mid") is not None, "'mid' 应仍存在"
        assert backend.get("newest") is not None, "'newest' 应仍存在"
        assert backend.get("overflow") is not None, "'overflow' 应存在"

        stats_after = backend.get_stats()
        assert stats_after["total_entries"] == 3, "淘汰后应有 3 条"


class TestQueryCache:
    """QueryCache 单元测试 —— 使用内存后端"""

    def test_cache_key_generation(self):
        """
        测试：相同问题和相同 use_web_search 生成相同 key
        """
        cache = QueryCache(max_size=100, ttl_seconds=3600, redis_url=None)

        data = {"answer": "压实度检测方法"}
        cache.set(question="压实度怎么检", data=data, use_web_search=False)

        # 相同问题获取
        result = cache.get(question="压实度怎么检", use_web_search=False)
        assert result is not None, "相同问题应命中缓存"
        assert result["answer"] == "压实度检测方法", "缓存数据应一致"

    def test_cache_web_search_key_diff(self):
        """
        测试：相同问题但 use_web_search 不同，生成的 key 不同
        """
        cache = QueryCache(max_size=100, ttl_seconds=3600, redis_url=None)

        # 写入 use_web_search=False 的数据
        cache.set(
            question="压实度检测",
            data={"answer": "本地检索结果"},
            use_web_search=False,
        )

        # 写入 use_web_search=True 的数据（应不同 key）
        cache.set(
            question="压实度检测",
            data={"answer": "含网络检索结果"},
            use_web_search=True,
        )

        # 获取时应分别返回不同的数据
        result_no_web = cache.get(question="压实度检测", use_web_search=False)
        result_with_web = cache.get(question="压实度检测", use_web_search=True)

        assert result_no_web is not None, "无网络检索应命中缓存"
        assert result_with_web is not None, "有网络检索应命中缓存"
        assert result_no_web["answer"] != result_with_web["answer"], \
            "不同 use_web_search 的缓存应是不同的"

        assert result_no_web["answer"] == "本地检索结果", "应返回对应数据"
        assert result_with_web["answer"] == "含网络检索结果", "应返回对应数据"

    def test_query_cache_get_stats(self):
        """
        测试：get_stats 返回正确的统计信息
        """
        cache = QueryCache(max_size=100, ttl_seconds=7200, redis_url=None)

        cache.set(question="测试问题", data={"answer": "测试答案"})

        stats = cache.get_stats()
        assert stats["backend"] == "memory", "后端应为 memory"
        assert stats["total_entries"] == 1, "应有 1 条缓存"
        assert stats["max_size"] == 100, "max_size 应为 100"
        assert stats["ttl_seconds"] == 7200, "ttl_seconds 应为 7200"

    def test_query_cache_clear(self):
        """
        测试：QueryCache.clear() 清理所有数据
        """
        cache = QueryCache(max_size=100, ttl_seconds=3600, redis_url=None)

        for i in range(3):
            cache.set(question=f"问题{i}", data={"answer": f"答案{i}"})

        # 验证存在
        for i in range(3):
            assert cache.get(question=f"问题{i}") is not None, f"问题{i} 应存在"

        # 清空
        cache.clear()

        # 验证全部不存在
        for i in range(3):
            assert cache.get(question=f"问题{i}") is None, f"clear 后问题{i} 应不存在"

    def test_query_cache_invalidate(self):
        """
        测试：invalidate 使指定问题缓存失效
        """
        cache = QueryCache(max_size=100, ttl_seconds=3600, redis_url=None)

        # 写入两条数据
        cache.set(question="保留的问题", data={"answer": "保留"}, use_web_search=False)
        cache.set(question="要失效的问题", data={"answer": "失效"}, use_web_search=False)

        # 失效指定问题
        cache.invalidate(question="要失效的问题", use_web_search=False)

        # "保留的问题" 应还在
        result_keep = cache.get(question="保留的问题", use_web_search=False)
        assert result_keep is not None, "未失效的问题应可获取"
        assert result_keep["answer"] == "保留", "数据应不变"

        # "要失效的问题" 应不存在
        result_invalid = cache.get(question="要失效的问题", use_web_search=False)
        assert result_invalid is None, "已失效的问题应返回 None"
