"""测试工具注册表"""
import json

import pytest

from tools.base import Tool
from tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "回显"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str = ""):
        return {"echo": text}


class BoomTool(Tool):
    name = "boom"
    description = "总是失败"

    def run(self, **kwargs):
        raise RuntimeError("炸了")


class StrTool(Tool):
    name = "str_tool"
    description = "返回字符串"

    def run(self, **kwargs):
        return "纯文本结果"


class TestToolRegistry:
    def test_register_and_names(self):
        registry = ToolRegistry([EchoTool()])
        assert registry.names() == ["echo"]
        assert registry.get("echo") is not None

    def test_schemas(self):
        registry = ToolRegistry([EchoTool()])
        schema = registry.schemas()[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "echo"
        assert "text" in schema["function"]["parameters"]["properties"]

    def test_execute_dict_serialized(self):
        registry = ToolRegistry([EchoTool()])
        output = registry.execute("echo", {"text": "hi"})
        assert json.loads(output) == {"echo": "hi"}

    def test_execute_str_passthrough(self):
        registry = ToolRegistry([StrTool()])
        assert registry.execute("str_tool", {}) == "纯文本结果"

    def test_execute_unknown_tool(self):
        registry = ToolRegistry([EchoTool()])
        output = json.loads(registry.execute("nope", {}))
        assert "error" in output
        assert output["available"] == ["echo"]

    def test_execute_bad_arguments(self):
        registry = ToolRegistry([EchoTool()])
        output = json.loads(registry.execute("echo", {"unexpected": 1}))
        assert "error" in output

    def test_execute_exception_contained(self):
        registry = ToolRegistry([BoomTool()])
        output = json.loads(registry.execute("boom", {}))
        assert "炸了" in output["error"]

    def test_register_without_name_raises(self):
        class Nameless(Tool):
            def run(self, **kwargs):
                return ""

        with pytest.raises(ValueError):
            ToolRegistry([Nameless()])
