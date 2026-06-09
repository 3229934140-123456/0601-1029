"""工具函数"""

import hashlib
import csv
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import FileType, CollectionFile, ErrorRecord


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'}
TEXT_EXTENSIONS = {'.txt', '.md', '.doc', '.docx', '.rtf'}


def detect_file_type(file_path: Path) -> FileType:
    """检测文件类型"""
    ext = file_path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    elif ext in AUDIO_EXTENSIONS:
        return FileType.AUDIO
    elif ext in TEXT_EXTENSIONS:
        return FileType.TEXT
    return FileType.UNKNOWN


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """计算文件的SHA256哈希值"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_file_size(file_path: Path) -> int:
    """获取文件大小（字节）"""
    return file_path.stat().st_size


def extract_collection_id(filename: str) -> Optional[str]:
    """从文件名中提取藏品编号
    
    支持的格式：
    - COL001, COL-001, COL_001
    - 2024-001, 2024_001
    - 纯数字编号如 001, 123
    """
    name = Path(filename).stem
    
    patterns = [
        r'([A-Z]{2,4}[-_]?\d{3,6})',
        r'(\d{4}[-_]\d{3,6})',
        r'(\d{3,6})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace('_', '-')
    
    return None


def create_collection_file(file_path: Path, compute_hash: bool = True) -> CollectionFile:
    """创建CollectionFile对象"""
    file_type = detect_file_type(file_path)
    size = get_file_size(file_path)
    collection_id = extract_collection_id(file_path.name)
    file_hash = compute_file_hash(file_path) if compute_hash else None
    
    return CollectionFile(
        path=file_path,
        file_type=file_type,
        file_hash=file_hash,
        size_bytes=size,
        collection_id=collection_id,
        original_name=file_path.name,
    )


def scan_directory(directory: Path, recursive: bool = True) -> List[Path]:
    """扫描目录中的所有文件"""
    if not directory.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")
    
    files = []
    pattern = '**/*' if recursive else '*'
    
    for file_path in directory.glob(pattern):
        if file_path.is_file():
            files.append(file_path)
    
    return files


def save_error_records(records: List[ErrorRecord], output_path: Path) -> None:
    """保存错误记录到CSV文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['file_path', 'error_type', 'message', 'resolved'])
        for record in records:
            writer.writerow([record.file_path, record.error_type, record.message, record.resolved])


def load_error_records(input_path: Path) -> List[ErrorRecord]:
    """从CSV文件加载错误记录"""
    records = []
    
    with open(input_path, 'r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(ErrorRecord(
                file_path=row['file_path'],
                error_type=row['error_type'],
                message=row['message'],
                resolved=row.get('resolved', '').lower() == 'true',
            ))
    
    return records


def load_tags_from_csv(csv_path: Path, id_column: str = '藏品编号') -> Dict[str, Dict[str, str]]:
    """从CSV/Excel文件加载标签"""
    import pandas as pd
    
    suffix = csv_path.suffix.lower()
    if suffix in {'.xlsx', '.xls'}:
        df = pd.read_excel(csv_path)
    else:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    tags_dict: Dict[str, Dict[str, str]] = {}
    
    for _, row in df.iterrows():
        if id_column in df.columns:
            item_id = str(row[id_column]).strip()
            tags = {}
            for col in df.columns:
                if col != id_column and pd.notna(row[col]):
                    tags[col] = str(row[col]).strip()
            if item_id:
                tags_dict[item_id] = tags
    
    return tags_dict


def save_json(data: Any, output_path: Path) -> None:
    """保存JSON数据"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(input_path: Path) -> Any:
    """加载JSON数据"""
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def validate_naming_pattern(filename: str, pattern: Optional[str] = None) -> bool:
    """验证文件名是否符合命名规则
    
    默认规则：藏品编号_类型描述.扩展名
    例如：COL001_正面照片.jpg, COL001_讲解音频.mp3, COL001_文物说明.txt
    """
    if pattern:
        return bool(re.match(pattern, filename))
    
    stem = Path(filename).stem
    default_pattern = r'^[A-Z0-9\-]{3,20}_.+$'
    return bool(re.match(default_pattern, stem))
