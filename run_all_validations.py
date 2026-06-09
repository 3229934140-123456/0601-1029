"""一键运行三个修复场景的验证"""

import subprocess
import sys
import shutil
from pathlib import Path


def run_cmd(cmd: str, cwd: Path) -> int:
    print(f"\n{'='*70}")
    print(f"▶  {cmd}")
    print(f"{'='*70}\n")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    return result.returncode


def main() -> int:
    project_root = Path(__file__).parent
    test_root = project_root / 'test_fix_data'
    collections = test_root / 'collections'

    # 0. 重置测试数据
    print("\n" + "#" * 70)
    print("# 0. 重置测试数据")
    print("#" * 70)
    if test_root.exists():
        shutil.rmtree(test_root)
    subprocess.run([sys.executable, str(project_root / 'create_test_data.py')], cwd=project_root, check=True)

    all_ok = True

    # 场景1：tag --apply 生成清单 -> pack 自动读取
    print("\n" + "#" * 70)
    print("# 场景1：tag --apply 导入标签后，pack 直接自动读取 .collection_tags.json")
    print("#" * 70)
    rc = run_cmd(
        f"{sys.executable} -m collection_manager tag {collections} {test_root/'场景1_藏品标签.csv'} --apply",
        project_root,
    )
    all_ok = all_ok and (rc == 0)

    tags_file = collections / '.collection_tags.json'
    if tags_file.exists():
        print(f"\n✅ 标签清单已生成: {tags_file}")
    else:
        print(f"\n❌ 标签清单未生成！")
        all_ok = False

    rc = run_cmd(
        f"{sys.executable} -m collection_manager pack {collections} -v",
        project_root,
    )
    all_ok = all_ok and (rc == 0)

    # 场景2：check 检测不支持格式
    print("\n" + "#" * 70)
    print("# 场景2：check 将 pdf/exe/zip/ppt/db 标记为格式失败")
    print("#" * 70)
    rc = run_cmd(
        f"{sys.executable} -m collection_manager check {collections} "
        f"-o {test_root/'check_report.csv'} --error-log {test_root/'check_errors.csv'}",
        project_root,
    )
    all_ok = all_ok and (rc == 0)

    err_csv = test_root / 'check_errors.csv'
    if err_csv.exists():
        content = err_csv.read_text(encoding='utf-8-sig')
        bad_formats = ['.pdf', '.exe', '.zip', '.ppt', '.db']
        found = all(ext in content for ext in bad_formats)
        if found:
            print(f"\n✅ error-log 包含所有不支持格式记录")
        else:
            print(f"\n❌ error-log 缺少某些不支持格式记录！")
            all_ok = False

    # 场景3：rename --id-map 编号映射
    print("\n" + "#" * 70)
    print("# 场景3：rename --id-map 让旧编号→新编号真正生效")
    print("#" * 70)
    rc = run_cmd(
        f"{sys.executable} -m collection_manager rename {collections} "
        f"--id-map {test_root/'场景3_编号映射.csv'}",
        project_root,
    )
    all_ok = all_ok and (rc == 0)

    print("\n" + "#" * 70)
    if all_ok:
        print("# ✅ 全部三个场景验证通过！")
    else:
        print("# ❌ 部分场景验证失败，请检查上方输出")
    print("#" * 70 + "\n")

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
