"""读取器基类"""
from abc import ABC, abstractmethod
from typing import Optional
from core.document import Document


class BaseReader(ABC):
    """文档读取器基类"""

    @abstractmethod
    def read(self, file_path: str) -> Document:
        """读取文档并返回 Document 对象"""
        ...

    @abstractmethod
    def read_paginated(self, file_path: str) -> list[dict]:
        """读取文档，保留分页信息"""
        ...
