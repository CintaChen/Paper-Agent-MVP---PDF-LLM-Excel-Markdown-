"""测试内容标签提取"""
import pytest
import json
from core.document import Document, Chunk, ContentTag
from rag.tag_extractor import (
    ContentTagExtractor,
    safe_parse_json,
    extract_keywords_from_text,
    STOP_WORDS,
)


class TestSafeParseJson:
    def test_clean_json(self):
        text = '{"domain": "NLP", "confidence": 0.9}'
        result = safe_parse_json(text)
        assert result["domain"] == "NLP"
        assert result["confidence"] == 0.9

    def test_json_with_markdown_block(self):
        text = '```json\n{"domain": "NLP", "confidence": 0.9}\n```'
        result = safe_parse_json(text)
        assert result["domain"] == "NLP"

    def test_json_with_surrounding_text(self):
        text = '这是分析结果：\n{"domain": "NLP"}\n希望对你有帮助'
        result = safe_parse_json(text)
        assert result["domain"] == "NLP"

    def test_json_with_single_quotes(self):
        text = "{'domain': 'NLP', 'confidence': 0.9}"
        result = safe_parse_json(text)
        assert result["domain"] == "NLP"

    def test_empty_string(self):
        assert safe_parse_json("") == {}

    def test_invalid_json(self):
        assert safe_parse_json("not json at all") == {}


class TestExtractKeywordsFromText:
    def test_chinese_keywords_semicolon(self):
        text = "摘要内容...\n关键词：自然语言处理；机器学习；深度学习\n\n引言..."
        result, _ = extract_keywords_from_text(text)
        assert "自然语言处理" in result
        assert "机器学习" in result
        assert "深度学习" in result

    def test_english_keywords(self):
        text = "Abstract...\nKeywords: NLP, machine learning, deep learning\n\nIntroduction..."
        result, _ = extract_keywords_from_text(text)
        assert "NLP" in result
        assert "machine learning" in result

    def test_keywords_with_comma(self):
        text = "关键词: 人工智能, 教育, 应用"
        result, _ = extract_keywords_from_text(text)
        assert "人工智能" in result
        assert "教育" in result

    def test_stop_words_filtered(self):
        text = "关键词：研究；分析；方法；技术"
        result, _ = extract_keywords_from_text(text)
        # 停用词应该被过滤
        assert "研究" not in result
        assert "分析" not in result

    def test_no_keywords(self):
        text = "这是一段没有关键词的文本"
        result, _ = extract_keywords_from_text(text)
        assert result == []

    def test_max_10_keywords(self):
        text = "关键词：a1；a2；a3；a4；a5；a6；a7；a8；a9；a10；a11；a12"
        result, _ = extract_keywords_from_text(text)
        assert len(result) <= 10


class TestContentTagExtractor:
    def test_extract_with_pdf_keywords(self):
        """测试自带关键词提取"""
        chunks = [
            Chunk(
                id="test_1",
                text="摘要：本文研究了自然语言处理在教育中的应用。\n关键词：自然语言处理；机器学习；教育应用\n\n引言内容...",
                page=1,
                metadata={"doc_id": "test_doc"},
            ),
            Chunk(
                id="test_2",
                text="这是第二段内容。",
                page=2,
                metadata={"doc_id": "test_doc"},
            ),
        ]
        doc = Document(
            id="test_doc",
            title="测试论文",
            chunks=chunks,
        )

        # 不调用 LLM，只测试自带关键词提取
        extractor = ContentTagExtractor(llm_client=None)
        keywords, _ = extract_keywords_from_text("\n".join(c.text for c in doc.chunks))

        # 验证关键词被正确提取
        assert "自然语言处理" in keywords
        assert "机器学习" in keywords
        assert "教育应用" in keywords

    def test_deduplicate(self):
        """测试去重"""
        extractor = ContentTagExtractor(llm_client=None)
        tags = [
            ContentTag(tag_type="topic", value="NLP", confidence=1.0, source="pdf_keywords"),
            ContentTag(tag_type="topic", value="NLP", confidence=0.8, source="llm_extracted"),
            ContentTag(tag_type="domain", value="CS", confidence=0.9, source="llm_extracted"),
        ]
        result = extractor._deduplicate(tags)
        assert len(result) == 2
        # 保留置信度高的
        nlp_tags = [t for t in result if t.value == "NLP"]
        assert len(nlp_tags) == 1
        assert nlp_tags[0].confidence == 1.0

    def test_extract_abstract(self):
        """测试摘要提取"""
        chunks = [
            Chunk(
                id="test_1",
                text="摘要：这是一篇关于深度学习的论文。\n\n关键词：深度学习；神经网络\n\n引言...",
                page=1,
                metadata={"doc_id": "test_doc"},
            ),
        ]
        doc = Document(id="test_doc", title="测试", chunks=chunks)
        extractor = ContentTagExtractor(llm_client=None)
        abstract = extractor._extract_abstract(doc)
        assert "深度学习" in abstract

    def test_get_introduction_text(self):
        """测试引言提取"""
        chunks = [
            Chunk(id="t1", text="第一段", page=1, metadata={}),
            Chunk(id="t2", text="第二段", page=2, metadata={}),
        ]
        doc = Document(id="test_doc", title="测试", chunks=chunks)
        extractor = ContentTagExtractor(llm_client=None)
        intro = extractor._get_introduction_text(doc, max_chars=100)
        assert "第一段" in intro
        assert "第二段" in intro


class TestContentTagModel:
    def test_create_tag(self):
        tag = ContentTag(
            tag_type="domain",
            value="自然语言处理",
            confidence=0.95,
            evidence="论文明确提及 NLP 领域",
            source="llm_extracted",
            needs_review=False,
        )
        assert tag.tag_type == "domain"
        assert tag.value == "自然语言处理"
        assert tag.confidence == 0.95

    def test_default_values(self):
        tag = ContentTag(tag_type="topic", value="test")
        assert tag.confidence == 1.0
        assert tag.evidence == ""
        assert tag.source == "pdf_keywords"
        assert tag.needs_review is False

    def test_confidence_range(self):
        # 超出范围应该报错
        with pytest.raises(Exception):
            ContentTag(tag_type="domain", value="test", confidence=1.5)
