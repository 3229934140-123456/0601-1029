"""数据模型定义"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum


class FileType(Enum):
    """文件类型枚举"""
    IMAGE = 'image'
    AUDIO = 'audio'
    TEXT = 'text'
    UNKNOWN = 'unknown'


class CheckStatus(Enum):
    """检查状态"""
    PASS = 'pass'
    WARN = 'warn'
    FAIL = 'fail'


@dataclass
class CollectionFile:
    """藏品文件"""
    path: Path
    file_type: FileType
    file_hash: Optional[str] = None
    size_bytes: int = 0
    collection_id: Optional[str] = None
    original_name: str = ''
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def extension(self) -> str:
        return self.path.suffix.lower().lstrip('.')

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)


@dataclass
class CollectionItem:
    """藏品（包含多个关联文件）"""
    collection_id: str
    image_file: Optional[CollectionFile] = None
    audio_file: Optional[CollectionFile] = None
    text_file: Optional[CollectionFile] = None
    tags: Dict[str, str] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return all([self.image_file, self.audio_file, self.text_file])

    @property
    def missing_files(self) -> List[str]:
        missing = []
        if not self.image_file:
            missing.append('image')
        if not self.audio_file:
            missing.append('audio')
        if not self.text_file:
            missing.append('text')
        return missing


@dataclass
class CheckResult:
    """检查结果"""
    file: CollectionFile
    status: CheckStatus
    checks: Dict[str, Tuple[CheckStatus, str]] = field(default_factory=dict)

    @property
    def is_pass(self) -> bool:
        return self.status == CheckStatus.PASS

    @property
    def messages(self) -> List[str]:
        return [msg for _, msg in self.checks.values()]


@dataclass
class ScanReport:
    """扫描报告"""
    total_files: int = 0
    image_count: int = 0
    audio_count: int = 0
    text_count: int = 0
    duplicate_files: List[List[CollectionFile]] = field(default_factory=list)
    missing_files: Dict[str, List[str]] = field(default_factory=dict)
    collection_items: Dict[str, CollectionItem] = field(default_factory=dict)
    unidentified_files: List[CollectionFile] = field(default_factory=list)


@dataclass
class RenamePlan:
    """重命名计划"""
    original_path: Path
    new_path: Path
    reason: str = ''


@dataclass
class ErrorRecord:
    """错误记录"""
    file_path: str
    error_type: str
    message: str
    resolved: bool = False
