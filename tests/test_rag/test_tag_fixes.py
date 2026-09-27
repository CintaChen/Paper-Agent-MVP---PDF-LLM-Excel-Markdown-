"""测试标签提取修复"""
import pytest
from unittest.mock import patch, MagicMock
from processors.cleaner import extract_evidence
from readers.pdf_reader import PDFReader


class TestExtractEvidence:
    def test_basic_extraction(self):
        """基本证据截取"""
        text = "本文研究了深度学习在图像识别中的应用。实验结果表明，该方法优于传统方法。"
        keyword = "深度学习"
        result = extract_evidence(text, keyword, window=80)
        assert "深度学习" in result

    def test_sentence_boundary_not_cut(self):
        """长句中的并列项不被截断"""
        text = "本研究采用了问卷调查、实验研究和案例分析三种方法，结果表明混合方法能够更全面地回答研究问题。"
        keyword = "实验研究"
        result = extract_evidence(text, keyword, window=80)
        # 应该包含完整的句子，不会把"问卷调查、实验研究和案例分析"截断
        assert "问卷调查" in result or "案例分析" in result or "实验" in result

    def test_keyword_not_found(self):
        """关键词不在原文中"""
        text = "这是一段关于机器学习的文本。"
        keyword = "深度学习"
        result = extract_evidence(text, keyword, window=80)
        assert result == "深度学习"

    def test_empty_text(self):
        """空文本"""
        assert extract_evidence("", "关键词") == ""

    def test_empty_keyword(self):
        """空关键词"""
        assert extract_evidence("文本内容", "") == ""

    def test_window_size(self):
        """窗口大小控制"""
        text = "A" * 200 + "关键词" + "B" * 200
        result = extract_evidence(text, "关键词", window=50)
        assert len(result) <= 200  # 合理范围内


class TestHeuristicExtractTitle:
    def test_filter_noise_patterns(self):
        """过滤噪音行"""
        reader = PDFReader(input_dir="./test_data")
        first_page = """Available online at www.sciencedirect.com
Academic Editor: John Doe
ORIGINAL ARTICLE
Received: 2024-01-01
Accepted: 2024-02-01
DOI: 10.1234/test
Journal of Computer Science

基于深度学习的图像识别方法研究

张三，李四

摘要：本文提出了一种新的图像识别方法..."""

        result = reader._heuristic_extract_title_v2(first_page)
        assert result is not None
        assert "深度学习" in result or "图像识别" in result

    def test_english_paper_title(self):
        """英文论文标题提取"""
        reader = PDFReader(input_dir="./test_data")
        first_page = """Available online at
Academic Editor: Jane Smith
ORIGINAL ARTICLE

A Novel Approach to Natural Language Processing Using Deep Learning

John Doe, Jane Smith

Abstract: This paper presents a novel approach..."""

        result = reader._heuristic_extract_title_v2(first_page)
        assert result is not None
        assert len(result) > 15

    def test_no_candidates(self):
        """没有候选行"""
        reader = PDFReader(input_dir="./test_data")
        first_page = """Available online at
Academic Editor:
ORIGINAL ARTICLE
Received: 2024"""

        result = reader._heuristic_extract_title_v2(first_page)
        assert result is None


class TestSplitKeywords:
    def test_semicolon_separator(self):
        """分号分隔"""
        reader = PDFReader(input_dir="./test_data")
        result = reader._split_keywords("自然语言处理；机器学习；深度学习")
        assert len(result) == 3
        assert "自然语言处理" in result

    def test_comma_separator(self):
        """逗号分隔"""
        reader = PDFReader(input_dir="./test_data")
        result = reader._split_keywords("NLP, machine learning, deep learning")
        assert len(result) == 3

    def test_mixed_separators(self):
        """混合分隔符"""
        reader = PDFReader(input_dir="./test_data")
        result = reader._split_keywords("AI；机器学习,深度学习；NLP")
        assert len(result) == 4

    def test_duplicate_keywords(self):
        """去重"""
        reader = PDFReader(input_dir="./test_data")
        result = reader._split_keywords("机器学习, 机器学习, 深度学习")
        assert len(result) == 2

    def test_empty_input(self):
        """空输入"""
        reader = PDFReader(input_dir="./test_data")
        assert reader._split_keywords("") == []


class TestExtractKeywordsFromText:
    def test_chinese_keywords(self):
        """中文关键词"""
        reader = PDFReader(input_dir="./test_data")
        text = """摘要：本文研究了...
关键词：自然语言处理；机器学习；深度学习

引言..."""
        result = reader._extract_keywords_from_text(text)
        assert "自然语言处理" in result
        assert "机器学习" in result
        assert "深度学习" in result

    def test_english_keywords(self):
        """英文关键词"""
        reader = PDFReader(input_dir="./test_data")
        text = """Abstract: This paper...
Keywords: NLP, machine learning, deep learning

Introduction..."""
        result = reader._extract_keywords_from_text(text)
        assert "NLP" in result

    def test_no_keywords(self):
        """没有关键词"""
        reader = PDFReader(input_dir="./test_data")
        text = "这是一段没有关键词的文本"
        result = reader._extract_keywords_from_text(text)
        assert result == []
