"""pytest 配置

解决 PYTHONPATH 污染问题：
当 hermes-agent 的 venv 路径在 PYTHONPATH 中时，
会优先加载旧版 pydantic_core，导致版本不兼容。
此 conftest.py 在测试收集前清理 sys.path。
"""
import sys

# 清理 hermes-agent 路径，避免 pydantic_core 版本冲突
sys.path = [p for p in sys.path if "hermes" not in p]
