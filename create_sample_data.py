"""创建示例测试数据"""

import csv
from pathlib import Path


def create_sample_data(base_dir: Path) -> None:
    """创建示例藏品素材数据"""
    base_dir.mkdir(parents=True, exist_ok=True)

    collections = [
        {'id': 'COL-001', 'name': '青铜鼎', 'era': '商代', 'category': '青铜器', 'author': '未知', 'exhibition': '古代文明展'},
        {'id': 'COL-002', 'name': '青花瓷瓶', 'era': '明代', 'category': '瓷器', 'author': '佚名', 'exhibition': '古代文明展'},
        {'id': 'COL-003', 'name': '山水画', 'era': '清代', 'category': '书画', 'author': '王翚', 'exhibition': '书画艺术展'},
        {'id': 'COL-004', 'name': '玉如意', 'era': '清代', 'category': '玉器', 'author': '宫廷造办处', 'exhibition': '书画艺术展'},
        {'id': 'COL-005', 'name': '唐三彩', 'era': '唐代', 'category': '陶器', 'author': '佚名', 'exhibition': '古代文明展'},
    ]

    for col in collections:
        cid = col['id']
        
        img_path = base_dir / f'{cid}_照片.jpg'
        if not img_path.exists():
            img_path.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb' * 100)
        else:
            img_path.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb' * 100)
        
        audio_path = base_dir / f'{cid}_讲解.mp3'
        audio_path.write_bytes(b'ID3\x04\x00\x00\x00\x00\x00\x00' + cid.encode() + b'\x00' * 500)
        
        text_path = base_dir / f'{cid}_说明.txt'
        text_path.write_text(
            f"藏品编号：{cid}\n"
            f"名称：{col['name']}\n"
            f"年代：{col['era']}\n"
            f"类别：{col['category']}\n"
            f"作者：{col['author']}\n"
            f"简介：这是{col['era']}时期的{col['name']}，属于{col['category']}类文物。\n",
            encoding='utf-8'
        )

    extra_files = [
        ('无名照片.jpg', '这是一个没有编号的图片'),
        ('COL-006_照片_重复.jpg', '重复的额外图片'),
        ('some_random_file.txt', '一个随机文件'),
    ]
    for name, _ in extra_files:
        (base_dir / name).write_text('test data', encoding='utf-8')

    tags_csv = base_dir.parent / '藏品标签.csv'
    with open(tags_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['藏品编号', '名称', '年代', '类别', '作者', '展览主题', '备注'])
        for col in collections:
            writer.writerow([col['id'], col['name'], col['era'], col['category'], col['author'], col['exhibition'], ''])
        writer.writerow(['COL-006', '石雕佛像', '唐代', '石刻', '', '古代文明展', '缺少图片'])

    print(f"示例数据已创建在: {base_dir}")
    print(f"标签文件: {tags_csv}")


if __name__ == '__main__':
    sample_dir = Path(__file__).parent / 'sample_data' / 'collections'
    create_sample_data(sample_dir)
