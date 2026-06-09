from setuptools import setup, find_packages

setup(
    name='collection-manager',
    version='1.0.0',
    description='数字文化馆馆藏素材整理工具',
    author='Digital Culture Museum',
    packages=find_packages(),
    install_requires=[
        'click>=8.0.0',
        'pandas>=1.3.0',
        'openpyxl>=3.0.0',
        'Pillow>=9.0.0',
        'pydub>=0.25.0',
    ],
    entry_points={
        'console_scripts': [
            'cm=collection_manager.cli:cli',
        ],
    },
    python_requires='>=3.7',
)
