"""scan 命令 - 扫描文件夹，识别重复文件和缺失说明"""

import click
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

from ..models import ScanReport, CollectionFile, CollectionItem, FileType, ErrorRecord
from ..utils import (
    scan_directory,
    create_collection_file,
    save_error_records,
    format_size,
)


def build_scan_report(files: List[Path], compute_hash: bool = True) -> ScanReport:
    """构建扫描报告"""
    report = ScanReport()
    
    collection_files: List[CollectionFile] = []
    
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=compute_hash)
            collection_files.append(cf)
            
            report.total_files += 1
            if cf.file_type == FileType.IMAGE:
                report.image_count += 1
            elif cf.file_type == FileType.AUDIO:
                report.audio_count += 1
            elif cf.file_type == FileType.TEXT:
                report.text_count += 1
            
            if cf.collection_id:
                if cf.collection_id not in report.collection_items:
                    report.collection_items[cf.collection_id] = CollectionItem(
                        collection_id=cf.collection_id
                    )
                item = report.collection_items[cf.collection_id]
                
                if cf.file_type == FileType.IMAGE:
                    item.image_file = cf
                elif cf.file_type == FileType.AUDIO:
                    item.audio_file = cf
                elif cf.file_type == FileType.TEXT:
                    item.text_file = cf
            else:
                report.unidentified_files.append(cf)
                
        except Exception as e:
            error_rec = ErrorRecord(
                file_path=str(file_path),
                error_type='scan_error',
                message=str(e),
            )
            report.unidentified_files.append(
                CollectionFile(path=file_path, file_type=FileType.UNKNOWN)
            )
    
    if compute_hash:
        hash_map: Dict[str, List[CollectionFile]] = defaultdict(list)
        for cf in collection_files:
            if cf.file_hash:
                hash_map[cf.file_hash].append(cf)
        
        for h, cfs in hash_map.items():
            if len(cfs) > 1:
                report.duplicate_files.append(cfs)
    
    for cid, item in report.collection_items.items():
        missing = item.missing_files
        if missing:
            report.missing_files[cid] = missing
    
    return report


def print_scan_report(report: ScanReport, verbose: bool = False) -> None:
    """打印扫描报告"""
    click.echo("=" * 60)
    click.echo("扫描报告")
    click.echo("=" * 60)
    
    click.echo(f"\n📊 文件统计:")
    click.echo(f"  总文件数: {report.total_files}")
    click.echo(f"  图片文件: {report.image_count}")
    click.echo(f"  音频文件: {report.audio_count}")
    click.echo(f"  文本文件: {report.text_count}")
    click.echo(f"  识别藏品数: {len(report.collection_items)}")
    
    if report.duplicate_files:
        click.echo(f"\n⚠️  发现重复文件: {len(report.duplicate_files)} 组")
        for i, group in enumerate(report.duplicate_files, 1):
            click.echo(f"  重复组 {i}:")
            for cf in group:
                click.echo(f"    - {cf.path} ({format_size(cf.size_bytes)})")
    
    if report.missing_files:
        click.echo(f"\n❌ 缺失文件的藏品: {len(report.missing_files)} 个")
        for cid, missing in report.missing_files.items():
            missing_str = '、'.join(missing)
            click.echo(f"  {cid}: 缺少 {missing_str}")
    
    if report.unidentified_files:
        click.echo(f"\n🔍 未识别藏品编号的文件: {len(report.unidentified_files)} 个")
        if verbose:
            for cf in report.unidentified_files:
                click.echo(f"  - {cf.path}")
    
    complete_count = sum(1 for item in report.collection_items.values() if item.is_complete)
    click.echo(f"\n✅ 完整藏品（图片+音频+文本）: {complete_count}/{len(report.collection_items)}")
    
    click.echo("\n" + "=" * 60)


@click.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--no-recursive', is_flag=True, help='不递归扫描子目录')
@click.option('--no-hash', is_flag=True, help='不计算文件哈希（加快扫描，跳过重复检测）')
@click.option('--output', '-o', type=click.Path(path_type=Path), help='输出报告文件路径（JSON）')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误记录输出路径（CSV）')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息')
def scan(directory: Path, no_recursive: bool, no_hash: bool, output: Path, error_log: Path, verbose: bool):
    """扫描指定文件夹，识别重复文件和缺失说明"""
    click.echo(f"🔍 正在扫描目录: {directory}")
    
    files = scan_directory(directory, recursive=not no_recursive)
    click.echo(f"找到 {len(files)} 个文件，正在分析...")
    
    report = build_scan_report(files, compute_hash=not no_hash)
    print_scan_report(report, verbose)
    
    if output:
        report_data = {
            'total_files': report.total_files,
            'image_count': report.image_count,
            'audio_count': report.audio_count,
            'text_count': report.text_count,
            'collection_count': len(report.collection_items),
            'duplicate_groups': [
                [str(cf.path) for cf in group]
                for group in report.duplicate_files
            ],
            'missing_files': report.missing_files,
            'unidentified_files': [str(cf.path) for cf in report.unidentified_files],
            'complete_items': [
                cid for cid, item in report.collection_items.items() if item.is_complete
            ],
        }
        from ..utils import save_json
        save_json(report_data, output)
        click.echo(f"\n💾 报告已保存到: {output}")
    
    if error_log:
        errors = []
        for cf in report.unidentified_files:
            if cf.file_type != FileType.UNKNOWN:
                errors.append(ErrorRecord(
                    file_path=str(cf.path),
                    error_type='unidentified_id',
                    message='无法从文件名提取藏品编号',
                ))
        for group in report.duplicate_files:
            for cf in group[1:]:
                errors.append(ErrorRecord(
                    file_path=str(cf.path),
                    error_type='duplicate_file',
                    message=f'与 {group[0].path} 内容重复',
                ))
        for cid, missing in report.missing_files.items():
            for m in missing:
                errors.append(ErrorRecord(
                    file_path=cid,
                    error_type=f'missing_{m}',
                    message=f'藏品 {cid} 缺少{m}文件',
                ))
        
        save_error_records(errors, error_log)
        click.echo(f"💾 错误记录已保存到: {error_log}")
