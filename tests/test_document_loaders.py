"""
文档加载器（MarkdownLoader / TxtLoader / PDFLoader / WordLoader / ExcelLoader）单元测试
使用 pytest 的 tmp_path fixture 创建临时文件进行测试
"""
import sys
import os
from pathlib import Path

# 将项目根目录加入 sys.path，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from app.processors.document_loaders import (
    MarkdownLoader, ExcelLoader, TxtLoader, PDFLoader, WordLoader,
)


class TestMarkdownLoader:
    """MarkdownLoader 单元测试"""

    def test_load_markdown(self, tmp_path):
        """
        测试：加载一个正常 Markdown 文件，验证 Document 内容正确
        """
        # 创建临时 .md 文件
        md_content = """# 公路工程质量检测规范

## 路基检测

路基压实度应按每层每200m检测不少于4个点。

## 路面检测

路面检测包括平整度、抗滑性能和弯沉值等指标。"""

        md_file = tmp_path / "test_spec.md"
        md_file.write_text(md_content, encoding="utf-8")

        loader = MarkdownLoader(str(md_file))
        documents = loader.load()

        assert len(documents) == 1, "应返回 1 个 Document"
        doc = documents[0]

        # 验证内容
        assert "路基压实度" in doc.page_content, "Document 内容应包含原始文本"
        assert "路面检测" in doc.page_content, "Document 内容应包含原始文本"
        assert doc.page_content == md_content, "Document 内容应与源文件完全一致"

        # 验证元数据
        assert "doc_id" in doc.metadata, "应有 doc_id"
        assert "doc_name" in doc.metadata, "应有 doc_name"
        assert doc.metadata.get("doc_type") == "markdown", "doc_type 应为 markdown"
        assert doc.metadata.get("source_type") == "local", "source_type 应为 local"
        assert "file_path" in doc.metadata, "应有 file_path"
        assert str(md_file) in doc.metadata.get("file_path", ""), \
            "file_path 应指向源文件"

    def test_load_empty_markdown(self, tmp_path):
        """
        测试：加载空 Markdown 文件，应返回空列表
        """
        # 创建空文件
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        loader = MarkdownLoader(str(md_file))
        documents = loader.load()

        assert documents == [], "空 Markdown 文件应返回空列表"

    def test_load_whitespace_only_markdown(self, tmp_path):
        """
        测试：仅包含空白字符的 Markdown 文件应返回空列表
        """
        md_file = tmp_path / "whitespace.md"
        md_file.write_text("   \n\t\n   \n", encoding="utf-8")

        loader = MarkdownLoader(str(md_file))
        documents = loader.load()

        assert documents == [], "纯空白 Markdown 文件应返回空列表"

    def test_metadata_generation(self, tmp_path):
        """
        测试：Document 元数据包含正确的字段和值
        """
        md_content = "# 水泥检测\n水泥检测包括凝结时间、安定性和强度等指标。"
        md_file = tmp_path / "水泥检测规范.md"
        md_file.write_text(md_content, encoding="utf-8")

        loader = MarkdownLoader(str(md_file))
        documents = loader.load()

        assert len(documents) == 1
        metadata = documents[0].metadata

        # 必选字段
        assert "doc_id" in metadata, "metadata 应包含 doc_id"
        assert "doc_name" in metadata, "metadata 应包含 doc_name"
        assert "doc_type" in metadata, "metadata 应包含 doc_type"
        assert "source_type" in metadata, "metadata 应包含 source_type"
        assert "file_path" in metadata, "metadata 应包含 file_path"

        # 值语义检查
        assert metadata["doc_type"] == "markdown", "doc_type 应为 'markdown'"
        assert metadata["source_type"] == "local", "source_type 应为 'local'"
        assert metadata["doc_name"] == "水泥检测规范", \
            f"doc_name 应为去除扩展名的文件名，实际: {metadata['doc_name']}"

        # doc_id 应为 md5 前 16 位 hex
        assert len(metadata["doc_id"]) == 16, "doc_id 应为 16 位 hex"


class TestExcelLoader:
    """ExcelLoader 单元测试"""

    def test_load_xlsx(self, tmp_path):
        """
        测试：加载一个包含数据的 Excel (.xlsx) 文件
        """
        # 使用 openpyxl 创建临时 Excel 文件
        import openpyxl

        xlsx_file = tmp_path / "test_data.xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "检测项目"

        # 写入表头和数据行
        ws["A1"] = "检测项目"
        ws["B1"] = "检测频率"
        ws["C1"] = "取样数量"
        ws["D1"] = "检测方法"

        ws["A2"] = "压实度"
        ws["B2"] = "每层1次"
        ws["C2"] = "3个点"
        ws["D2"] = "T0921"

        ws["A3"] = "含水率"
        ws["B3"] = "每批次1次"
        ws["C3"] = "2个样"
        ws["D3"] = "T0305"

        ws["A4"] = "强度"
        ws["B4"] = "每台班1次"
        ws["C4"] = "3组"
        ws["D4"] = "T0558"

        wb.save(str(xlsx_file))

        loader = ExcelLoader(str(xlsx_file))
        documents = loader.load()

        # 应返回 3 个 Document（每行一个）
        assert len(documents) == 3, f"应返回 3 个 Document，实际: {len(documents)}"

        # 验证每个 Document 的内容包含对应行数据
        assert "压实度" in documents[0].page_content, "第一行应包含'压实度'"
        assert "含水率" in documents[1].page_content, "第二行应包含'含水率'"
        assert "强度" in documents[2].page_content, "第三行应包含'强度'"

        # 验证元数据
        for i, doc in enumerate(documents):
            assert doc.metadata.get("doc_type") == "excel", \
                f"第{i}行的 doc_type 应为 'excel'"
            assert doc.metadata.get("source_type") == "local", \
                f"第{i}行的 source_type 应为 'local'"
            assert "row_index" in doc.metadata, \
                f"第{i}行应有 row_index"

    def test_load_empty_xlsx(self, tmp_path):
        """
        测试：加载仅含表头没有数据的 Excel 文件
        """
        import openpyxl

        xlsx_file = tmp_path / "empty_data.xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "检测项目"
        ws["B1"] = "检测频率"
        ws["C1"] = "检测方法"

        # 第二行全空（无有效数据）
        ws["A2"] = ""
        ws["B2"] = ""
        ws["C2"] = ""

        wb.save(str(xlsx_file))

        loader = ExcelLoader(str(xlsx_file))
        documents = loader.load()

        # 空数据行应被跳过，应返回空列表
        assert documents == [], "无有效数据的 Excel 应返回空列表"

    def test_excel_metadata(self, tmp_path):
        """
        测试：Excel 加载的 Document 元数据包含正确字段
        """
        import openpyxl

        xlsx_file = tmp_path / "metadata_test.xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "检测项目"
        ws["B1"] = "检测频率"
        ws["A2"] = "压实度"
        ws["B2"] = "每层1次"

        wb.save(str(xlsx_file))

        loader = ExcelLoader(str(xlsx_file))
        documents = loader.load()

        assert len(documents) == 1
        metadata = documents[0].metadata

        # 必选字段
        assert metadata["doc_type"] == "excel", "doc_type 应为 'excel'"
        assert metadata["source_type"] == "local", "source_type 应为 'local'"
        assert "doc_id" in metadata, "应有 doc_id"
        assert "doc_name" in metadata, "应有 doc_name"
        assert "file_path" in metadata, "应有 file_path"
        assert "row_index" in metadata, "应有 row_index"

        # row_index 应为整数
        assert isinstance(metadata["row_index"], int), \
            f"row_index 应为整数，实际类型: {type(metadata['row_index'])}"

    def test_load_nonexistent_file(self):
        """
        测试：加载不存在的文件应返回空列表（不抛异常）
        """
        loader = MarkdownLoader("/nonexistent/path/not_exist.md")
        documents = loader.load()
        assert documents == [], "不存在的文件应返回空列表"

    def test_xlsx_content_format(self, tmp_path):
        """
        测试：Excel 加载的 Document page_content 格式正确（包含表格名、表头、键值对）
        """
        import openpyxl

        xlsx_file = tmp_path / "format_test.xlsx"

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "检测项目"
        ws["B1"] = "检测频率"
        ws["A2"] = "压实度"
        ws["B2"] = "每层1次"

        wb.save(str(xlsx_file))

        loader = ExcelLoader(str(xlsx_file))
        documents = loader.load()

        assert len(documents) == 1
        content = documents[0].page_content

        # 格式应包含表格名、表头、键值对
        assert "表格：format_test" in content, \
            f"内容应包含表格名，实际: '{content}'"
        assert "表头：检测项目 | 检测频率" in content, \
            f"内容应包含表头，实际: '{content}'"
        assert "检测项目: 压实度" in content, \
            f"内容格式应包含列名:值，实际: '{content}'"
        assert "检测频率: 每层1次" in content, \
            f"内容格式应包含列名:值，实际: '{content}'"


class TestTxtLoader:
    """TxtLoader 单元测试"""

    def test_load_utf8_txt(self, tmp_path):
        """
        测试：加载 UTF-8 编码的 TXT 文件
        """
        txt_content = "这是公路工程质量检测的标准文本。\n包含多行内容。"
        txt_file = tmp_path / "test.txt"
        txt_file.write_text(txt_content, encoding="utf-8")

        loader = TxtLoader(str(txt_file))
        documents = loader.load()

        assert len(documents) == 1
        assert documents[0].page_content == txt_content
        assert documents[0].metadata["doc_type"] == "txt"
        assert documents[0].metadata["source_type"] == "local"

    def test_load_gbk_txt(self, tmp_path):
        """
        测试：加载 GBK 编码的 TXT 文件（自动编码探测）
        """
        txt_content = "公路工程检测标准GBK编码文本"
        txt_file = tmp_path / "gbk_test.txt"
        txt_file.write_text(txt_content, encoding="gbk")

        loader = TxtLoader(str(txt_file))
        documents = loader.load()

        assert len(documents) == 1
        assert txt_content in documents[0].page_content

    def test_load_empty_txt(self, tmp_path):
        """
        测试：空 TXT 文件返回空列表
        """
        txt_file = tmp_path / "empty.txt"
        txt_file.write_text("", encoding="utf-8")

        loader = TxtLoader(str(txt_file))
        documents = loader.load()

        assert documents == []


class TestPDFLoader:
    """PDFLoader 单元测试"""

    def test_load_pdf(self, tmp_path):
        """
        测试：加载 PDF 文件，提取文本内容
        """
        from pypdf import PdfWriter, PageObject

        pdf_file = tmp_path / "test.pdf"

        writer = PdfWriter()
        # 创建带文本的空页面
        page = PageObject.create_blank_page(width=595, height=842)
        writer.add_page(page)
        writer.add_blank_page(width=595, height=842)
        writer.write(str(pdf_file))

        loader = PDFLoader(str(pdf_file))
        documents = loader.load()

        assert isinstance(documents, list), "应返回列表"

    def test_load_nonexistent_pdf(self):
        """
        测试：加载不存在的 PDF 返回空列表
        """
        loader = PDFLoader("/nonexistent/not_exist.pdf")
        documents = loader.load()
        assert documents == []

    def test_pdf_table_formatting(self):
        """
        测试：PDF 加载器对空格对齐表格的 Markdown 格式化
        """
        loader = PDFLoader("/nonexistent/dummy.pdf")

        raw_text = "投诉类型    扣分\n一般投诉    2分\n严重投诉    5分\n重大投诉    10分"
        formatted = loader._format_tables(raw_text)

        assert "| 投诉类型 | 扣分 |" in formatted, f"表头应格式化为 Markdown 表格，实际: '{formatted}'"
        assert "| 一般投诉 | 2分 |" in formatted, f"数据行应格式化为 Markdown 表格，实际: '{formatted}'"


class TestWordLoader:
    """WordLoader 单元测试"""

    def test_load_docx(self, tmp_path):
        """
        测试：加载 Word (.docx) 文件，提取段落文本
        """
        from docx import Document as DocxDocument

        docx_file = tmp_path / "test.docx"

        doc = DocxDocument()
        doc.add_paragraph("公路工程质量检测规范")
        doc.add_paragraph("路基压实度检测频率：每层每200m检测不少于4个点。")
        doc.add_paragraph("路面平整度检测应符合相关标准要求。")
        doc.save(str(docx_file))

        loader = WordLoader(str(docx_file))
        documents = loader.load()

        assert len(documents) == 1
        content = documents[0].page_content
        assert "路基压实度" in content
        assert "路面平整度" in content
        assert documents[0].metadata["doc_type"] == "word"

    def test_load_docx_with_table(self, tmp_path):
        """
        测试：加载包含表格的 Word 文件
        """
        from docx import Document as DocxDocument

        docx_file = tmp_path / "table_test.docx"

        doc = DocxDocument()
        doc.add_paragraph("以下为检测项目表：")

        table = doc.add_table(rows=3, cols=3)
        table.cell(0, 0).text = "检测项目"
        table.cell(0, 1).text = "检测频率"
        table.cell(0, 2).text = "检测方法"
        table.cell(1, 0).text = "压实度"
        table.cell(1, 1).text = "每层1次"
        table.cell(1, 2).text = "T0921"
        table.cell(2, 0).text = "含水量"
        table.cell(2, 1).text = "每批次1次"
        table.cell(2, 2).text = "T0305"

        doc.save(str(docx_file))

        loader = WordLoader(str(docx_file))
        documents = loader.load()

        assert len(documents) == 1
        content = documents[0].page_content
        assert "压实度" in content
        assert "T0921" in content
        # Word 表格现在输出为 Markdown 格式
        assert "| 检测项目 | 检测频率 | 检测方法 |" in content
        assert "| 压实度 | 每层1次 | T0921 |" in content

    def test_load_empty_docx(self, tmp_path):
        """
        测试：空 Word 文件返回空列表
        """
        from docx import Document as DocxDocument

        docx_file = tmp_path / "empty.docx"

        doc = DocxDocument()
        doc.add_paragraph("")  # 空段落
        doc.save(str(docx_file))

        loader = WordLoader(str(docx_file))
        documents = loader.load()

        assert documents == []
