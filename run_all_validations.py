"""一键验证脚本 - 覆盖所有修复与新增场景"""

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


def read_csv_rows(path: Path) -> list:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


# ============================================================
# 场景 A：tag 版本历史 + 清单复用 + missing_tag_ids
# ============================================================
def scene_a_tag_history():
    print("\n" + "#" * 70)
    print("# 场景A：tag 版本历史 / 清单复用 / 清单有但目录无的编号")
    print("#" * 70)
    
    tags_csv = TEST_BASE / '场景1_藏品标签.csv'
    
    # 清理旧的清单与历史
    for p in COLLECTIONS.iterdir():
        if p.name.startswith('.collection_tags'):
            p.unlink()
    
    # 第一次 tag --apply
    out1 = run([
        PYTHON, '-m', 'collection_manager', 'tag',
        str(COLLECTIONS), str(tags_csv), '--apply',
    ])
    assert_true('已记录到版本历史 (v1)' in out1,
                "第一次 tag --apply 显示 v1 版本历史")
    
    # 第二次 tag --apply（应该是 v2）
    out2 = run([
        PYTHON, '-m', 'collection_manager', 'tag',
        str(COLLECTIONS), str(tags_csv), '--apply',
    ])
    assert_true('已记录到版本历史 (v2)' in out2,
                "第二次 tag --apply 显示 v2 版本历史")
    
    history_file = COLLECTIONS / '.collection_tags_history.json'
    assert_true(history_file.exists(), ".collection_tags_history.json 存在于素材目录")
    
    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
    assert_true(isinstance(history, list) and len(history) >= 2,
                f"历史列表至少有 2 条记录，实际 {len(history)}")
    assert_true(history[-1]['version'] == 2,
                f"最新版本号=2，实际 {history[-1]['version']}")
    assert_true(history[-1].get('generated_at') and history[-1].get('source'),
                "历史记录包含 generated_at 和 source 元数据")
    
    manifest = COLLECTIONS / '.collection_tags.json'
    assert_true(manifest.exists(), ".collection_tags.json 存在")
    with open(manifest, 'r', encoding='utf-8') as f:
        mf = json.load(f)
    assert_true('GHOST-999' in mf.get('tags', {}),
                "清单里包含 GHOST-999（幽灵编号，用于测试 missing_tag_ids）")
    
    print("\n✅ 场景A通过")


# ============================================================
# 场景 B：--only-themes + --exclude-uncategorized，报告范围验证
# ============================================================
def scene_b_only_themes():
    print("\n" + "#" * 70)
    print("# 场景B：只选古代文明展并排除未分类 → 报告范围验证")
    print("#" * 70)
    
    packed_dir = TEST_BASE / 'sceneB_only_ancient'
    if packed_dir.exists():
        shutil.rmtree(packed_dir)
    
    out = run([
        PYTHON, '-m', 'collection_manager', 'pack',
        str(COLLECTIONS),
        '--only-themes', '古代文明展',
        '--exclude-uncategorized',
        '-o', str(packed_dir),
        '-v', '--apply',
    ], input_text='y\n')
    
    # 输出目录下只应有 古代文明展
    subdirs = [p.name for p in packed_dir.iterdir() if p.is_dir()]
    assert_true(subdirs == ['古代文明展'],
                f"只输出 '古代文明展' 分组，实际目录: {subdirs}")
    
    # JSON 报告里的 collections 只有 OLD-001、OLD-002（GHOST-999 没文件）
    report_json = packed_dir / '整理报告.json'
    assert_true(report_json.exists(), "整理报告.json 存在")
    with open(report_json, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    collections_in_report = list(report['collections'].keys())
    assert_true(sorted(collections_in_report) == ['OLD-001', 'OLD-002'],
                f"JSON 报告 collections 只含 OLD-001/OLD-002，实际: {collections_in_report}")
    assert_true(report['statistics']['total_collections'] == 2,
                f"总藏品数=2，实际 {report['statistics']['total_collections']}")
    
    # 标签版本信息存在
    assert_true('tags_history_used_version' in report,
                "报告包含 tags_history_used_version")
    assert_true(report.get('tags_history_used_version') >= 2,
                f"使用标签版本 >= 2，实际 {report.get('tags_history_used_version')}")
    
    # missing_tag_ids 包含 GHOST-999
    assert_true('GHOST-999' in report.get('missing_tag_ids', []),
                f"missing_tag_ids 包含 GHOST-999，实际: {report.get('missing_tag_ids')}")
    
    # 主题汇总与 JSON group_summaries 一致
    summary_csv = packed_dir / '主题汇总清单.csv'
    summary_rows = read_csv_rows(summary_csv)
    assert_true(len(summary_rows) == 1 and summary_rows[0]['主题分组'] == '古代文明展',
                f"主题汇总清单只有一行 古代文明展，实际 {[r['主题分组'] for r in summary_rows]}")
    assert_true(int(summary_rows[0]['藏品数']) == 2,
                f"主题汇总藏品数=2，实际 {summary_rows[0]['藏品数']}")
    gs = report['group_summaries']['古代文明展']
    assert_true(int(summary_rows[0]['文件数']) == gs['file_count'],
                "主题汇总 CSV 与 JSON group_summaries 的文件数一致")
    
    # CSV 报告藏品范围也只有 OLD-001、OLD-002
    report_csv = packed_dir / '整理报告.csv'
    csv_rows = read_csv_rows(report_csv)
    csv_ids = sorted([r['藏品编号'] for r in csv_rows])
    assert_true(csv_ids == ['OLD-001', 'OLD-002'],
                f"CSV 报告藏品列表只含 OLD-001/OLD-002，实际: {csv_ids}")
    with open(report_csv, 'r', encoding='utf-8-sig') as f:
        csv_header = list(csv.reader(f))[0]
    assert_true('展览主题' in csv_header,
                f"CSV 报告表头包含展览主题标签列，表头: {csv_header}")
    
    # 缺失素材 CSV 存在
    missing_csv = packed_dir / '缺失素材_标签有但目录无.csv'
    assert_true(missing_csv.exists(), "缺失素材 CSV 已生成")
    missing_rows = read_csv_rows(missing_csv)
    missing_ids = [r['藏品编号'] for r in missing_rows]
    assert_true('GHOST-999' in missing_ids and 'GHOST-888' in missing_ids,
                f"缺失素材 CSV 含 GHOST-999/GHOST-888，实际: {missing_ids}")
    
    # 交接清单：古代文明展_交接清单.csv
    handover = packed_dir / '古代文明展_交接清单.csv'
    assert_true(handover.exists(), f"古代文明展_交接清单.csv 存在")
    handover_rows = read_csv_rows(handover)
    handover_ids = sorted([r['藏品编号'] for r in handover_rows])
    assert_true(handover_ids == ['OLD-001', 'OLD-002'],
                f"交接清单里只含 OLD-001/OLD-002，实际: {handover_ids}")
    
    # 交接清单包含 image/audio/text 存在/文件名/大小字段
    hdr = handover_rows[0]
    for ftype in ('image', 'audio', 'text'):
        assert_true(f'{ftype}_存在' in hdr or any(k.startswith(f'{ftype}_') for k in hdr.keys()),
                    f"交接清单包含 {ftype}_ 相关字段")
    
    # 对照磁盘：OLD-001 的图片文件在交接清单里的文件名、大小与磁盘一致
    old001_row = next(r for r in handover_rows if r['藏品编号'] == 'OLD-001')
    assert_true(old001_row['image_存在'] == '是',
                "OLD-001 图片存在=是")
    ancient_dir = packed_dir / '古代文明展'
    img_file = ancient_dir / old001_row['image_文件名']
    assert_true(img_file.exists() and img_file.stat().st_size == int(old001_row['image_大小(字节)']),
                "交接清单 OLD-001 图片文件名/大小 与磁盘实际一致")
    
    print("\n✅ 场景B通过")


# ============================================================
# 场景 C：批次配置打包（--batch-config）
# ============================================================
def scene_c_batch_config():
    print("\n" + "#" * 70)
    print("# 场景C：批次配置打包（3个批次）")
    print("#" * 70)
    
    batch_config = TEST_BASE / '批次配置_展览交接.json'
    batch_out_root = TEST_BASE / '批次输出'
    if batch_out_root.exists():
        shutil.rmtree(batch_out_root)
    
    out = run([
        PYTHON, '-m', 'collection_manager', 'pack',
        str(COLLECTIONS),
        '--batch-config', str(batch_config),
        '--apply', '-v',
    ], input_text='y\ny\ny\n')
    
    # 终端有批次汇总
    assert_true('批次汇总' in out, "终端输出包含 '批次汇总'")
    assert_true('春季展_古代文明' in out and '春季展_书画艺术' in out and '未分类素材' in out,
                "三个批次都出现在终端输出中")
    
    # 三个输出目录都存在
    ancient_out = batch_out_root / '春季展_古代文明'
    calligraphy_out = batch_out_root / '春季展_书画艺术'
    uncategorized_out = batch_out_root / '未分类素材'
    for p, name in ((ancient_out, '春季展_古代文明'),
                    (calligraphy_out, '春季展_书画艺术'),
                    (uncategorized_out, '未分类素材')):
        assert_true(p.exists(), f"批次输出目录 {name} 存在")
    
    # 春季展_古代文明：只有古代文明展分组
    ancient_subdirs = [p.name for p in ancient_out.iterdir() if p.is_dir()]
    assert_true(ancient_subdirs == ['古代文明展'],
                f"春季展_古代文明 只含 古代文明展 目录，实际: {ancient_subdirs}")
    ancient_report = ancient_out / '整理报告.json'
    with open(ancient_report, 'r', encoding='utf-8') as f:
        ar = json.load(f)
    assert_true(ar['statistics']['total_collections'] == 2,
                f"春季展_古代文明 报告总藏品数=2，实际 {ar['statistics']['total_collections']}")
    assert_true((ancient_out / '古代文明展_交接清单.csv').exists(),
                "春季展_古代文明 有交接清单")
    
    # 春季展_书画艺术：OLD-003 一个藏品，3个文件
    calligraphy_report = calligraphy_out / '整理报告.json'
    with open(calligraphy_report, 'r', encoding='utf-8') as f:
        cr = json.load(f)
    assert_true(cr['statistics']['total_collections'] == 1,
                f"春季展_书画艺术 报告总藏品数=1，实际 {cr['statistics']['total_collections']}")
    calligraphy_handover = calligraphy_out / '书画艺术展_交接清单.csv'
    calligraphy_rows = read_csv_rows(calligraphy_handover)
    assert_true(calligraphy_rows[0]['藏品编号'] == 'OLD-003',
                f"书画艺术展交接清单藏品=OLD-003，实际 {calligraphy_rows[0]['藏品编号']}")
    assert_true(calligraphy_rows[0]['是否完整'] == '是',
                "OLD-003 三类文件齐全，标记完整")
    
    # 未分类素材：包含 TMP-A1~TMP-A3 和 unsupported files
    uncategorized_report = uncategorized_out / '整理报告.json'
    with open(uncategorized_report, 'r', encoding='utf-8') as f:
        ur = json.load(f)
    uncategorized_files = ur['groups'].get('未分类', {}).get('files', [])
    uncategorized_names = [Path(p).name for p in uncategorized_files]
    assert_true(any('TMP-A1' in n for n in uncategorized_names),
                "未分类素材包含 TMP-A1 的文件")
    assert_true(any('参观指南.pdf' == n for n in uncategorized_names),
                "未分类素材包含 pdf 等不支持格式")
    
    # 未分类目录文件数与磁盘一致
    uncat_dir = uncategorized_out / '未分类'
    disk_count = len([f for f in uncat_dir.iterdir() if f.is_file()])
    report_count = ur['groups']['未分类']['file_count']
    assert_true(disk_count == report_count,
                f"未分类磁盘文件数={disk_count} 与报告 file_count={report_count} 一致")
    
    print("\n✅ 场景C通过")


# ============================================================
# 场景 2（旧）：不支持格式 - 终端+error-log
# ============================================================
def scene2_check_unsupported():
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
    
    for name in unsupported_names:
        assert_true(name in check_out, f"终端输出包含 {name}")
    assert_true('不支持的文件格式' in check_out,
                "终端输出包含 '不支持的文件格式' 错误信息")
    
    assert_true(report_csv.exists(), "check_report.csv 已生成")
    report_rows = read_csv_rows(report_csv)
    unsupported_in_report = [r for r in report_rows if r.get('file') and Path(r['file']).name in unsupported_names]
    assert_true(len(unsupported_in_report) == 5,
                f"check_report.csv 中 5 个不支持格式均有记录，实际 {len(unsupported_in_report)}")
    for r in unsupported_in_report:
        assert_true('不支持' in r.get('format', ''),
                    f"{Path(r['file']).name} 的 format 列含'不支持'")
    
    assert_true(error_csv.exists(), "check_errors.csv 已生成")
    err_rows = read_csv_rows(error_csv)
    for name in unsupported_names:
        file_errs = [r for r in err_rows if r.get('file_path') and Path(r['file_path']).name == name]
        assert_true(len(file_errs) >= 1, f"error-log 包含 {name} 的至少一条记录")
        has_format_err = any(
            'format' in (r.get('error_type') or '') and
            '不支持' in (r.get('message') or '')
            for r in file_errs
        )
        assert_true(has_format_err, f"error-log 中 {name} 存在含'不支持'的 format 错误")
    
    print("\n✅ 场景2通过")


# ============================================================
# 场景 3（旧）：rename --id-map --apply
# ============================================================
def scene3_rename_apply():
    print("\n" + "#" * 70)
    print("# 场景3：rename 编号映射 apply → 图片/音频/说明同新编号落盘")
    print("#" * 70)
    
    id_map_csv = TEST_BASE / '场景3_编号映射.csv'
    error_log = TEST_BASE / 'rename_errors.csv'
    
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
    
    apply_out = run([
        PYTHON, '-m', 'collection_manager', 'rename',
        str(COLLECTIONS),
        '--id-map', str(id_map_csv),
        '--error-log', str(error_log),
        '--apply',
    ], input_text='y\n')
    
    new_ids = ['EXH-2024-001', 'EXH-2024-002', 'EXH-2024-003']
    old_ids = ['TMP-A1', 'TMP-A2', 'TMP-A3']
    
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
        scene_a_tag_history()
        scene_b_only_themes()
        scene_c_batch_config()
        scene2_check_unsupported()
        scene3_rename_apply()
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
    
    print("\n" + "#" * 70)
    print("# ✅ 全部场景验证通过！")
    print("#" * 70)


if __name__ == '__main__':
    main()
