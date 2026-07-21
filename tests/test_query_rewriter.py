"""
查询重写器（QueryRewriter）单元测试
测试规则改写、空字符串处理、术语映射等功能
"""
import sys
import os

# 将项目根目录加入 sys.path，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from app.processors.query_rewriter import QueryRewriter


class TestQueryRewriter:
    """QueryRewriter 单元测试 —— 仅测试规则重写（不依赖 LLM）"""

    def test_rule_based_rewrite_colloquial(self):
        """
        测试：口语化输入能被规则正确改写为规范术语
        例："压实度怎么检" -> 应包含"检测方法"
        """
        rewriter = QueryRewriter(api_key=None)  # 不使用 LLM，仅规则重写

        # "怎么检" 应映射为 "检测方法"
        result = rewriter.rewrite("压实度怎么检")
        assert "检测方法" in result, \
            f"口语化'怎么检'应被替换为'检测方法'，实际输出: '{result}'"

        # "怎么取样" 应映射为 "取样方法"
        result2 = rewriter.rewrite("沥青怎么取样")
        assert "取样方法" in result2, \
            f"口语化'怎么取样'应被替换为'取样方法'，实际输出: '{result2}'"

        # "多久检一次" 应映射为 "检测频率"
        result3 = rewriter.rewrite("压实度多久检一次")
        assert "检测频率" in result3, \
            f"口语化'多久检一次'应被替换为'检测频率'，实际输出: '{result3}'"

        # "检什么" 应映射为 "检测项目"
        result4 = rewriter.rewrite("路基检什么")
        assert "检测项目" in result4, \
            f"口语化'检什么'应被替换为'检测项目'，实际输出: '{result4}'"

    def test_rule_based_rewrite_no_change(self):
        """
        测试：已经是规范术语的输入保持不变
        """
        rewriter = QueryRewriter(api_key=None)

        # 输入已经是规范术语，不应被改动
        formal_queries = [
            "压实度检测方法",
            "取样方法",
            "检测频率",
            "路基检测项目",
        ]

        for q in formal_queries:
            result = rewriter.rewrite(q)
            assert result == q, \
                f"规范查询 '{q}' 应保持不变，实际变为 '{result}'"

    def test_empty_query(self):
        """
        测试：空字符串或纯空白输入的处理
        """
        rewriter = QueryRewriter(api_key=None)

        # 空字符串
        result1 = rewriter.rewrite("")
        assert result1 == "", f"空字符串应原样返回，实际: '{result1}'"

        # None 输入（rewrite 只接受 str，但应安全处理）
        # 注意：类型标注是 str，我们测边界行为
        result2 = rewriter.rewrite("   ")
        assert result2 == "   ", f"纯空白字符串应原样返回，实际: '{result2}'"

    def test_term_mapping(self):
        """
        测试：特定术语映射是否按预期工作
        """
        rewriter = QueryRewriter(api_key=None)

        # "怎么检" -> "检测方法"
        result = rewriter.rewrite("水泥怎么检")
        assert "检测方法" in result, f"'怎么检'应映射为'检测方法'，实际: '{result}'"

        # "含水量" -> "含水率"
        result2 = rewriter.rewrite("含水量怎么测")
        assert "含水率" in result2, f"'含水量'应映射为'含水率'，实际: '{result2}'"

        # "塌落度" -> "坍落度" (错别字纠正)
        result3 = rewriter.rewrite("塌落度检测")
        assert "坍落度" in result3, f"'塌落度'应映射为'坍落度'，实际: '{result3}'"

        # "碎石" -> "粗集料"
        result4 = rewriter.rewrite("碎石检测项目")
        assert "粗集料" in result4, f"'碎石'应映射为'粗集料'，实际: '{result4}'"

        # "砂" -> "细集料"
        result5 = rewriter.rewrite("砂的检测频率")
        assert "细集料" in result5, f"'砂'应映射为'细集料'，实际: '{result5}'"

        # "cbr" -> "CBR试验" (大小写不敏感)
        result6 = rewriter.rewrite("cbr怎么检")
        assert "CBR试验" in result6, f"'cbr'应映射为'CBR试验'，实际: '{result6}'"

    def test_filler_word_removal(self):
        """
        测试：口语化修饰词（"请问"、"我想知道"等）应被移除
        """
        rewriter = QueryRewriter(api_key=None)

        # "请问" 应被移除
        result1 = rewriter.rewrite("请问压实度怎么检")
        assert "请问" not in result1, f"'请问'应被移除，实际: '{result1}'"

        # "我想知道" 应被移除
        result2 = rewriter.rewrite("我想知道含水率检测方法")
        assert "我想知道" not in result2, f"'我想知道'应被移除，实际: '{result2}'"

        # "帮我查一下" 应被移除
        result3 = rewriter.rewrite("帮我查一下路基检测项目")
        assert "帮我查一下" not in result3, f"'帮我查一下'应被移除，实际: '{result3}'"

    def test_already_mapped_word_not_remapped(self):
        """
        测试：如果结果中已包含规范术语，不应重复替换
        例如 "检测方法怎么检" 中"检测方法"已存在，不应再被替换
        """
        rewriter = QueryRewriter(api_key=None)

        # 如果查询中已有"检测方法"，"怎么检"不应再替换
        result = rewriter.rewrite("压实度检测方法")
        assert result == "压实度检测方法", \
            f"已包含规范术语的查询不应被修改，实际: '{result}'"

    def test_sentence_normalization(self):
        """
        测试：句子的规范化处理（通用规章 + 公路工程）
        """
        rewriter = QueryRewriter(api_key=None)

        # "XX扣几分" 应规范化为 "XX扣分"
        result1 = rewriter.rewrite("客户经理被投诉一次扣几分")
        assert "扣分" in result1, \
            f"'扣几分'应被规范化为'扣分'，实际: '{result1}'"

        # "XX有哪些" 应规范化为 "XX有哪些"
        result2 = rewriter.rewrite("路基检测有哪些")
        assert "检测项目" in result2, \
            f"'有哪些'应被规范化为'检测项目'，实际: '{result2}'"

    def test_query_expansion(self):
        """
        测试：查询扩展应生成多个语义相关查询
        """
        rewriter = QueryRewriter(api_key=None)

        expanded = rewriter.expand_query("客户经理被投诉一次扣几分")
        assert len(expanded) >= 2, f"应至少扩展为2个查询，实际: {len(expanded)}"
        assert any("扣分" in q for q in expanded), "扩展查询中应包含'扣分'"

    def test_rewrite_not_modify_when_filler_only(self):
        """
        测试：如果查询仅包含修饰词，重构后的查询不应是纯空字符串
        """
        rewriter = QueryRewriter(api_key=None)

        # 如果只有"查一下"这种修饰词，应该返回去除后的内容
        result = rewriter.rewrite("查一下压实度")
        assert "压实度" in result, f"去除修饰词后核心词汇'压实度'应保留，实际: '{result}'"
