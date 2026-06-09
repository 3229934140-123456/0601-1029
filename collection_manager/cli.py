"""命令行入口"""

import click

from .commands.scan_cmd import scan
from .commands.rename_cmd import rename
from .commands.check_cmd import check
from .commands.tag_cmd import tag
from .commands.pack_cmd import pack


@click.group()
@click.version_option(version='1.0.0', prog_name='collection-manager')
def cli():
    """数字文化馆馆藏素材整理工具

    \b
    提供以下命令：
      scan    - 扫描文件夹，识别重复文件和缺失说明
      rename  - 按藏品编号统一重命名
      check   - 检查文件大小、格式和命名规则
      tag     - 从表格导入标签，生成待补充清单
      pack    - 按展览主题打包素材，输出整理报告
    """
    pass


cli.add_command(scan)
cli.add_command(rename)
cli.add_command(check)
cli.add_command(tag)
cli.add_command(pack)


if __name__ == '__main__':
    cli()
