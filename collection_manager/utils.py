"""工具函数"""

import hashlib
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple

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
    - TMP-A1, EXH-2024-001 (多段带字母和数字)
    - 纯数字编号如 001, 123
    """
    name = Path(filename).stem
    
    patterns = [
        r'([A-Z]{2,6}(?:[-_][A-Z0-9]+)+)',
        r'([A-Z]{2,4}[-_]?\d{1,6})',
        r'(\d{4}[-_]\d{1,6})',
        r'(\d{2,6})',
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


def scan_directory(directory: Path, recursive: bool = True, exclude_internal: bool = True) -> List[Path]:
    """扫描目录中的所有文件
    
    Args:
        directory: 要扫描的目录
        recursive: 是否递归子目录
        exclude_internal: 是否排除工具内部文件（如 .collection_tags.json、.collection_tags_history.json）
    """
    if not directory.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")
    
    files = []
    pattern = '**/*' if recursive else '*'
    internal_names = INTERNAL_FILENAMES if exclude_internal else set()
    
    for file_path in directory.glob(pattern):
        if file_path.is_file() and file_path.name not in internal_names:
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


TAGS_FILENAME = '.collection_tags.json'
MANIFEST_SCHEMA_VERSION = '1.0'


def save_tags_manifest(tags_dict: Dict[str, Dict[str, str]], target: Path,
                       source: Optional[str] = None) -> Path:
    """保存标签清单到指定路径
    
    Args:
        tags_dict: 标签数据 {藏品编号: {字段名: 字段值}}
        target: 输出文件路径（或目录路径，目录下会自动用 .collection_tags.json）
        source: 原始标签来源说明（如原始CSV路径）
    """
    if target.is_dir():
        manifest_path = target / TAGS_FILENAME
    else:
        manifest_path = target
    
    data = {
        'schema_version': MANIFEST_SCHEMA_VERSION,
        'generated_at': datetime.now().isoformat(),
        'source': source or '',
        'tag_count': len(tags_dict),
        'tags': tags_dict,
    }
    save_json(data, manifest_path)
    return manifest_path


def load_tags_manifest(source: Path) -> Optional[Dict[str, Dict[str, str]]]:
    """从标签清单文件或目录加载
    
    Args:
        source: 可以是清单文件路径，或包含 .collection_tags.json 的目录
    """
    if source.is_dir():
        manifest_path = source / TAGS_FILENAME
    else:
        manifest_path = source
    
    if manifest_path.exists():
        try:
            data = load_json(manifest_path)
            return data.get('tags', {})
        except Exception:
            return None
    return None


def get_manifest_metadata(source: Path) -> Optional[dict]:
    """获取标签清单的元数据（来源、生成时间等）"""
    if source.is_dir():
        manifest_path = source / TAGS_FILENAME
    else:
        manifest_path = source
    
    if manifest_path.exists():
        try:
            data = load_json(manifest_path)
            return {
                'path': str(manifest_path),
                'generated_at': data.get('generated_at', ''),
                'source': data.get('source', ''),
                'tag_count': data.get('tag_count', len(data.get('tags', {}))),
            }
        except Exception:
            return None
    return None


def find_tags_source(directory: Path,
                     explicit_file: Optional[Path] = None,
                     manifest_file: Optional[Path] = None,
                     id_column: str = '藏品编号') -> Optional[Dict[str, Dict[str, str]]]:
    """查找并加载标签数据
    
    优先级：manifest_file > explicit_file(CSV/Excel) > 目录下 .collection_tags.json > 同目录CSV/Excel
    """
    if manifest_file:
        return load_tags_manifest(manifest_file)
    
    if explicit_file:
        return load_tags_from_csv(explicit_file, id_column)
    
    manifest_tags = load_tags_manifest(directory)
    if manifest_tags:
        return manifest_tags
    
    for candidate in directory.glob('*.csv'):
        if candidate.name.startswith('.'):
            continue
        try:
            return load_tags_from_csv(candidate, id_column)
        except Exception:
            continue
    for candidate in directory.glob('*.xlsx'):
        try:
            return load_tags_from_csv(candidate, id_column)
        except Exception:
            continue
    for candidate in directory.parent.glob('*.csv'):
        if candidate.name.startswith('.'):
            continue
        try:
            return load_tags_from_csv(candidate, id_column)
        except Exception:
            continue
    
    return None


def resolve_manifest_source(directory: Path,
                            explicit_file: Optional[Path] = None,
                            manifest_file: Optional[Path] = None) -> str:
    """获取标签来源描述字符串"""
    if manifest_file:
        meta = get_manifest_metadata(manifest_file)
        if meta:
            extra = f"（原始来源: {meta['source']}）" if meta.get('source') else ''
            return f"清单文件: {manifest_file}{extra}"
        return f"清单文件: {manifest_file}"
    if explicit_file:
        return f"表格文件: {explicit_file}"
    meta = get_manifest_metadata(directory)
    if meta:
        extra = f"（原始来源: {meta['source']}）" if meta.get('source') else ''
        return f"自动发现（{TAGS_FILENAME}）{extra}"
    return "未找到标签数据"


TAGS_HISTORY_FILENAME = '.collection_tags_history.json'

INTERNAL_FILENAMES = {TAGS_FILENAME, TAGS_HISTORY_FILENAME}


def append_tags_history(directory: Path, manifest_path: Path, tags_dict: Dict[str, Dict[str, str]],
                        source: Optional[str] = None) -> Path:
    """追加标签导入历史摘要
    
    每次 tag --apply 把本次清单的摘要写入目录下的 .collection_tags_history.json
    """
    history_path = directory / TAGS_HISTORY_FILENAME
    history: List[dict] = []
    if history_path.exists():
        try:
            history = load_json(history_path) or []
        except Exception:
            history = []
    
    version = len(history) + 1
    entry = {
        'version': version,
        'generated_at': datetime.now().isoformat(),
        'manifest_path': str(manifest_path),
        'source': source or '',
        'tag_count': len(tags_dict),
        'sample_ids': sorted(list(tags_dict.keys()))[:10],
    }
    history.append(entry)
    save_json(history, history_path)
    return history_path


def get_tags_history(directory: Path) -> List[dict]:
    """读取标签导入历史摘要列表（按版本升序）"""
    history_path = directory / TAGS_HISTORY_FILENAME
    if not history_path.exists():
        return []
    try:
        return load_json(history_path) or []
    except Exception:
        return []


def find_missing_tag_ids(tags_dict: Dict[str, Dict[str, str]],
                         collection_ids_in_dir: Set[str]) -> List[str]:
    """找出清单里有但素材目录里找不到的藏品编号"""
    return sorted([cid for cid in tags_dict.keys() if cid not in collection_ids_in_dir])


def write_handover_csv(output_path: Path, group_name: str,
                       items: Dict[str, 'CollectionItem'],
                       tag_fields: List[str]) -> Path:
    """为单个主题生成交接清单 CSV
    
    每行一个藏品，列出图片/音频/说明三类文件是否存在、文件名、大小，以及标签字段
    """
    from .models import FileType as _FT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = ['藏品编号', '是否完整', '缺失文件']
    for ftype in ('image', 'audio', 'text'):
        header.extend([
            f'{ftype}_存在',
            f'{ftype}_文件名',
            f'{ftype}_大小(字节)',
            f'{ftype}_大小(可读)',
        ])
    header.extend(tag_fields)
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for cid in sorted(items.keys()):
            item = items[cid]
            row = [cid, '是' if item.is_complete else '否', ', '.join(item.missing_files)]
            for ftype, attr in (('image', 'image_file'), ('audio', 'audio_file'), ('text', 'text_file')):
                cf = getattr(item, attr, None)
                if cf:
                    size = cf.path.stat().st_size if cf.path.exists() else 0
                    row.extend(['是', cf.path.name, size, format_size(size)])
                else:
                    row.extend(['否', '', '', ''])
            for field in tag_fields:
                row.append(item.tags.get(field, ''))
            writer.writerow(row)
    return output_path
