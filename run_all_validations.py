"""一键验证脚本 - 覆盖全部修复与新增场景"""

import csv
import json
import shutil
import subprocess
import sys
import zipfile
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
# 场景 1：tag 多次 apply → 版本历史
# ============================================================
def scene1_tag_history_and_external_manifest():
    print("\n" + "#" * 70)
    print("# 场景1：tag 版本历史 + 外部清单文件")
    print("#" * 70)
    
    tags_csv = TEST_BASE / '场景1_藏品标签.csv'
    external_manifest = TEST_BASE / '我的外部清单.json'
    
    for p in COLLECTIONS.iterdir():
        if p.name.startswith('.collection_tags'):
            p.unlink()
    if external_manifest.exists():
        external_manifest.unlink()
    
    # 第一次（写到目录内部）
    out1 = run([PYTHON, '-m', 'collection_manager', 'tag',
                str(COLLECTIONS), str(tags_csv), '--apply'])
    assert_true('已记录到版本历史 (v1)' in out1, "第一次 tag --apply 是 v1")
    
    # 第二次（写到外部路径）
    out2 = run([PYTHON, '-m', 'collection_manager', 'tag',
                str(COLLECTIONS), str(tags_csv),
                '--apply', '--manifest-output', str(external_manifest)])
    assert_true('已记录到版本历史 (v2)' in out2, "第二次 tag --apply 是 v2")
    assert_true(external_manifest.exists(), "外部清单文件已生成")
    
    history_file = COLLECTIONS / '.collection_tags_history.json'
    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
    assert_true(len(history) == 2, f"历史共 2 条，实际 {len(history)}")
    # 第二次的 manifest_path 应该是外部清单路径
    assert_true(str(external_manifest.resolve()) == str(Path(history[-1]['manifest_path']).resolve()) or
                external_manifest.name in history[-1]['manifest_path'],
                "第二次历史记录指向外部清单路径")
    
    # 测试 1a：用 tag --apply --manifest-output 生成的外部清单通过 --manifest-file 传给 pack
    #  → 因为历史里 manifest_path / generated_at 能对上，应该匹配到 v2
    packed_match = TEST_BASE / 'scene1_pack_match_history'
    if packed_match.exists():
        shutil.rmtree(packed_match)
    run([PYTHON, '-m', 'collection_manager', 'pack',
         str(COLLECTIONS), '--manifest-file', str(external_manifest),
         '-o', str(packed_match), '--only-themes', '古代文明展',
         '-v', '--apply'],
        input_text='y\n')
    
    report_a = json.loads((packed_match / '整理报告.json').read_text(encoding='utf-8'))
    assert_true(report_a.get('tags_history_used_version') == 2,
                f"通过 tag --apply 生成的外部清单匹配到历史 v2，实际 {report_a.get('tags_history_used_version')}")
    assert_true('匹配历史记录' in report_a.get('tags_history_used_version_note', ''),
                "note 里包含'匹配历史记录'")
    
    # 测试 1b：构造一个"真正外部"的清单（不是目录历史任何一次生成的），应匹配不上
    fake_manifest = TEST_BASE / '真正外部清单.json'
    fake_tags = {
        'OLD-001': {'年代': '商代', '类别': '青铜器', '作者': '未知', '展览主题': '古代文明展'},
    }
    fake_manifest.write_text(json.dumps({
        'schema_version': '1.0',
        'generated_at': '2000-01-01T00:00:00',
        'source': '手工伪造',
        'tag_count': 1,
        'tags': fake_tags,
    }, ensure_ascii=False), encoding='utf-8')
    
    packed_nomatch = TEST_BASE / 'scene1_pack_nomatch'
    if packed_nomatch.exists():
        shutil.rmtree(packed_nomatch)
    run([PYTHON, '-m', 'collection_manager', 'pack',
         str(COLLECTIONS), '--manifest-file', str(fake_manifest),
         '-o', str(packed_nomatch), '--only-themes', '古代文明展',
         '-v', '--apply'],
        input_text='y\n')
    
    report_b = json.loads((packed_nomatch / '整理报告.json').read_text(encoding='utf-8'))
    note = report_b.get('tags_history_used_version_note', '')
    assert_true(report_b.get('tags_history_used_version') is None,
                f"伪造外部清单 tags_history_used_version=None，实际 {report_b.get('tags_history_used_version')}")
    assert_true('未匹配到目录历史版本' in note or '仅使用清单自带元数据' in note,
                f"伪造外部清单 note 提示未匹配，note={note}")
    assert_true('tags_manifest_meta' in report_b and report_b['tags_manifest_meta']['path'],
                "报告含 tags_manifest_meta 并指向外部清单路径")
    
    print("\n✅ 场景1通过")


# ============================================================
# 场景 2：--only-themes 不带 --exclude-uncategorized，仍不混入未分类
# ============================================================
def scene2_only_themes_without_exclude():
    print("\n" + "#" * 70)
    print("# 场景2：--only-themes 古代文明展（不带 --exclude-uncategorized）→ 报告范围只包含选中主题")
    print("#" * 70)
    
    packed_dir = TEST_BASE / 'scene2_only_ancient_without_exclude'
    if packed_dir.exists():
        shutil.rmtree(packed_dir)
    
    out = run([PYTHON, '-m', 'collection_manager', 'pack',
               str(COLLECTIONS), '--only-themes', '古代文明展',
               '-o', str(packed_dir), '-v', '--apply'],
              input_text='y\n')
    
    assert_true('已自动排除未分类' in out, "终端提示 '已自动排除未分类'")
    
    subdirs = [p.name for p in packed_dir.iterdir() if p.is_dir()]
    assert_true(subdirs == ['古代文明展'],
                f"输出只有古代文明展目录，实际: {subdirs}")
    
    report_json = packed_dir / '整理报告.json'
    with open(report_json, 'r', encoding='utf-8') as f:
        report = json.load(f)
    cids = sorted(report['collections'].keys())
    assert_true(cids == ['OLD-001', 'OLD-002'],
                f"JSON 报告藏品范围只含 OLD-001/OLD-002，实际: {cids}")
    assert_true(report['statistics']['total_collections'] == 2,
                f"总藏品数=2，实际 {report['statistics']['total_collections']}")
    
    csv_rows = read_csv_rows(packed_dir / '整理报告.csv')
    csv_ids = sorted([r['藏品编号'] for r in csv_rows])
    assert_true(csv_ids == ['OLD-001', 'OLD-002'],
                f"CSV 报告藏品列表只含 OLD-001/OLD-002，实际: {csv_ids}")
    
    summary_rows = read_csv_rows(packed_dir / '主题汇总清单.csv')
    assert_true(len(summary_rows) == 1 and summary_rows[0]['主题分组'] == '古代文明展',
                "主题汇总清单只含古代文明展")
    assert_true(int(summary_rows[0]['藏品数']) == 2,
                f"主题汇总藏品数=2，实际 {summary_rows[0]['藏品数']}")
    
    # 交接清单：文件名/大小 与磁盘一致
    handover = packed_dir / '古代文明展_交接清单.csv'
    handover_rows = read_csv_rows(handover)
    ancient_dir = packed_dir / '古代文明展'
    old001 = next(r for r in handover_rows if r['藏品编号'] == 'OLD-001')
    img_file = ancient_dir / old001['image_文件名']
    assert_true(img_file.exists() and img_file.stat().st_size == int(old001['image_大小(字节)']),
                "交接清单 OLD-001 图片文件名/大小 与磁盘一致")
    
    print("\n✅ 场景2通过")


# ============================================================
# 场景 3：zip 模式交接清单与 zip 内部条目一致
# ============================================================
def scene3_zip_handover():
    print("\n" + "#" * 70)
    print("# 场景3：--format zip → 每个 zip 旁有交接清单，文件名/大小与 zipinfo 对齐")
    print("#" * 70)
    
    packed_dir = TEST_BASE / 'scene3_zip'
    if packed_dir.exists():
        shutil.rmtree(packed_dir)
    
    run([PYTHON, '-m', 'collection_manager', 'pack',
         str(COLLECTIONS), '--only-themes', '古代文明展,书画艺术展',
         '-o', str(packed_dir), '--format', 'zip', '-v', '--apply'],
        input_text='y\n')
    
    ancient_zip = packed_dir / '古代文明展.zip'
    ancient_handover = packed_dir / '古代文明展_交接清单.csv'
    calli_zip = packed_dir / '书画艺术展.zip'
    calli_handover = packed_dir / '书画艺术展_交接清单.csv'
    
    for zip_path, handover_path, group_name in (
        (ancient_zip, ancient_handover, '古代文明展'),
        (calli_zip, calli_handover, '书画艺术展'),
    ):
        assert_true(zip_path.exists(), f"{group_name}.zip 存在")
        assert_true(handover_path.exists(), f"{group_name}_交接清单.csv 存在")
        
        zip_sizes = {}
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                zip_sizes[Path(info.filename).name] = info.file_size
        assert_true(len(zip_sizes) >= 3, f"{group_name} zip 内至少 3 个文件")
        
        ho_rows = read_csv_rows(handover_path)
        for row in ho_rows:
            for ftype in ('image', 'audio', 'text'):
                if row.get(f'{ftype}_存在') == '是':
                    fname = row[f'{ftype}_文件名']
                    fsize = int(row[f'{ftype}_大小(字节)'])
                    assert_true(fname in zip_sizes,
                                f"{group_name} 交接清单 {fname} 在 zip 条目里存在")
                    assert_true(zip_sizes[fname] == fsize,
                                f"{group_name} {fname} 交接清单大小({fsize})与 zipinfo({zip_sizes[fname]})一致")
    
    # zip 批次在 batch-config 里也要生效 → 验证其交接清单
    calli_zip_batch = TEST_BASE / '批次输出' / '春季展_书画艺术_zip'
    if calli_zip_batch.exists():
        shutil.rmtree(calli_zip_batch)
    
    print("\n✅ 场景3通过")


# ============================================================
# 场景 4：未分类报告里没有内部文件解析出的假藏品，缺失文件统计正常
# ============================================================
def scene4_no_internal_fake_collections():
    print("\n" + "#" * 70)
    print("# 场景4：未分类素材里不再混入 .collection_tags_history.json 等内部文件解析的假藏品")
    print("#" * 70)
    
    packed_dir = TEST_BASE / 'scene4_uncategorized'
    if packed_dir.exists():
        shutil.rmtree(packed_dir)
    
    # 确保目录有内部文件
    assert_true((COLLECTIONS / '.collection_tags.json').exists(),
                "素材目录下有 .collection_tags.json")
    assert_true((COLLECTIONS / '.collection_tags_history.json').exists(),
                "素材目录下有 .collection_tags_history.json")
    
    # 只打未分类
    run([PYTHON, '-m', 'collection_manager', 'pack',
         str(COLLECTIONS), '-o', str(packed_dir),
         '--only-themes', '', '--exclude-uncategorized'],  # 预览
        )
    
    run([PYTHON, '-m', 'collection_manager', 'pack',
         str(COLLECTIONS), '-o', str(packed_dir),
         '--format', 'copy', '-v', '--apply'],
        input_text='y\n')
    
    report_json = packed_dir / '整理报告.json'
    with open(report_json, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    cids = list(report['collections'].keys())
    fake_cids = [c for c in cids if 'ECTION' in c or c.startswith('COLLECTION')]
    assert_true(len(fake_cids) == 0,
                f"未分类报告里无内部文件解析出的假藏品，实际出现: {fake_cids}")
    
    # TMP-A1/TMP-A2/TMP-A3 三个藏品，每个三类文件齐全 → 完整藏品数 = 3
    assert_true(report['statistics']['complete_collections'] == 3,
                f"未分类里完整藏品数=3（TMP-A1/2/3 各齐全），实际 {report['statistics']['complete_collections']}")
    # 总藏品数应为 3（TMP-A1/2/3），其他文件（pdf/exe/zip/ppt/db）没有编号，不算藏品
    assert_true(report['statistics']['total_collections'] == 3,
                f"未分类总藏品数=3，实际 {report['statistics']['total_collections']}")
    
    # 未分类目录里不出现 .collection_tags*.json
    uncat_dir = packed_dir / '未分类'
    internal_files = [f.name for f in uncat_dir.iterdir()
                      if f.is_file() and f.name.startswith('.collection_tags')]
    assert_true(len(internal_files) == 0,
                f"打包后的未分类目录不含内部文件，实际出现: {internal_files}")
    
    print("\n✅ 场景4通过")


# ============================================================
# 场景 5：批次配置 - zip 批次生效 + 非法 format 批次失败但不阻断后续
# ============================================================
def scene5_batch_with_invalid_format():
    print("\n" + "#" * 70)
    print("# 场景5：批次配置（含 zip 批次和非法 format 批次）")
    print("#" * 70)
    
    batch_config = TEST_BASE / '批次配置_展览交接.json'
    batch_root = TEST_BASE / '批次输出'
    if batch_root.exists():
        shutil.rmtree(batch_root)
    
    error_log = TEST_BASE / '批次_errors.csv'
    out = run([PYTHON, '-m', 'collection_manager', 'pack',
               str(COLLECTIONS), '--batch-config', str(batch_config),
               '--apply', '-v', '--error-log', str(error_log)],
              input_text='y\ny\ny\ny\n')
    
    assert_true('批次汇总' in out, "终端显示批次汇总")
    assert_true('春季展_古代文明' in out and '春季展_书画艺术_zip' in out,
                "copy 批次 + zip 批次都出现在汇总里")
    assert_true('格式非法的批次' in out and '失败' in out,
                "非法 format 批次在汇总里被标记为失败")
    assert_true('未分类素材' in out and '成功' in out,
                "非法批次之后的未分类素材批次仍然成功（未被阻断）")
    
    # zip 批次有 zip 文件和交接清单
    zip_batch_dir = batch_root / '春季展_书画艺术_zip'
    assert_true((zip_batch_dir / '书画艺术展.zip').exists(),
                "zip 批次产出书画艺术展.zip")
    assert_true((zip_batch_dir / '书画艺术展_交接清单.csv').exists(),
                "zip 批次产出书画艺术展_交接清单.csv")
    
    # 交接清单与 zip 内条目一致
    zip_path = zip_batch_dir / '书画艺术展.zip'
    handover_path = zip_batch_dir / '书画艺术展_交接清单.csv'
    zip_sizes = {}
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            zip_sizes[Path(info.filename).name] = info.file_size
    for row in read_csv_rows(handover_path):
        for ftype in ('image', 'audio', 'text'):
            if row.get(f'{ftype}_存在') == '是':
                fname = row[f'{ftype}_文件名']
                assert_true(zip_sizes.get(fname) == int(row[f'{ftype}_大小(字节)']),
                            f"zip 批次 {fname} 交接清单大小与 zipinfo 对齐")
    
    # error-log 包含非法 format 的记录
    assert_true(error_log.exists(), "批次 error-log 存在")
    err_rows = read_csv_rows(error_log)
    bad_format = [r for r in err_rows if r.get('error_type') == 'batch_config_error'
                  and '不支持的 format' in (r.get('message', ''))]
    assert_true(len(bad_format) >= 1,
                f"error-log 包含至少一条 batch_config_error（非法 format），实际 {len(bad_format)} 条")
    
    print("\n✅ 场景5通过")


# ============================================================
# 主流程
# ============================================================
def main():
    try:
        reset_data()
        scene1_tag_history_and_external_manifest()
        scene2_only_themes_without_exclude()
        scene3_zip_handover()
        scene4_no_internal_fake_collections()
        scene5_batch_with_invalid_format()
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
