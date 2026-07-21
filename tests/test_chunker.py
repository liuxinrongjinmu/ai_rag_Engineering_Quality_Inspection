"""
文本切片器（TextChunker）单元测试
测试文档类型感知切片、Markdown表格按行切片、章节上下文保留、空文档、短段落等功能
"""
import sys
import os

# 将项目根目录加入 sys.path，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from langchain_core.documents import Document

from app.processors.chunker import TextChunker


class TestTextChunker:
    """TextChunker 单元测试"""

    def test_split_markdown_with_tables(self):
        """
        测试：包含 Markdown 表格的文本，表格应按行切片，每行携带表头
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=50)

        markdown_text = """# 公路工程质量检测规范

## 检测要求

本规范规定了公路工程中各类材料的检测标准和方法。

| 检测项目 | 检测频率 | 取样数量 | 检测方法 |
|---------|---------|---------|---------|
| 压实度   | 每层1次  | 3个点   | T0921  |
| 含水率   | 每批次1次 | 2个样   | T0305  |
| 强度     | 每台班1次 | 3组    | T0558  |

## 检测频次说明

以上检测项目均需按规范要求执行，任何未经检测的工程部位不得进行下一道工序。"""

        doc = Document(
            page_content=markdown_text,
            metadata={"doc_id": "test-md-001", "doc_name": "road_test.md", "doc_type": "markdown"},
        )

        chunks = chunker.split_documents([doc])

        assert len(chunks) > 0, "应该至少产生一个切片"

        # 表格行应被切分为独立切片
        table_row_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "table_row"]
        assert len(table_row_chunks) >= 3, f"3行数据应产生至少3个表格行切片，实际: {len(table_row_chunks)}"

        # 每个表格行切片应包含表头
        for chunk in table_row_chunks:
            assert "表头：" in chunk.page_content, "表格行切片应包含表头"
            assert "检测项目:" in chunk.page_content, "表格行切片应包含'检测项目'列说明"

        # 切片 ID 唯一且不含空值
        chunk_ids = [c.metadata.get("chunk_id") for c in chunks]
        assert len(set(chunk_ids)) == len(chunk_ids), "每个切片的 chunk_id 应唯一"

    def test_split_large_table(self):
        """
        测试：超大型表格（行数很多，总长度超过 MAX_EMBEDDING_LENGTH 2000）
              应被切分为多个行级切片，且每个子切片都保留表头
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=50)

        header = "| 序号 | 检测项目 | 检测频率 | 取样数量 | 检测方法 |\n|------|---------|---------|---------|---------|\n"
        data_rows = []
        for i in range(1, 101):
            data_rows.append(f"| {i} | 压实度 | 每层1次 | 3个点 | T0921-2019 |")
        table_text = header + "\n".join(data_rows)

        assert len(table_text) > 2000, f"测试表格长度应超过2000，实际: {len(table_text)}"

        doc = Document(
            page_content=table_text,
            metadata={"doc_id": "test-big-table", "doc_name": "big_table.md", "doc_type": "markdown"},
        )

        chunks = chunker.split_documents([doc])

        assert len(chunks) > 1, f"大表格应被切分为多个切片，实际: {len(chunks)}"

        # 每一个表格切片都应包含表头（以 '表头：' 开头）
        for chunk in chunks:
            if chunk.metadata.get("chunk_type") == "table_row":
                assert "表头：" in chunk.page_content, \
                    f"每个表格切片应保留表头，但未在切片 {chunk.metadata.get('chunk_index')} 中找到"

        # 每个切片长度不超过 MAX_EMBEDDING_LENGTH (2000)
        for chunk in chunks:
            assert len(chunk.page_content) <= 2000, \
                f"切片长度 {len(chunk.page_content)} 超过 2000 上限"

    def test_table_row_focuses_on_specific_row(self):
        """
        测试：针对"扣分"类表格，每行切片应能独立匹配具体问题
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=20)

        table_text = """## 客户经理考核扣分标准

| 投诉类型 | 扣分 |
|---------|------|
| 一般投诉 | 2分 |
| 严重投诉 | 5分 |
| 重大投诉 | 10分 |
"""
        doc = Document(
            page_content=table_text,
            metadata={"doc_id": "test-penalty", "doc_name": "penalty.md", "doc_type": "markdown"},
        )

        chunks = chunker.split_documents([doc])
        table_row_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "table_row"]

        assert len(table_row_chunks) == 3, f"应有3个表格行切片，实际: {len(table_row_chunks)}"

        # 每个切片应包含对应的扣分数值
        scores = []
        for chunk in table_row_chunks:
            match = __import__('re').search(r'(\d+)分', chunk.page_content)
            if match:
                scores.append(int(match.group(1)))

        assert sorted(scores) == [2, 5, 10], f"扣分分值应分别为2/5/10，实际: {scores}"

    def test_split_text_document_with_space_table(self):
        """
        测试：PDF/TXT 中空格对齐的表格能被识别并按行切片
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=20)

        text = """## 考核标准

投诉类型    扣分
一般投诉    2分
严重投诉    5分
重大投诉    10分

其他说明文字，用于测试段落切片。"""

        doc = Document(
            page_content=text,
            metadata={"doc_id": "test-space-table", "doc_name": "space_table.pdf", "doc_type": "pdf"},
        )

        chunks = chunker.split_documents([doc])
        table_row_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "table_row"]

        assert len(table_row_chunks) >= 3, f"应识别出至少3行表格，实际: {len(table_row_chunks)}"

    def test_split_empty_document(self):
        """
        测试：空字符串输入应返回空列表
        """
        chunker = TextChunker()

        doc = Document(page_content="", metadata={"doc_id": "empty"})
        chunks = chunker.split_documents([doc])
        assert chunks == [], "空文档应返回空列表"

        doc2 = Document(page_content="   \n  \n  ", metadata={"doc_id": "whitespace"})
        chunks2 = chunker.split_documents([doc2])
        assert chunks2 == [], "纯空白文档应返回空列表"

        chunks3 = chunker.split_documents([])
        assert chunks3 == [], "空Document列表应返回空列表"

    def test_split_single_paragraph(self):
        """
        测试：短段落文本（长度小于 chunk_size）应产生单个切片
        """
        chunker = TextChunker(chunk_size=1000, chunk_overlap=200, min_chunk_size=50)

        short_text = "路基压实度应按每层每200m检测不少于4个点，这是公路工程质量控制的重要指标之一，必须严格执行相关规范要求。"

        doc = Document(
            page_content=short_text,
            metadata={"doc_id": "test-short", "doc_name": "short.txt", "doc_type": "txt"},
        )

        chunks = chunker.split_documents([doc])

        assert len(chunks) == 1, f"短文本应产生1个切片，实际: {len(chunks)}"
        assert short_text in chunks[0].page_content, "切片内容应包含原文"
        assert chunks[0].metadata.get("doc_id") == "test-short", "元数据中的 doc_id 应保留"

    def test_chunk_size_limit(self):
        """
        测试：所有切片内容长度不超过 MAX_EMBEDDING_LENGTH (2000)
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=50)

        long_text = ""
        paragraphs = [
            "路基填筑前必须进行基底处理，清除地表植被、树根和腐殖土。",
            "压实度检测采用灌砂法或环刀法，每层压实度必须达到设计要求。",
            "含水率检测应在摊铺后碾压前进行，每批次至少取2个样。",
            "混凝土强度检测采用标准养护28天抗压强度试验。",
        ]

        for para in paragraphs:
            for _ in range(15):
                long_text += para + "\n\n"

        doc = Document(
            page_content=long_text,
            metadata={"doc_id": "test-long", "doc_name": "long_doc.md", "doc_type": "markdown"},
        )

        chunks = chunker.split_documents([doc])

        assert len(chunks) > 1, f"长文本应产生多个切片，实际: {len(chunks)}"

        for chunk in chunks:
            assert len(chunk.page_content) <= 2000, \
                f"切片长度 {len(chunk.page_content)} 超过 2000 上限"

        indices = [c.metadata.get("chunk_index", -1) for c in chunks]
        assert indices == sorted(indices), "chunk_index 应该按序递增"

    def test_chunk_metadata_preserved(self):
        """
        测试：切片后原始元数据应保留并传播到每个切片
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=50)

        text = "路基压实度检测是公路工程质量控制的重要环节，必须严格按规范执行。"
        doc = Document(
            page_content=text,
            metadata={
                "doc_id": "preserve-001",
                "doc_name": "preserve_test.md",
                "doc_type": "markdown",
                "source_type": "local",
            },
        )

        chunks = chunker.split_documents([doc])

        for chunk in chunks:
            assert chunk.metadata.get("doc_id") == "preserve-001", \
                "doc_id 应保留在每个切片中"
            assert chunk.metadata.get("doc_name") == "preserve_test.md", \
                "doc_name 应保留在每个切片中"
            assert chunk.metadata.get("chunk_type") in ["paragraph", "table_row", "excel_row", "article"], \
                "切片类型应被正确标记"

        for i, chunk in enumerate(chunks):
            assert "chunk_id" in chunk.metadata, "每个切片应有 chunk_id"
            assert "chunk_index" in chunk.metadata, "每个切片应有 chunk_index"
            assert chunk.metadata["chunk_index"] == i, "chunk_index 从 0 开始连续"

    def test_excel_row_preserved(self):
        """
        测试：Excel 行级 Document 应被保留并增强表头上下文
        """
        chunker = TextChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=20)

        doc = Document(
            page_content="表格：检测频率\n表头：项目 | 频率\n项目: 压实度 | 频率: 每层1次",
            metadata={"doc_id": "test-excel", "doc_name": "freq.xlsx", "doc_type": "excel"},
        )

        chunks = chunker.split_documents([doc])

        assert len(chunks) == 1, f"Excel行应产生1个切片，实际: {len(chunks)}"
        assert chunks[0].metadata.get("chunk_type") == "excel_row", "Excel切片类型应为excel_row"
        assert "压实度" in chunks[0].page_content, "Excel切片应保留原始内容"

    def test_article_rules_chunking(self):
        """
        测试：PDF/Word 中的条例项（第X条、X、（X））应每条独立切片，
              并正确合并跨行内容
        """
        chunker = TextChunker(chunk_size=1000, chunk_overlap=200, min_chunk_size=20)

        text = """第五章  工作质量考核标准
第九条  工作质量考核实行扣分制。工作质量指个金客户经理在
从事所有个人业务时出现投诉、差错及风险。该项考核最多扣50 分，
如发生重大差错事故，按分行有关制度处理。
（一）服务质量考核：
1、工作责任心不强，缺乏配合协作精神；扣5 分
2、客户服务效率低，态度生硬或不及时为客户提供维护服务，
有客户投诉的,每投诉一次扣2 分
3、不服从支行工作安排，不认真参加分（支）行宣传活动的，
每次扣 2 分；
"""

        doc = Document(
            page_content=text,
            metadata={"doc_id": "test-article", "doc_name": "考核标准.pdf", "doc_type": "pdf"},
        )

        chunks = chunker.split_documents([doc])

        # 应至少产生 4 个切片：第九条 + 3 条例项
        assert len(chunks) >= 4, f"应至少产生4个切片，实际: {len(chunks)}"

        # 找到包含"客户投诉"的切片
        complaint_chunk = None
        for chunk in chunks:
            if "客户投诉" in chunk.page_content:
                complaint_chunk = chunk
                break

        assert complaint_chunk is not None, "应存在包含'客户投诉'的切片"
        assert "扣2 分" in complaint_chunk.page_content or "扣2分" in complaint_chunk.page_content, \
            f"客户投诉切片应包含扣分值，实际: {complaint_chunk.page_content}"
        assert complaint_chunk.metadata.get("chunk_type") == "article", \
            f"条例项切片类型应为 article，实际: {complaint_chunk.metadata.get('chunk_type')}"
