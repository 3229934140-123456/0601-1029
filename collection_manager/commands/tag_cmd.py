"""tag 命令 - 从表格导入年代、类别、作者标签，生成待补充清单"""

import click
import csv
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..models import ErrorRecord
from ..utils import (
    scan_directory,
    create_collection_file,
    load_tags_from_csv,
    extract_collection_id,
    save_error_records,
    save_tags_manifest,
    load_tags_manifest,
)


def find_missing_tags(
    collection_ids: Set[str],
    tags_dict: Dict[str, Dict[str, str]],
    required_fields: List[str],
) -> Dict[str, List[str]]:
    """查找缺失的标签字段"""
    missing: Dict[str, List[str]] = {}
    
    for cid in collection_ids:
        tags = tags_dict.get(cid, {})
        missing_fields = []
        for field in required_fields:
            if field not in tags or not tags[field]:
                missing_fields.append(field)
        if missing_fields:
            missing[cid] = missing_fields
    
    return missing


def find_untagged_files(
    files: List[Path],
    tags_dict: Dict[str, Dict[str, str]],
) -> List[str]:
    """查找没有标签信息的文件"""
    untagged = []
    
    for file_path in files:
        try:
            cid = extract_collection_id(file_path.name)
            if cid and cid not in tags_dict:
                untagged.append(str(file_path))
        except Exception:
            pass
    
    return untagged


@click.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('tags_file', type=click.Path(exists=True, dir_okay=False, path_type=Path), required=False)
@click.option('--id-column', default='藏品编号', help='编号列名')
@click.option('--required-fields', default='年代,类别,作者', help='必填字段，逗号分隔')
@click.option('--output', '-o', type=click.Path(path_type=Path), help='输出待补充清单')
@click.option('--apply', is_flag=True, help='导入标签并生成可复用的 .collection_tags.json 到素材目录')
@click.option('--manifest-output', type=click.Path(path_type=Path), help='指定标签清单输出位置（默认写到素材目录）')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误记录输出路径')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息')
def tag(directory: Path, tags_file: Optional[Path], id_column: str, required_fields: str,
        output: Path, apply: bool, manifest_output: Optional[Path], error_log: Path, verbose: bool):
    """从表格导入年代、类别、作者标签，生成待补充清单
    
    标签文件支持 CSV 和 Excel。使用 --apply 会在素材目录生成 .collection_tags.json，
    后续的 pack、check 等命令可自动读取，无需重复指定原始表格。
    """
    files = scan_directory(directory)
    click.echo(f"扫描到 {len(files)} 个文件")
    
    collection_ids: Set[str] = set()
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=False)
            if cf.collection_id:
                collection_ids.add(cf.collection_id)
        except Exception:
            pass
    
    click.echo(f"识别到 {len(collection_ids)} 个藏品编号")
    
    tags_dict: Dict[str, Dict[str, str]] = {}
    if tags_file:
        try:
            tags_dict = load_tags_from_csv(tags_file, id_column)
            click.echo(f"🏷️  从 {tags_file} 加载了 {len(tags_dict)} 条标签记录")
        except Exception as e:
            click.echo(f"❌ 读取标签文件失败: {e}")
            return
    else:
        existing = load_tags_manifest(directory)
        if existing:
            tags_dict = existing
            click.echo(f"📂 从现有标签清单加载了 {len(tags_dict)} 条记录")
        else:
            click.echo("❌ 未指定标签文件，且素材目录下也没有 .collection_tags.json")
            return
    
    required = [f.strip() for f in required_fields.split(',') if f.strip()]
    click.echo(f"必填字段: {', '.join(required)}")
    
    missing_tags = find_missing_tags(collection_ids, tags_dict, required)
    untagged_files = find_untagged_files(files, tags_dict)
    
    click.echo("=" * 60)
    click.echo("标签导入结果")
    click.echo("=" * 60)
    
    tagged_count = len(collection_ids) - len(missing_tags)
    click.echo(f"\n✅ 标签完整的藏品: {tagged_count}/{len(collection_ids)}")
    
    if missing_tags:
        click.echo(f"\n❌ 缺失标签的藏品: {len(missing_tags)} 个")
        for cid, fields in missing_tags.items():
            click.echo(f"  {cid}: 缺少 {', '.join(fields)}")
    
    if untagged_files:
        click.echo(f"\n⚠️  表格中无对应标签的文件: {len(untagged_files)} 个")
        if verbose:
            for f in untagged_files:
                click.echo(f"  - {f}")
    
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['藏品编号'] + required + ['备注'])
            
            for cid in sorted(collection_ids):
                tags = tags_dict.get(cid, {})
                row = [cid]
                for field in required:
                    row.append(tags.get(field, ''))
                
                remarks = []
                if cid in missing_tags:
                    remarks.append(f"缺少: {', '.join(missing_tags[cid])}")
                if cid not in tags_dict:
                    remarks.append("表格中无记录")
                
                row.append('; '.join(remarks))
                writer.writerow(row)
            
            if untagged_files:
                writer.writerow([])
                writer.writerow(['以下文件无对应标签记录'])
                for f in untagged_files:
                    writer.writerow([f])
        
        click.echo(f"\n💾 待补充清单已保存到: {output}")
    
    if apply:
        if manifest_output:
            manifest_output.parent.mkdir(parents=True, exist_ok=True)
            target = manifest_output
        else:
            target = directory
        source_info = str(tags_file) if tags_file else '目录现有标签'
        manifest_path = save_tags_manifest(tags_dict, target, source=source_info)
        click.echo(f"✅ 标签清单已写入: {manifest_path}")
        if manifest_output:
            click.echo(f"   后续可通过 --manifest-file {manifest_path} 给 pack/check 等命令直接复用")
        else:
            click.echo("   后续 pack 等命令可自动读取该清单，无需再指定原始表格。")
    
    if error_log:
        errors = []
        for cid, fields in missing_tags.items():
            errors.append(ErrorRecord(
                file_path=cid,
                error_type='missing_tag',
                message=f"缺少标签字段: {', '.join(fields)}",
            ))
        for f in untagged_files:
            errors.append(ErrorRecord(
                file_path=f,
                error_type='untagged_file',
                message='文件在标签表格中无对应记录',
            ))
        save_error_records(errors, error_log)
        click.echo(f"💾 错误记录已保存到: {error_log}")
    
    click.echo("\n" + "=" * 60)
