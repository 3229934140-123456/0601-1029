"""rename 命令 - 按藏品编号统一重命名"""

import click
import csv
from pathlib import Path
from typing import List, Optional

from ..models import RenamePlan, FileType, ErrorRecord
from ..utils import (
    scan_directory,
    create_collection_file,
    save_error_records,
)


def generate_new_name(collection_id: str, file_type: FileType, suffix: str, description: str = '') -> str:
    """生成新文件名
    
    格式: {藏品编号}_{类型描述}{扩展名}
    例如: COL001_正面图片.jpg, COL001_讲解音频.mp3, COL001_文物说明.txt
    """
    type_descriptions = {
        FileType.IMAGE: '图片',
        FileType.AUDIO: '音频',
        FileType.TEXT: '说明',
    }
    
    type_desc = description or type_descriptions.get(file_type, '文件')
    return f"{collection_id}_{type_desc}{suffix}"


def build_rename_plans(
    files: List[Path],
    prefix: str = '',
    description_map: Optional[dict] = None,
) -> List[RenamePlan]:
    """构建重命名计划"""
    plans: List[RenamePlan] = []
    used_names = set()
    
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=False)
            
            if not cf.collection_id:
                continue
            
            new_collection_id = prefix + cf.collection_id if prefix else cf.collection_id
            
            desc = ''
            if description_map and cf.collection_id in description_map:
                type_desc = description_map[cf.collection_id].get(cf.file_type.value, '')
                if type_desc:
                    desc = type_desc
            
            new_name = generate_new_name(
                new_collection_id, cf.file_type, cf.path.suffix.lower(), desc)
            new_path = file_path.parent / new_name
            
            if new_path == file_path:
                continue
            
            counter = 1
            base_new_path = new_path
            while str(new_path) in used_names or (new_path.exists() and new_path != file_path):
                stem = base_new_path.stem
                suffix = base_new_path.suffix
                new_path = file_path.parent / f"{stem}_{counter}{suffix}"
                counter += 1
            
            used_names.add(str(new_path))
            
            reason = f"按编号 {new_collection_id} 统一命名"
            plans.append(RenamePlan(
                original_path=file_path,
                new_path=new_path,
                reason=reason,
            ))
            
        except Exception:
            pass
    
    return plans


def print_rename_plans(plans: List[RenamePlan]) -> None:
    """打印重命名计划"""
    click.echo("=" * 80)
    click.echo(f"重命名预览（共 {len(plans)} 个文件）")
    click.echo("=" * 80)
    
    for i, plan in enumerate(plans, 1):
        click.echo(f"\n{i}. {plan.original_path.name}")
        click.echo(f"   ↓")
        click.echo(f"   {plan.new_path.name}")
        click.echo(f"   原因: {plan.reason}")
    
    click.echo("\n" + "=" * 80)


@click.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--prefix', default='', help='藏品编号前缀（如 COL-')
@click.option('--id-map', type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='编号映射表 CSV 文件（旧编号,新编号,图片描述,音频描述,文本描述）')
@click.option('--apply', is_flag=True, help='实际执行重命名（默认仅预览')
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='保存重命名计划到 CSV')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误记录输出路径')
def rename(directory: Path, prefix: str, id_map: Path, apply: bool, output: Path, error_log: Path):
    """按藏品编号统一重命名文件"""
    click.echo(f"📝 准备重命名目录: {directory}")
    
    files = scan_directory(directory)
    click.echo(f"找到 {len(files)} 个文件")
    
    description_map = {}
    if id_map:
        with open(id_map, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                old_id = row.get('旧编号', row.get('old_id', '')).strip()
                if old_id:
                    description_map[old_id] = {
                        'image': row.get('图片描述', row.get('image_desc', '')),
                        'audio': row.get('音频描述', row.get('audio_desc', '')),
                        'text': row.get('文本描述', row.get('text_desc', '')),
                    }
                    new_id = row.get('新编号', row.get('new_id', '')).strip()
                    if new_id:
                        pass
    
    plans = build_rename_plans(files, prefix=prefix, description_map=description_map)
    
    if not plans:
        click.echo("✅ 没有需要重命名的文件")
        return
    
    print_rename_plans(plans)
    
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['original_path', 'new_path', 'reason'])
            for plan in plans:
                writer.writerow([str(plan.original_path), str(plan.new_path), plan.reason])
        click.echo(f"\n💾 重命名计划已保存到: {output}")
    
    if not apply:
        click.echo("\n⚠️  预览模式，未实际修改文件。使用 --apply 参数执行重命名。")
        return
    
    if not click.confirm(f"\n确认要重命名以上 {len(plans)} 个文件吗？"):
        click.echo("已取消")
        return
    
    errors = []
    success_count = 0
    
    for plan in plans:
        try:
            plan.new_path.parent.mkdir(parents=True, exist_ok=True)
            plan.original_path.rename(plan.new_path)
            success_count += 1
            click.echo(f"✅ {plan.original_path.name} -> {plan.new_path.name}")
        except Exception as e:
            errors.append(ErrorRecord(
                file_path=str(plan.original_path),
                error_type='rename_error',
                message=str(e),
            ))
            click.echo(f"❌ {plan.original_path.name}: {e}")
    
    click.echo(f"\n完成：成功 {success_count}/{len(plans)} 个文件")
    
    if errors and error_log:
        save_error_records(errors, error_log)
        click.echo(f"💾 错误记录已保存到: {error_log}")
