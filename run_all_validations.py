"""一键验证脚本 - 覆盖所有修复场景"""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
TEST_BASE = BASE / 'test_fix_data'
COLLECTIONS = TEST_BASE / 'collections'
PYTHON = sys.executable


def run(cmd: list, cwd=None, input_text=None) -> str:
    """运行命令并返回 stdout+stderr"""
    print("\n" + "=" * 70)
    print(f"▶  {' '.join(cmd)}")
    print("=" * 70)
    env = None
    if sys.platform.startswith('win'):
        import os
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run(
        cmd,
        cwd=cwd or str(BASE),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        input=input_text,
        env=env,
    )
    output = (result.stdout or '') + (result.stderr or '')
    sys.stdout.write(output)
    sys.stdout.flush()
    return output


def reset_data():
    """重置测试数据"""
    print("\n" + "#" * 70)
    print("# 0. 重置测试数据")
    print("#" * 70)
    run([PYTHON, str(BASE / 'create_test_data.py')])


def assert_true(cond: bool, msg: str):
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        raise AssertionError(msg)


# ============================================================
# 场景 1：tag --apply → pack --apply，整理报告里有完整标签
# ============================================================
def scene1():
    print("\n" + "#" * 70)
    print("# 场景1：tag 导入标签 → pack 自动读取清单 → 整理报告含标签")
    print("#" * 70)
    
    tags_csv = TEST_BASE / '场景1_藏品标签.csv'
    external_manifest = TEST_BASE / '我的标签清单.json'
    
    # 步骤1：tag --apply 把清单写到用户指定的外部路径
    tag_out = run([
        PYTHON, '-m', 'collection_manager', 'tag',
        str(COLLECTIONS), str(tags_csv),
        '--apply', '--manifest-output', str(external_manifest),
    ])
    assert_true(external_manifest.exists(), f"外部清单文件已生成: {external_manifest.name}")
    
    with open(external_manifest, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    assert_true('tags' in manifest and len(manifest['tags']) == 3,
                "清单包含 3 条标签记录")
    assert_true(manifest.get('source', '').endswith('场景1_藏品标签.csv'),
                f"清单元数据记录了来源: {manifest.get('source')}")
    assert_true('OLD-001' in manifest['tags'] and '展览主题' in manifest['tags']['OLD-001'],
                "OLD-001 有完整标签（含展览主题）")
    
    # 步骤2：pack 使用 --manifest-file 指定外部清单，且 --apply 真正执行
    packed_dir = TEST_BASE / 'collections_packed'
    if packed_dir.exists():
        shutil.rmtree(packed_dir)
    
    pack_out = run([
        PYTHON, '-m', 'collection_manager', 'pack',
        str(COLLECTIONS),
        '--manifest-file', str(external_manifest),
        '-v', '--apply',
    ], input_text='y\n')
    
    # 步骤3：验证输出目录结构
    assert_true(packed_dir.exists(), "pack 输出目录已创建")
    
    ancient_dir = packed_dir / '古代文明展'
    calligraphy_dir = packed_dir / '书画艺术展'
    uncategorized_dir = packed_dir / '未分类'
    assert_true(ancient_dir.is_dir(), "存在 '古代文明展' 分组目录")
    assert_true(calligraphy_dir.is_dir(), "存在 '书画艺术展' 分组目录")
    assert_true(uncategorized_dir.is_dir(), "存在 '未分类' 分组目录")
    
    ancient_files = list(ancient_dir.iterdir())
    assert_true(len(ancient_files) == 6,
                f"古代文明展有 6 个文件（OLD-001 + OLD-002 各3件），实际 {len(ancient_files)}")
    old001_present = any('OLD-001' in f.name for f in ancient_files)
    assert_true(old001_present, "古代文明展包含 OLD-001 藏品")
    
    # 步骤4：检查整理报告 JSON
    report_json = packed_dir / '整理报告.json'
    assert_true(report_json.exists(), "整理报告.json 已生成")
    with open(report_json, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    assert_true('tags_source' in report, "报告中包含 tags_source")
    assert_true('清单文件' in report['tags_source'],
                f"tags_source 指示为清单文件: {report['tags_source']}")
    assert_true('all_tag_fields' in report and len(report['all_tag_fields']) >= 4,
                f"报告包含全部标签字段名: {report.get('all_tag_fields')}")
    assert_true('OLD-001' in report['collections'],
                "报告包含 OLD-001 藏品")
    tags001 = report['collections']['OLD-001']['tags']
    assert_true(tags001.get('年代') and tags001.get('类别') and tags001.get('作者') and tags001.get('展览主题'),
                f"OLD-001 在报告里有完整标签: {tags001}")
    
    # 步骤5：检查整理报告 CSV（各标签字段展开为独立列）
    report_csv = packed_dir / '整理报告.csv'
    assert_true(report_csv.exists(), "整理报告.csv 已生成")
    with open(report_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    header = reader.fieldnames or []
    assert_true('展览主题' in header and '年代' in header,
                f"CSV 表头已展开标签列: {header}")
    old001_row = next(r for r in rows if r['藏品编号'] == 'OLD-001')
    assert_true(old001_row['展览主题'] == '古代文明展',
                f"OLD-001 CSV 里的展览主题正确: {old001_row['展览主题']}")
    
    # 步骤6：检查主题汇总清单
    summary_csv = packed_dir / '主题汇总清单.csv'
    assert_true(summary_csv.exists(), "主题汇总清单.csv 已生成")
    with open(summary_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        summary_rows = list(reader)
    assert_true(len(summary_rows) == 3, f"主题汇总共 3 行，实际 {len(summary_rows)}")
    ancient_summary = next(r for r in summary_rows if r['主题分组'] == '古代文明展')
    assert_true(int(ancient_summary['藏品数']) == 2,
                f"古代文明展藏品数=2，实际 {ancient_summary['藏品数']}")
    assert_true(int(ancient_summary['文件数']) == 6,
                f"古代文明展文件数=6，实际 {ancient_summary['文件数']}")
    assert_true('总大小(可读)' in ancient_summary and ancient_summary['总大小(可读)'],
                "主题汇总含总大小(可读)字段")
    
    # 步骤7：验证 --only-themes 筛选
    packed_only = TEST_BASE / 'collections_only_ancient'
    if packed_only.exists():
        shutil.rmtree(packed_only)
    pack_only_out = run([
        PYTHON, '-m', 'collection_manager', 'pack',
        str(COLLECTIONS),
        '--manifest-file', str(external_manifest),
        '--only-themes', '古代文明展',
        '--exclude-uncategorized',
        '-o', str(packed_only),
        '-v', '--apply',
    ], input_text='y\n')
    only_dirs = [d.name for d in packed_only.iterdir() if d.is_dir()]
    assert_true('古代文明展' in only_dirs and '书画艺术展' not in only_dirs and '未分类' not in only_dirs,
                f"--only-themes + --exclude-uncategorized 只保留古代文明展: {only_dirs}")
    
    print("\n✅ 场景1通过")


# ============================================================
# 场景 2：check 不支持格式 - 终端报告 + error-log 都要有
# ============================================================
def scene2():
    print("\n" + "#" * 70)
    print("# 场景2：check 不支持格式 → 终端+error-log 双记录")
    print("#" * 70)
    
    report_csv = TEST_BASE / 'check_report.csv'
    error_csv = TEST_BASE / 'check_errors.csv'
    for p in (report_csv, error_csv):
        if p.exists():
            p.unlink()
    
    check_out = run([
        PYTHON, '-m', 'collection_manager', 'check',
        str(COLLECTIONS),
        '-o', str(report_csv),
        '--error-log', str(error_csv),
    ])
    
    unsupported_names = ['参观指南.pdf', '安装程序.exe', '资料包.zip', '演示文稿.ppt', '数据备份.db']
    
    # 终端输出检查
    for name in unsupported_names:
        assert_true(name in check_out, f"终端输出包含 {name}")
    assert_true('不支持的文件格式' in check_out,
                "终端输出包含 '不支持的文件格式' 错误信息")
    
    # check_report.csv 检查
    assert_true(report_csv.exists(), "check_report.csv 已生成")
    with open(report_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        report_rows = list(reader)
    unsupported_in_report = [r for r in report_rows if r.get('file') and Path(r['file']).name in unsupported_names]
    assert_true(len(unsupported_in_report) == 5,
                f"check_report.csv 中 5 个不支持格式均有记录，实际 {len(unsupported_in_report)}")
    for r in unsupported_in_report:
        assert_true('不支持' in r.get('format', ''),
                    f"{Path(r['file']).name} 的格式列含'不支持': {r.get('format', '')}")
    
    # error-log 检查
    assert_true(error_csv.exists(), "check_errors.csv 已生成")
    with open(error_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        err_rows = list(reader)
    
    for name in unsupported_names:
        file_errs = [r for r in err_rows if r.get('file_path') and Path(r['file_path']).name == name]
        assert_true(len(file_errs) >= 1, f"error-log 包含 {name} 的至少一条记录")
        has_format_err = any(
            'format' in (r.get('error_type') or '') and
            ('不支持' in (r.get('message') or '') or 'unsupported' in (r.get('message') or '').lower())
            for r in file_errs
        )
        assert_true(has_format_err, f"error-log 中 {name} 存在含'不支持'的 format 错误")
    
    print("\n✅ 场景2通过")


# ============================================================
# 场景 3：rename --id-map --apply → 三类文件同新编号落盘
# ============================================================
def scene3():
    print("\n" + "#" * 70)
    print("# 场景3：rename 编号映射 apply → 图片/音频/说明同新编号落盘")
    print("#" * 70)
    
    id_map_csv = TEST_BASE / '场景3_编号映射.csv'
    error_log = TEST_BASE / 'rename_errors.csv'
    
    # 先预览，看冲突检查是否正常（我们的数据是干净的，应该只有 missing_description 级别的提示）
    preview_out = run([
        PYTHON, '-m', 'collection_manager', 'rename',
        str(COLLECTIONS),
        '--id-map', str(id_map_csv),
        '--error-log', str(error_log),
    ])
    assert_true('TMP-A1→EXH-2024-001' in preview_out,
                "预览中显示 TMP-A1→EXH-2024-001 变换")
    assert_true('文物照片' in preview_out or '讲解录音' in preview_out or '藏品说明' in preview_out,
                "预览中显示自定义描述")
    
    # apply 真正执行
    apply_out = run([
        PYTHON, '-m', 'collection_manager', 'rename',
        str(COLLECTIONS),
        '--id-map', str(id_map_csv),
        '--error-log', str(error_log),
        '--apply',
    ], input_text='y\n')
    
    new_ids = ['EXH-2024-001', 'EXH-2024-002', 'EXH-2024-003']
    old_ids = ['TMP-A1', 'TMP-A2', 'TMP-A3']
    
    # 检查旧文件不存在、新文件存在
    files_on_disk = {f.name for f in COLLECTIONS.iterdir() if f.is_file() and not f.name.startswith('.')}
    
    for oid, nid in zip(old_ids, new_ids):
        old_match = [n for n in files_on_disk if n.startswith(oid)]
        assert_true(len(old_match) == 0,
                    f"旧编号 {oid} 的文件已不存在（剩余 {old_match}）")
        
        new_img = [n for n in files_on_disk if n.startswith(nid) and n.endswith('.jpg')]
        new_aud = [n for n in files_on_disk if n.startswith(nid) and n.endswith('.mp3')]
        new_txt = [n for n in files_on_disk if n.startswith(nid) and n.endswith('.txt')]
        assert_true(len(new_img) == 1 and '文物照片' in new_img[0],
                    f"{nid} 的图片文件存在且使用描述: {new_img}")
        assert_true(len(new_aud) == 1 and '讲解录音' in new_aud[0],
                    f"{nid} 的音频文件存在且使用描述: {new_aud}")
        assert_true(len(new_txt) == 1 and '藏品说明' in new_txt[0],
                    f"{nid} 的文本文件存在且使用描述: {new_txt}")
    
    print(f"\n📂 apply 后磁盘文件:")
    for f in sorted(files_on_disk):
        print(f"   - {f}")
    
    print("\n✅ 场景3通过")


# ============================================================
# 主流程
# ============================================================
def main():
    try:
        reset_data()
        scene1()
        scene2()
        scene3()
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
    
    print("\n" + "#" * 70)
    print("# ✅ 全部三个场景验证通过！")
    print("#" * 70)


if __name__ == '__main__':
    main()
