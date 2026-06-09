"""rename 命令 - 按藏品编号统一重命名"""

import click
import csv
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

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


def load_id_map(id_map_path: Path) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]], List[ErrorRecord]]:
    """从CSV加载编号映射
    
    返回: (旧编号->新编号映射, 旧编号->{image,audio,text}描述映射, 冲突/错误记录列表)
    """
    id_remap: Dict[str, str] = {}
    description_map: Dict[str, Dict[str, str]] = {}
    errors: List[ErrorRecord] = []
    
    seen_old_ids: Dict[str, List[str]] = defaultdict(list)
    
    with open(id_map_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            old_id = row.get('旧编号', row.get('old_id', '')).strip()
            if not old_id:
                continue
            
            new_id = row.get('新编号', row.get('new_id', '')).strip()
            
            seen_old_ids[old_id].append(new_id)
            if len(seen_old_ids[old_id]) > 1 and new_id and seen_old_ids[old_id][0] != new_id:
                errors.append(ErrorRecord(
                    file_path=old_id,
                    error_type='id_map_conflict',
                    message=f"同一旧编号 {old_id} 映射到多个新编号: {', '.join(filter(None, seen_old_ids[old_id]))}",
                ))
            
            if new_id:
                id_remap[old_id] = new_id
            
            img_desc = row.get('图片描述', row.get('image_desc', '')).strip()
            aud_desc = row.get('音频描述', row.get('audio_desc', '')).strip()
            txt_desc = row.get('文本描述', row.get('text_desc', '')).strip()
            
            description_map[old_id] = {
                'image': img_desc,
                'audio': aud_desc,
                'text': txt_desc,
            }
    
    return id_remap, description_map, errors


def check_descriptions(id_remap: Dict[str, str], description_map: Dict[str, Dict[str, str]]) -> List[ErrorRecord]:
    """检查描述字段是否缺失"""
    errors: List[ErrorRecord] = []
    
    for old_id in id_remap:
        descs = description_map.get(old_id, {})
        missing = [ftype for ftype, desc in descs.items() if not desc]
        if missing:
            type_names = {'image': '图片描述', 'audio': '音频描述', 'text': '文本描述'}
            errors.append(ErrorRecord(
                file_path=old_id,
                error_type='missing_description',
                message=f"编号 {old_id} 缺少描述字段: {', '.join(type_names[m] for m in missing)}（将使用默认描述）",
            ))
    
    return errors


def build_rename_plans(
    files: List[Path],
    prefix: str = '',
    id_remap: Optional[Dict[str, str]] = None,
    description_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Tuple[List[RenamePlan], List[ErrorRecord]]:
    """构建重命名计划
    
    返回: (重命名计划列表, 冲突/错误记录列表)
    """
    plans: List[RenamePlan] = []
    errors: List[ErrorRecord] = []
    
    target_to_sources: Dict[str, List[Path]] = defaultdict(list)
    
    temp_plans: List[Tuple[Path, Path, str]] = []
    
    for file_path in files:
        try:
            cf = create_collection_file(file_path, compute_hash=False)
            
            if not cf.collection_id:
                continue
            
            original_id = cf.collection_id
            
            final_id = original_id
            reason_parts = []
            
            if id_remap and original_id in id_remap:
                final_id = id_remap[original_id]
                reason_parts.append(f"{original_id}→{final_id}")
            
            if prefix:
                final_id = prefix + final_id
                reason_parts.append(f"加前缀{prefix}")
            
            desc = ''
            if description_map and original_id in description_map:
                type_key = cf.file_type.value
                type_desc = description_map[original_id].get(type_key, '')
                if type_desc:
                    desc = type_desc
                    reason_parts.append(f"使用描述: {type_desc}")
            
            if not reason_parts:
                reason_parts.append(f"按编号 {final_id} 统一命名")
            
            new_name = generate_new_name(
                final_id, cf.file_type, cf.path.suffix.lower(), desc)
            new_path = file_path.parent / new_name
            
            if new_path == file_path:
                continue
            
            temp_plans.append((file_path, new_path, '; '.join(reason_parts)))
            target_to_sources[str(new_path)].append(file_path)
            
        except Exception:
            pass
    
    for target_path, sources in target_to_sources.items():
        if len(sources) > 1:
            for src in sources:
                errors.append(ErrorRecord(
                    file_path=str(src),
                    error_type='name_collision',
                    message=f"多个文件将重命名为同一目标 {Path(target_path).name}: " +
                            ", ".join(s.name for s in sources),
                ))
    
    used_names = set()
    
    for file_path, new_path, reason in temp_plans:
        if len(target_to_sources[str(new_path)]) > 1:
            continue
        
        final_new_path = new_path
        counter = 1
        base_new_path = new_path
        while str(final_new_path) in used_names:
            stem = base_new_path.stem
            suffix = base_new_path.suffix
            final_new_path = file_path.parent / f"{stem}_{counter}{suffix}"
            counter += 1
        
        if final_new_path.exists() and final_new_path != file_path:
            errors.append(ErrorRecord(
                file_path=str(file_path),
                error_type='target_exists',
                message=f"目标文件已存在，将跳过以避免覆盖: {final_new_path.name}",
            ))
            continue
        
        used_names.add(str(final_new_path))
        
        plans.append(RenamePlan(
            original_path=file_path,
            new_path=final_new_path,
            reason=reason,
        ))
    
    return plans, errors


def print_rename_plans(plans: List[RenamePlan], warnings: List[ErrorRecord]) -> None:
    """打印重命名计划"""
    if warnings:
        click.echo("\n" + "=" * 80)
        click.echo(f"⚠️  冲突与警告（共 {len(warnings)} 条）")
        click.echo("=" * 80)
        for i, w in enumerate(warnings, 1):
            icon = '❌' if w.error_type in ('id_map_conflict', 'name_collision') else '⚠️'
            click.echo(f"\n{i}. {icon} [{w.error_type}]")
            click.echo(f"   文件/编号: {w.file_path}")
            click.echo(f"   {w.message}")
    
    click.echo("\n" + "=" * 80)
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
@click.option('--prefix', default='', help='藏品编号前缀（如 COL-）')
@click.option('--id-map', type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help='编号映射表 CSV 文件（列：旧编号,新编号,图片描述,音频描述,文本描述）')
@click.option('--apply', is_flag=True, help='实际执行重命名（默认仅预览）')
@click.option('--overwrite', is_flag=True, help='允许覆盖已存在的目标文件（默认不覆盖）')
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='保存重命名计划到 CSV')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误/冲突记录输出路径')
def rename(directory: Path, prefix: str, id_map: Optional[Path], apply: bool, overwrite: bool,
           output: Optional[Path], error_log: Optional[Path]):
    """按藏品编号统一重命名文件
    
    支持通过 --id-map 指定编号映射表，将旧编号批量替换为新编号，
    同时可为图片/音频/说明分别自定义类型描述文字。
    执行前会自动检查编号映射冲突、目标文件重名、描述缺失等问题。
    """
    click.echo(f"📝 准备重命名目录: {directory}")
    
    files = scan_directory(directory)
    click.echo(f"找到 {len(files)} 个文件")
    
    id_remap: Dict[str, str] = {}
    description_map: Dict[str, Dict[str, str]] = {}
    all_errors: List[ErrorRecord] = []
    
    if id_map:
        id_remap, description_map, map_errors = load_id_map(id_map)
        all_errors.extend(map_errors)
        if id_remap:
            click.echo(f"🔀 加载编号映射: {len(id_remap)} 条（如 "
                       + ", ".join(f"{k}→{v}" for k, v in list(id_remap.items())[:3])
                       + ("..." if len(id_remap) > 3 else "") + ")")
        if description_map:
            click.echo(f"📝 加载文件描述: {len(description_map)} 条")
            desc_errors = check_descriptions(id_remap, description_map)
            all_errors.extend(desc_errors)
    
    plans, plan_errors = build_rename_plans(
        files,
        prefix=prefix,
        id_remap=id_remap,
        description_map=description_map,
    )
    all_errors.extend(plan_errors)
    
    if not plans and not all_errors:
        click.echo("✅ 没有需要重命名的文件")
        return
    
    print_rename_plans(plans, all_errors)
    
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['original_path', 'new_path', 'reason'])
            for plan in plans:
                writer.writerow([str(plan.original_path), str(plan.new_path), plan.reason])
        click.echo(f"\n💾 重命名计划已保存到: {output}")
    
    if error_log and all_errors:
        error_log.parent.mkdir(parents=True, exist_ok=True)
        save_error_records(all_errors, error_log)
        click.echo(f"💾 冲突/错误记录已保存到: {error_log}")
    
    if not plans:
        click.echo("\n⚠️  没有可安全执行的重命名操作（请检查冲突与警告）。")
        return
    
    if not apply:
        click.echo("\n⚠️  预览模式，未实际修改文件。使用 --apply 参数执行重命名。")
        return
    
    fatal_conflicts = [e for e in all_errors if e.error_type in ('id_map_conflict', 'name_collision')]
    if fatal_conflicts and not overwrite:
        click.echo("\n❌ 检测到致命冲突（编号映射冲突/目标文件重名），"
                   "请先处理冲突或使用 --overwrite 强制执行。")
        return
    
    if not click.confirm(f"\n确认要重命名以上 {len(plans)} 个文件吗？"):
        click.echo("已取消")
        return
    
    errors = []
    success_count = 0
    
    for plan in plans:
        try:
            if plan.new_path.exists() and plan.new_path != plan.original_path and not overwrite:
                errors.append(ErrorRecord(
                    file_path=str(plan.original_path),
                    error_type='target_exists',
                    message=f"目标文件已存在，已跳过: {plan.new_path.name}",
                ))
                click.echo(f"⏭️  跳过 {plan.original_path.name}（目标已存在）")
                continue
            
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
    
    if errors:
        all_errors.extend(errors)
        if error_log:
            save_error_records(all_errors, error_log)
            click.echo(f"💾 错误记录已保存到: {error_log}")
    elif error_log and all_errors:
        save_error_records(all_errors, error_log)
