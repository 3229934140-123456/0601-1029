"""创建验证修复场景的测试数据"""

import csv
import json
import shutil
from pathlib import Path


def create_fix_test_data(base_dir: Path) -> None:
    """创建覆盖三个修复场景的测试数据"""
    
    # 清理旧数据
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    collections_dir = base_dir / 'collections'
    collections_dir.mkdir(parents=True, exist_ok=True)
    
    # ============================================================
    # 场景 1：tag --apply 生成清单后 pack 直接读取
    # ============================================================
    scene1_collections = [
        {'id': 'OLD-001', 'name': '青铜鼎', 'era': '商代', 'category': '青铜器', 'author': '未知', 'exhibition': '古代文明展'},
        {'id': 'OLD-002', 'name': '青花瓷瓶', 'era': '明代', 'category': '瓷器', 'author': '佚名', 'exhibition': '古代文明展'},
        {'id': 'OLD-003', 'name': '山水画', 'era': '清代', 'category': '书画', 'author': '王翚', 'exhibition': '书画艺术展'},
    ]
    
    for col in scene1_collections:
        cid = col['id']
        (collections_dir / f'{cid}_照片.jpg').write_bytes(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb' * 100)
        (collections_dir / f'{cid}_讲解.mp3').write_bytes(
            b'ID3\x04\x00\x00\x00\x00\x00\x00' + cid.encode() + b'\x00' * 500)
        (collections_dir / f'{cid}_说明.txt').write_text(
            f"藏品编号：{cid}\n名称：{col['name']}\n", encoding='utf-8')
    
    # 标签表格（加两个"清单里有但目录里无"的幽灵编号，用于测试 missing_tag_ids）
    scene1_tags = base_dir / '场景1_藏品标签.csv'
    with open(scene1_tags, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['藏品编号', '名称', '年代', '类别', '作者', '展览主题'])
        for col in scene1_collections:
            writer.writerow([col['id'], col['name'], col['era'], col['category'], col['author'], col['exhibition']])
        writer.writerow(['GHOST-999', '缺图文物', '唐代', '陶器', '佚名', '古代文明展'])
        writer.writerow(['GHOST-888', '遗失书画', '宋代', '书画', '苏轼', '书画艺术展'])
    
    # ============================================================
    # 场景 2：不支持格式文件（pdf、exe、zip 等）- check 应标记失败
    # ============================================================
    unsupported_files = [
        ('参观指南.pdf', b'%PDF-1.4 fake pdf content'),
        ('安装程序.exe', b'MZ\x90\x00 fake exe content'),
        ('资料包.zip', b'PK\x03\x04 fake zip content'),
        ('演示文稿.ppt', b'\xd0\xcf\x11\xe0 fake ppt content'),
        ('数据备份.db', b'SQLite format 3\x00 fake db'),
    ]
    for name, content in unsupported_files:
        (collections_dir / name).write_bytes(content)
    
    # ============================================================
    # 场景 3：编号映射表 - rename --id-map 应生效
    # ============================================================
    scene3_collections = [
        {'old': 'TMP-A1', 'new': 'EXH-2024-001', 'name': '玉如意'},
        {'old': 'TMP-A2', 'new': 'EXH-2024-002', 'name': '金步摇'},
        {'old': 'TMP-A3', 'new': 'EXH-2024-003', 'name': '银盘'},
    ]
    for col in scene3_collections:
        oid = col['old']
        (collections_dir / f'{oid}_照片.jpg').write_bytes(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb' * 100)
        (collections_dir / f'{oid}_音频.mp3').write_bytes(
            b'ID3\x04\x00\x00\x00\x00\x00\x00' + oid.encode() + b'\x00' * 500)
        (collections_dir / f'{oid}_文本.txt').write_text(
            f"临时编号：{oid}\n将改为：{col['new']}\n名称：{col['name']}\n", encoding='utf-8')
    
    # 编号映射表
    id_map_csv = base_dir / '场景3_编号映射.csv'
    with open(id_map_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['旧编号', '新编号', '图片描述', '音频描述', '文本描述'])
        for col in scene3_collections:
            writer.writerow([col['old'], col['new'], '文物照片', '讲解录音', '藏品说明'])
    
    # 批次配置文件（含 copy 批次、zip 批次、以及故意写错 format 的批次）
    batch_config = base_dir / '批次配置_展览交接.json'
    batch_data = [
        {
            'name': '春季展_古代文明',
            'themes': ['古代文明展'],
            'exclude_uncategorized': True,
            'output_dir': str((base_dir / '批次输出' / '春季展_古代文明').resolve()),
            'format': 'copy',
        },
        {
            'name': '春季展_书画艺术_zip',
            'themes': ['书画艺术展'],
            'exclude_uncategorized': True,
            'output_dir': str((base_dir / '批次输出' / '春季展_书画艺术_zip').resolve()),
            'format': 'zip',
        },
        {
            'name': '格式非法的批次',
            'themes': ['古代文明展'],
            'output_dir': str((base_dir / '批次输出' / '格式非法批次').resolve()),
            'format': 'tar_gz',
        },
        {
            'name': '未分类素材',
            'only_uncategorized': True,
            'output_dir': str((base_dir / '批次输出' / '未分类素材').resolve()),
            'format': 'copy',
        },
    ]
    with open(batch_config, 'w', encoding='utf-8') as f:
        json.dump(batch_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 测试数据已创建在: {base_dir}")
    print(f"   素材目录: {collections_dir}")
    print(f"\n📂 文件结构：")
    for p in sorted(collections_dir.iterdir()):
        print(f"   - {p.name}")
    print(f"\n📋 场景说明：")
    print(f"   场景1 - tag --apply 打包链路：")
    print(f"     藏品 OLD-001~003（图片+音频+说明）")
    print(f"     标签表: {scene1_tags.name}")
    print(f"   场景2 - 不支持格式：")
    print(f"     {', '.join(n for n, _ in unsupported_files)}")
    print(f"   场景3 - 编号映射：")
    for col in scene3_collections:
        print(f"     {col['old']} -> {col['new']}")
    print(f"     映射表: {id_map_csv.name}")
    print(f"\n🚀 验证命令：")
    print(f"   # 场景1：tag 导入 -> pack 自动读取")
    print(f"   python -m collection_manager tag {collections_dir} {scene1_tags} --apply")
    print(f"   python -m collection_manager pack {collections_dir} -v")
    print(f"   # 场景2：不支持格式检查")
    print(f"   python -m collection_manager check {collections_dir} -o check_report.csv --error-log check_errors.csv")
    print(f"   # 场景3：编号映射重命名")
    print(f"   python -m collection_manager rename {collections_dir} --id-map {id_map_csv}")
    print()


if __name__ == '__main__':
    test_base = Path(__file__).parent / 'test_fix_data'
    create_fix_test_data(test_base)
