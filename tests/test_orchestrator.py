"""
查询编排器单元测试
覆盖：意图分类、查询扩展、检索流程
"""
import pytest
from app.processors.query_rewriter import QueryRewriter


class TestQueryRewriter:
    """查询重写器测试"""

    def setup_method(self):
        self.rewriter = QueryRewriter()

    def test_rewrite_step_to_procedure(self):
        """'步骤' 应被扩展为 '试验步骤 检测步骤 方法'"""
        result = self.rewriter.rewrite("步骤是什么")
        assert "试验步骤" in result or "检测步骤" in result or "方法" in result

    def test_rewrite_deduction_impact(self):
        """'有什么影响' 应映射为 '扣分'"""
        result = self.rewriter.rewrite("投诉有什么影响")
        assert "扣分" in result

    def test_rewrite_method_query(self):
        """'怎么检' 应映射为 '检测方法'"""
        result = self.rewriter.rewrite("压实度怎么检")
        assert "检测方法" in result

    def test_intent_classification_numeric(self):
        """数值类意图识别"""
        intents = self.rewriter._classify_intent("压实度是多少")
        assert "numeric" in intents

    def test_intent_classification_procedure(self):
        """步骤类意图识别"""
        intents = self.rewriter._classify_intent("试验步骤有哪些")
        assert "procedure" in intents

    def test_intent_classification_overview(self):
        """概述类意图识别"""
        intents = self.rewriter._classify_intent("检测项目包含哪些")
        assert "overview" in intents

    def test_intent_classification_impact(self):
        """影响类意图识别"""
        intents = self.rewriter._classify_intent("客户投诉有什么影响")
        assert "impact" in intents

    def test_expand_query_multiple_variants(self):
        """查询扩展应生成多个变体"""
        variants = self.rewriter.expand_query("压实度试验步骤是什么")
        assert len(variants) >= 2
        assert len(variants) <= 6  # 限制最多6个变体

    def test_expand_query_dedup(self):
        """查询扩展应去重"""
        variants = self.rewriter.expand_query("压实度")
        assert len(variants) == len(set(variants))  # 无重复

    def test_empty_query(self):
        """空查询处理"""
        result = self.rewriter.rewrite("")
        assert result == ""

    def test_rewrite_no_change(self):
        """无需重写的查询保持原样"""
        result = self.rewriter.rewrite("压实度")
        assert "压实度" in result


class TestIntentionVariants:
    """意图变体生成测试"""

    def setup_method(self):
        self.rewriter = QueryRewriter()

    def test_numeric_deduction_variant(self):
        """扣分类应生成扣分标准变体"""
        variants = self.rewriter._generate_intent_variants("被投诉扣几分", "numeric")
        assert any("扣分标准" in v for v in variants)

    def test_procedure_step_variant(self):
        """步骤类应生成试验步骤变体"""
        variants = self.rewriter._generate_intent_variants("怎么做压实度试验", "procedure")
        assert any("试验步骤" in v or "检测步骤" in v or "操作规程" in v for v in variants)

    def test_overview_category_variant(self):
        """概述类应生成分类/目录变体"""
        variants = self.rewriter._generate_intent_variants("检测项目包含哪些", "overview")
        assert any("分类" in v or "目录" in v for v in variants)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
