"""pack 命令 - 按展览主题打包素材，输出整理报告"""

import click
import csv
import shutil
import zipfile
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from ..models import FileType, ErrorRecord, CollectionItem
from ..utils import (
    scan_directory,
    create_collection_file,
    load_tags_from_csv,
    format_size,
    save_error_records,
    find_tags_source,
    TAGS_FILENAME,
)


def group_by_tag(
    files: List[Path],
    tags_dict: Dict[str, Dict[str, str]],
    group_by: str,
) -> Dict[str, List[Path]]:
    """按标签分组文件"""
    groups: Dict[str, List[Path]] = defaultdict(list)
    ungrouped: List[Path] = []
    
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=False)
            if cf.collection_id and cf.collection_id in tags_dict:
                tag_value = tags_dict[cf.collection_id].get(group_by, '')
                if tag_value:
                    groups[tag_value].append(file_path)
                else:
                    ungrouped.append(file_path)
            else:
                ungrouped.append(file_path)
        except Exception:
            ungrouped.append(file_path)
    
    if ungrouped:
        groups['未分类'] = ungrouped
    
    return dict(groups)


def build_collection_items(files: List[Path], tags_dict: Dict[str, Dict[str, str]]) -> Dict[str, CollectionItem]:
    """构建藏品条目"""
    items: Dict[str, CollectionItem] = {}
    
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=False)
            if not cf.collection_id:
                continue
            
            if cf.collection_id not in items:
                tags = tags_dict.get(cf.collection_id, {})
                items[cf.collection_id] = CollectionItem(
                    collection_id=cf.collection_id,
                    tags=tags,
                )
            
            item = items[cf.collection_id]
            if cf.file_type == FileType.IMAGE:
                item.image_file = cf
            elif cf.file_type == FileType.AUDIO:
                item.audio_file = cf
            elif cf.file_type == FileType.TEXT:
                item.text_file = cf
        except Exception:
            pass
    
    return items


def create_report(
    items: Dict[str, CollectionItem],
    groups: Dict[str, List[Path]],
    directory: Path,
) -> dict:
    """生成整理报告"""
    total_size = sum(f.stat().st_size for f in scan_directory(directory))
    complete_count = sum(1 for item in items.values() if item.is_complete)
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'source_directory': str(directory),
        'statistics': {
            'total_collections': len(items),
            'complete_collections': complete_count,
            'incomplete_collections': len(items) - complete_count,
            'total_size_bytes': total_size,
            'total_size_human': format_size(total_size),
        },
        'groups': {},
        'collections': {},
    }
    
    for group_name, group_files in groups.items():
        group_size = sum(f.stat().st_size for f in group_files)
        report['groups'][group_name] = {
            'file_count': len(group_files),
            'size_bytes': group_size,
            'size_human': format_size(group_size),
            'files': [str(f) for f in group_files],
        }
    
    for cid, item in items.items():
        report['collections'][cid] = {
            'is_complete': item.is_complete,
            'missing_files': item.missing_files,
            'tags': item.tags,
            'files': {
                'image': str(item.image_file.path) if item.image_file else None,
                'audio': str(item.audio_file.path) if item.audio_file else None,
                'text': str(item.text_file.path) if item.text_file else None,
            },
        }
    
    return report


@click.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--output-dir', '-o', type=click.Path(path_type=Path), default=None,
              help='输出目录，默认为源目录同级的 collection_pack')
@click.option('--tags-file', type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='标签文件（CSV/Excel），用于按标签分组')
@click.option('--group-by', default='展览主题', help='按哪个标签字段分组')
@click.option('--format', 'pack_format', type=click.Choice(['copy', 'zip']), default='copy',
              help='打包方式：copy-复制到文件夹，zip-压缩为zip')
@click.option('--id-column', default='藏品编号', help='标签文件中的编号列名')
@click.option('--no-report', is_flag=True, help='不生成整理报告')
@click.option('--apply', is_flag=True, help='实际执行打包（默认仅预览）')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误记录输出路径')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息')
def pack(directory: Path, output_dir: Optional[Path], tags_file: Optional[Path],
         group_by: str, pack_format: str, id_column: str, no_report: bool,
         apply: bool, error_log: Path, verbose: bool):
    """按展览主题打包素材，输出整理报告"""
    click.echo(f"📦 准备打包目录: {directory}")
    
    if output_dir is None:
        output_dir = directory.parent / f"{directory.name}_packed"
    
    files = scan_directory(directory)
    click.echo(f"扫描到 {len(files)} 个文件")
    
    tags_dict: Dict[str, Dict[str, str]] = {}
    try:
        tags_dict = find_tags_source(directory, tags_file, id_column) or {}
        if tags_dict:
            source = str(tags_file) if tags_file else f"自动发现（{TAGS_FILENAME} 或同目录表格）"
            click.echo(f"📋 加载了 {len(tags_dict)} 条标签记录（来源: {source}）")
        else:
            click.echo("⚠️  未找到标签信息，将作为单组打包")
    except Exception as e:
        click.echo(f"⚠️  读取标签失败: {e}")
    
    items = build_collection_items(files, tags_dict)
    groups = group_by_tag(files, tags_dict, group_by) if tags_dict else {'全部': files}
    
    click.echo("=" * 60)
    click.echo("打包预览")
    click.echo("=" * 60)
    
    click.echo(f"\n📂 将输出到: {output_dir}")
    click.echo(f"📦 打包方式: {pack_format}")
    click.echo(f"🗂️  分组数量: {len(groups)}")
    
    for group_name, group_files in sorted(groups.items()):
        group_size = sum(f.stat().st_size for f in group_files)
        click.echo(f"\n  📁 {group_name}: {len(group_files)} 个文件, {format_size(group_size)}")
        if verbose:
            for f in group_files:
                click.echo(f"    - {f.name}")
    
    complete_count = sum(1 for item in items.values() if item.is_complete)
    click.echo(f"\n✅ 完整藏品: {complete_count}/{len(items)}")
    
    if not apply:
        click.echo("\n⚠️  预览模式，未实际执行。使用 --apply 参数执行打包。")
    else:
        if not click.confirm(f"\n确认要打包到 {output_dir} 吗？"):
            click.echo("已取消")
            return
        
        errors = []
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for group_name, group_files in groups.items():
            safe_group_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_group_name:
                safe_group_name = '未命名'
            
            if pack_format == 'zip':
                zip_path = output_dir / f"{safe_group_name}.zip"
                click.echo(f"\n📦 正在压缩: {zip_path.name}")
                try:
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for f in group_files:
                            arcname = f.name
                            zf.write(f, arcname)
                    click.echo(f"  ✅ 完成: {format_size(zip_path.stat().st_size)}")
                except Exception as e:
                    errors.append(ErrorRecord(
                        file_path=group_name,
                        error_type='zip_error',
                        message=str(e),
                    ))
                    click.echo(f"  ❌ 失败: {e}")
            else:
                group_dir = output_dir / safe_group_name
                group_dir.mkdir(parents=True, exist_ok=True)
                click.echo(f"\n📁 正在复制到: {group_dir.name}/")
                for f in group_files:
                    try:
                        dest = group_dir / f.name
                        if dest.exists():
                            stem = dest.stem
                            suffix = dest.suffix
                            counter = 1
                            while dest.exists():
                                dest = group_dir / f"{stem}_{counter}{suffix}"
                                counter += 1
                        shutil.copy2(f, dest)
                    except Exception as e:
                        errors.append(ErrorRecord(
                            file_path=str(f),
                            error_type='copy_error',
                            message=str(e),
                        ))
                click.echo(f"  ✅ 复制了 {len(group_files)} 个文件")
        
        if not no_report:
            report = create_report(items, groups, directory)
            report_path = output_dir / '整理报告.json'
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            click.echo(f"\n📄 整理报告已保存: {report_path}")
            
            csv_path = output_dir / '整理报告.csv'
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['藏品编号', '是否完整', '缺失文件', '图片', '音频', '文本', '标签'])
                for cid, item in sorted(items.items()):
                    writer.writerow([
                        cid,
                        '是' if item.is_complete else '否',
                        ', '.join(item.missing_files),
                        str(item.image_file.path) if item.image_file else '',
                        str(item.audio_file.path) if item.audio_file else '',
                        str(item.text_file.path) if item.text_file else '',
                        json.dumps(item.tags, ensure_ascii=False),
                    ])
            click.echo(f"📄 整理清单已保存: {csv_path}")
        
        click.echo(f"\n✅ 打包完成，输出目录: {output_dir}")
        
        if errors and error_log:
            save_error_records(errors, error_log)
            click.echo(f"💾 错误记录已保存到: {error_log}")
    
    click.echo("\n" + "=" * 60)
