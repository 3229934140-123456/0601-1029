"""check 命令 - 检查文件大小、格式和命名规则"""

import click
import csv
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from ..models import (
    CheckResult,
    CheckStatus,
    CollectionFile,
    FileType,
    ErrorRecord,
)
from ..utils import (
    scan_directory,
    create_collection_file,
    validate_naming_pattern,
    format_size,
    save_error_records,
    IMAGE_EXTENSIONS,
    AUDIO_EXTENSIONS,
    TEXT_EXTENSIONS,
)


DEFAULT_MAX_SIZE = {
    FileType.IMAGE: 50 * 1024 * 1024,
    FileType.AUDIO: 100 * 1024 * 1024,
    FileType.TEXT: 10 * 1024 * 1024,
}

DEFAULT_MIN_SIZE = {
    FileType.IMAGE: 10 * 1024,
    FileType.AUDIO: 100 * 1024,
    FileType.TEXT: 10,
}


def check_file_format(cf: CollectionFile) -> Tuple[CheckStatus, str]:
    """检查文件格式"""
    ext = cf.path.suffix.lower()
    
    if cf.file_type == FileType.IMAGE:
        if ext in IMAGE_EXTENSIONS:
            try:
                from PIL import Image
                with Image.open(cf.path) as img:
                    img.verify()
                return CheckStatus.PASS, f"有效图片格式: {ext.lstrip('.')}"
            except Exception as e:
                return CheckStatus.FAIL, f"图片文件损坏或无法读取: {e}"
        else:
            return CheckStatus.FAIL, f"不支持的图片格式: {ext}"
    
    elif cf.file_type == FileType.AUDIO:
        if ext in AUDIO_EXTENSIONS:
            try:
                return CheckStatus.PASS, f"音频格式: {ext.lstrip('.')}"
            except Exception as e:
                return CheckStatus.WARN, f"音频格式检查跳过: {e}"
        else:
            return CheckStatus.FAIL, f"不支持的音频格式: {ext}"
    
    elif cf.file_type == FileType.TEXT:
        if ext in TEXT_EXTENSIONS:
            try:
                if ext in {'.txt', '.md'}:
                    with open(cf.path, 'r', encoding='utf-8') as f:
                        f.read(1024)
                return CheckStatus.PASS, f"文本格式: {ext.lstrip('.')}"
            except UnicodeDecodeError:
                return CheckStatus.WARN, "文本编码可能不是UTF-8"
            except Exception as e:
                return CheckStatus.FAIL, f"文本文件读取失败: {e}"
        else:
            return CheckStatus.FAIL, f"不支持的文本格式: {ext}"
    
    return CheckStatus.FAIL, f"不支持的文件格式: {ext or '无扩展名'}（仅支持图片、音频、文本类文件）"


def check_file_size(cf: CollectionFile, max_size: Optional[int] = None, min_size: Optional[int] = None) -> Tuple[CheckStatus, str]:
    """检查文件大小"""
    size = cf.size_bytes
    
    file_max = max_size if max_size is not None else DEFAULT_MAX_SIZE.get(cf.file_type, 100 * 1024 * 1024)
    file_min = min_size if min_size is not None else DEFAULT_MIN_SIZE.get(cf.file_type, 0)
    
    if size > file_max:
        return CheckStatus.WARN, f"文件过大: {format_size(size)} (上限: {format_size(file_max)})"
    elif size < file_min:
        return CheckStatus.WARN, f"文件过小: {format_size(size)} (下限: {format_size(file_min)})"
    
    return CheckStatus.PASS, f"文件大小正常: {format_size(size)}"


def check_naming(cf: CollectionFile, pattern: Optional[str] = None) -> Tuple[CheckStatus, str]:
    """检查命名规则"""
    if not cf.collection_id:
        return CheckStatus.FAIL, "无法从文件名提取藏品编号"
    
    if validate_naming_pattern(cf.filename, pattern):
        return CheckStatus.PASS, f"命名符合规范 (编号: {cf.collection_id})"
    
    return CheckStatus.WARN, f"命名不符合规范，建议格式: {cf.collection_id}_类型描述.扩展名"


def run_checks(cf: CollectionFile, naming_pattern: Optional[str] = None,
               max_size: Optional[int] = None, min_size: Optional[int] = None) -> CheckResult:
    """对单个文件执行所有检查"""
    checks: Dict[str, Tuple[CheckStatus, str]] = {}
    
    checks['format'] = check_file_format(cf)
    checks['size'] = check_file_size(cf, max_size, min_size)
    checks['naming'] = check_naming(cf, naming_pattern)
    
    overall = CheckStatus.PASS
    for status, _ in checks.values():
        if status == CheckStatus.FAIL:
            overall = CheckStatus.FAIL
            break
        elif status == CheckStatus.WARN:
            overall = CheckStatus.WARN
    
    return CheckResult(file=cf, status=overall, checks=checks)


def print_check_results(results: List[CheckResult], verbose: bool = False) -> None:
    """打印检查结果"""
    pass_count = sum(1 for r in results if r.status == CheckStatus.PASS)
    warn_count = sum(1 for r in results if r.status == CheckStatus.WARN)
    fail_count = sum(1 for r in results if r.status == CheckStatus.FAIL)
    
    click.echo("=" * 80)
    click.echo("检查结果")
    click.echo("=" * 80)
    
    click.echo(f"\n📊 总览:")
    click.echo(f"  检查文件: {len(results)}")
    click.echo(f"  ✅ 通过: {pass_count}")
    click.echo(f"  ⚠️  警告: {warn_count}")
    click.echo(f"  ❌ 失败: {fail_count}")
    
    if verbose or fail_count > 0 or warn_count > 0:
        click.echo(f"\n📋 详情:")
        for i, result in enumerate(results, 1):
            if result.status == CheckStatus.PASS and not verbose:
                continue
            
            status_icon = {'pass': '✅', 'warn': '⚠️', 'fail': '❌'}[result.status.value]
            click.echo(f"\n{status_icon} [{i}] {result.file.filename}")
            
            for check_name, (status, msg) in result.checks.items():
                icon = {'pass': '  ✅', 'warn': '  ⚠️', 'fail': '  ❌'}[status.value]
                click.echo(f"{icon} {check_name}: {msg}")
    
    click.echo("\n" + "=" * 80)


@click.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--naming-pattern', help='自定义命名规则正则表达式')
@click.option('--max-image-size', type=int, help='图片最大大小（字节），默认50MB')
@click.option('--max-audio-size', type=int, help='音频最大大小（字节），默认100MB')
@click.option('--no-recursive', is_flag=True, help='不递归扫描子目录')
@click.option('--output', '-o', type=click.Path(path_type=Path), help='输出检查报告')
@click.option('--error-log', type=click.Path(path_type=Path), help='错误记录输出路径')
@click.option('--verbose', '-v', is_flag=True, help='显示详细信息')
def check(directory: Path, naming_pattern: str, max_image_size: int, max_audio_size: int,
          no_recursive: bool, output: Path, error_log: Path, verbose: bool):
    """检查文件大小、格式和命名规则"""
    click.echo(f"🔎 正在检查目录: {directory}")
    
    files = scan_directory(directory, recursive=not no_recursive)
    click.echo(f"找到 {len(files)} 个文件")
    
    results: List[CheckResult] = []
    
    with click.progressbar(files, label='检查中') as bar:
        for file_path in bar:
            try:
                cf = create_collection_file(file_path, compute_hash=False)
                
                max_size = None
                if cf.file_type == FileType.IMAGE and max_image_size:
                    max_size = max_image_size
                elif cf.file_type == FileType.AUDIO and max_audio_size:
                    max_size = max_audio_size
                
                result = run_checks(cf, naming_pattern, max_size)
                results.append(result)
            except Exception as e:
                click.echo(f"处理 {file_path.name} 出错: {e}")
    
    print_check_results(results, verbose)
    
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['file', 'status', 'format', 'size', 'naming'])
            for r in results:
                writer.writerow([
                    str(r.file.path),
                    r.status.value,
                    r.checks['format'][1],
                    r.checks['size'][1],
                    r.checks['naming'][1],
                ])
        click.echo(f"\n💾 检查报告已保存到: {output}")
    
    if error_log:
        errors = []
        for r in results:
            if r.status != CheckStatus.PASS:
                for check_name, (status, msg) in r.checks.items():
                    if status != CheckStatus.PASS:
                        errors.append(ErrorRecord(
                            file_path=str(r.file.path),
                            error_type=f'check_{check_name}_{status.value}',
                            message=msg,
                        ))
        save_error_records(errors, error_log)
        click.echo(f"💾 错误记录已保存到: {error_log}")
