#!/usr/bin/env python3
"""Generate Worker - 从模板生成新 Worker 服务"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# ============================================================
# Worker 生成脚本 — 基于 workers/pingpong-worker 模板
# 与 generate_service.py 同构，但适配 Worker（无端口、无 API）
# written by @awen
# ============================================================

# 基础路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
WORKERS_DIR = PROJECT_ROOT / "workers"
TEMPLATE_WORKER = WORKERS_DIR / "pingpong-worker"
SCRIPT_DIR = Path(__file__).parent


def to_snake_case(name: str) -> str:
    """转换为 snake_case: NewApp -> new_app, new-app -> new_app"""
    name = name.replace('-', '_')
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def toPascalCase(name: str) -> str:
    """转换为 PascalCase: new-app -> NewApp"""
    return ''.join(word.capitalize() for word in name.replace('-', ' ').split())


def check_worker_exists(worker_name: str) -> bool:
    """检查 Worker 是否已存在"""
    kebab_name = worker_name.lower()
    worker_dir = WORKERS_DIR / f"{kebab_name}-worker"
    return worker_dir.exists()


def check_prefix_exists(prefix: str) -> bool:
    """检查 SHORT_PREFIX 是否已存在于 workers 中"""
    # 同时检查 services 目录避免冲突
    for check_dir in [WORKERS_DIR, PROJECT_ROOT / "services"]:
        if not check_dir.exists():
            continue
        for item_dir in check_dir.iterdir():
            if not item_dir.is_dir():
                continue
            # 尝试 worker.metadata 和 service.metadata
            for metadata_name in ["worker.metadata", "service.metadata"]:
                metadata_file = item_dir / metadata_name
                if not metadata_file.exists():
                    continue
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        if metadata.get("worker_prefix") == prefix or metadata.get("service_prefix") == prefix:
                            return True
                except (json.JSONDecodeError, IOError):
                    continue
    return False


def get_all_replacements(worker_name: str, short_prefix: str) -> list:
    """获取所有需要替换的内容（按顺序）"""
    snake_name = to_snake_case(worker_name)
    pascal_name = toPascalCase(worker_name)
    kebab_name = snake_name.replace('_', '-')
    display_name = worker_name.replace('-', ' ').title()

    return [
        # 第一批：精确匹配（避免误替换）

        # 数据库名替换 (保持 kebab 格式) - 必须在 "pingpong" 替换之前
        ("pingpong-db", f"{kebab_name}-db"),

        # Worker 名称显示替换 (必须在 "pingpong" 替换之前)
        ("pingpong Worker", f"{display_name} Worker"),
        ("pingpong worker", f"{display_name} worker"),

        # 第二批：显示名称替换 (PascalCase)
        ("PingPong", pascal_name),
        ("PingpPong", pascal_name),

        # 第三批：Worker 名称替换 (目录名使用 kebab 格式)
        ("pingpong-worker", f"{kebab_name}-worker"),
        ("pingpong_worker", f"{snake_name}_worker"),

        # 第四批：前缀替换
        ("pipo", short_prefix),

        # 第五批：表名前缀
        ("pipo_", f"{short_prefix}_"),

        # 第六批：类名替换
        ("PingPongCache", f"{pascal_name}Cache"),
        ("PingPongRedisCache", f"{pascal_name}RedisCache"),
        ("PingPongService", f"{pascal_name}Service"),

        # 第七批：文件名替换
        ("ping_pong", snake_name),

        # 第八批：通用替换 (放最后)
        ("pingpong", snake_name),
    ]


def replace_content(content: str, replacements: list) -> str:
    """替换内容中的占位符（按顺序替换）"""
    for old, new in replacements:
        content = content.replace(old, new)
    return content


def should_skip_file(file_path: Path) -> bool:
    """检查是否应该跳过该文件"""
    if file_path.suffix in ['.pyc', '.pyo', '.so', '.egg-info', '.md5', '.pyo']:
        return True
    if '__pycache__' in str(file_path) or '.pytest_cache' in str(file_path):
        return True
    if '.ruff_cache' in str(file_path):
        return True
    return False


def process_file(file_path: Path, replacements: list) -> None:
    """处理单个文件"""
    if should_skip_file(file_path):
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IOError):
        return

    # 替换内容
    new_content = replace_content(content, replacements)

    # 处理文件名
    new_name = file_path.name
    for old, new in replacements:
        new_name = new_name.replace(old, new)

    # 如果文件名改变了，重命名文件
    if new_name != file_path.name:
        new_path = file_path.parent / new_name
        if not new_path.exists():
            file_path.rename(new_path)
            file_path = new_path

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)


def rename_directory(dir_path: Path, replacements: list) -> Path:
    """递归重命名目录（自底向上）"""
    if not dir_path.is_dir():
        return dir_path
    if should_skip_file(dir_path):
        return dir_path

    # 先递归处理子目录
    children = list(dir_path.iterdir())
    for child in children:
        if child.is_dir():
            rename_directory(child, replacements)

    # 处理当前目录名
    new_name = dir_path.name
    for old, new in replacements:
        new_name = new_name.replace(old, new)

    if new_name != dir_path.name:
        new_path = dir_path.parent / new_name
        if not new_path.exists():
            dir_path.rename(new_path)
            return new_path
    return dir_path


def process_worker(worker_name: str, short_prefix: str) -> None:
    """处理 Worker 生成"""
    kebab_name = worker_name.lower()
    new_worker_dir = WORKERS_DIR / f"{kebab_name}-worker"

    print(f"从模板复制到: {new_worker_dir}")

    # 复制整个目录（忽略 .env 文件和缓存目录）
    def ignore_func(src, names):
        ignored = set()
        if '.env' in names:
            ignored.add('.env')
        if '__pycache__' in names:
            ignored.add('__pycache__')
        if '.pytest_cache' in names:
            ignored.add('.pytest_cache')
        if '.ruff_cache' in names:
            ignored.add('.ruff_cache')
        if '.DS_Store' in names:
            ignored.add('.DS_Store')
        return ignored

    shutil.copytree(TEMPLATE_WORKER, new_worker_dir, dirs_exist_ok=False, ignore=ignore_func)

    # 获取替换规则
    replacements = get_all_replacements(worker_name, short_prefix)

    # 第一步：重命名所有目录
    rename_directory(new_worker_dir, replacements)

    # 第二步：处理所有文件（包括重命名和内容替换）
    for item in new_worker_dir.rglob('*'):
        if item.is_file():
            process_file(item, replacements)

    # 删除不必要的缓存文件
    for pattern in ['__pycache__', '.pytest_cache', '*.pyc', '.ruff_cache']:
        for item in new_worker_dir.rglob(pattern):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass


def create_metadata(worker_name: str, short_prefix: str) -> None:
    """创建 worker.metadata 文件"""
    kebab_name = worker_name.lower()
    snake_name = to_snake_case(worker_name)
    metadata_file = WORKERS_DIR / f"{kebab_name}-worker" / "worker.metadata"

    metadata = {
        "worker_name": snake_name,
        "worker_prefix": short_prefix,
    }

    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

    print(f"已创建: {metadata_file}")


def backup_and_update_root_pyproject(worker_name: str) -> None:
    """备份并更新根目录的 pyproject.toml"""
    kebab_name = worker_name.lower()
    root_pyproject = PROJECT_ROOT / "pyproject.toml"
    backup_dir = PROJECT_ROOT / ".cache" / "generate-bak"

    # 创建备份目录
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 备份原文件
    backup_file = backup_dir / "pyproject.toml"
    if root_pyproject.exists():
        shutil.copy2(root_pyproject, backup_file)
        print(f"已备份: {backup_file}")

    if not root_pyproject.exists():
        print(f"警告: 根目录 pyproject.toml 不存在，跳过更新")
        return

    content = root_pyproject.read_text(encoding='utf-8')

    # 更新 [project].dependencies
    if f'{kebab_name}-worker' not in content:
        pattern = r'(dependencies\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            old_deps = match.group(2)
            if old_deps.strip():
                new_deps = old_deps.rstrip().rstrip(',') + f',\n    "{kebab_name}-worker",'
            else:
                new_deps = f'\n    "{kebab_name}-worker",'
            content = content[:match.start(1)] + match.group(1) + new_deps + match.group(3) + content[match.end():]
            print(f"已更新 [project].dependencies: {kebab_name}-worker")

    # 更新 [tool.uv.workspace].members
    if f'"workers/{kebab_name}-worker"' not in content:
        pattern = r'(members\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            old_members = match.group(2)
            if old_members.strip():
                new_members = old_members.rstrip() + f'\n    "workers/{kebab_name}-worker",'
            else:
                new_members = f'\n    "workers/{kebab_name}-worker",'
            content = content[:match.start(1)] + match.group(1) + new_members + match.group(3) + content[match.end():]
            print(f"已更新 [tool.uv.workspace].members: workers/{kebab_name}-worker")

    # 更新 [tool.uv.sources]
    source_entry = f'{kebab_name}-worker = {{ workspace = true }}'
    if source_entry not in content:
        if '[tool.uv.sources]' in content:
            content = content.replace(
                '[tool.uv.sources]',
                f'[tool.uv.sources]\n{kebab_name}-worker = {{ workspace = true }}'
            )
            print(f"已更新 [tool.uv.sources]: {source_entry}")
        else:
            content += f"\n[tool.uv.sources]\n{kebab_name}-worker = {{ workspace = true }}\n"
            print(f"已创建 [tool.uv.sources]: {source_entry}")

    # 写回文件
    root_pyproject.write_text(content, encoding='utf-8')
    print(f"已更新: {root_pyproject}")


def main():
    parser = argparse.ArgumentParser(description="生成新 Worker 服务")
    parser.add_argument("worker_name", help="Worker 名称 (例如: new-app)")
    parser.add_argument("short_prefix", help="短前缀 (例如: na)")

    args = parser.parse_args()

    worker_name = args.worker_name
    short_prefix = args.short_prefix

    # 验证参数
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9-]*$', worker_name):
        print(f"错误: Worker 名称 '{worker_name}' 格式不正确")
        print("应使用字母、数字和连字符，不能以数字开头")
        sys.exit(1)

    if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', short_prefix):
        print(f"错误: 短前缀 '{short_prefix}' 格式不正确")
        print("应使用字母和数字，不能以数字开头")
        sys.exit(1)

    if len(short_prefix) < 2 or len(short_prefix) > 10:
        print(f"错误: 短前缀长度应在 2-10 之间")
        sys.exit(1)

    # 检查模板是否存在
    if not TEMPLATE_WORKER.exists():
        print(f"错误: Worker 模板不存在: {TEMPLATE_WORKER}")
        sys.exit(1)

    # 检查 Worker 是否已存在
    if check_worker_exists(worker_name):
        print(f"错误: Worker '{worker_name}' 已存在于 workers 目录中")
        sys.exit(1)

    # 检查前缀是否已存在
    if check_prefix_exists(short_prefix):
        print(f"错误: 前缀 '{short_prefix}' 已被其他服务/Worker 使用")
        sys.exit(1)

    # 生成 Worker
    print(f"\n开始生成 Worker: {worker_name} (前缀: {short_prefix})")
    print("=" * 50)

    process_worker(worker_name, short_prefix)
    create_metadata(worker_name, short_prefix)

    # 备份并更新根目录 pyproject.toml
    backup_and_update_root_pyproject(worker_name)

    print("=" * 50)
    print(f"Worker 生成完成!")
    print(f"Worker 目录: workers/{worker_name.lower()}-worker")
    print(f"\n接下来可以:")
    print(f"  1. 前置检查: 确保根目录 pyproject.toml 文件，【当删除 Worker 时请手动反向操作去除】")
    print(f"            在 [tool.uv.workspace].dependencies 中存在 \"{worker_name.lower()}-worker\"; ")
    print(f"            在 [tool.uv.workspace].members 中存在 \"workers/{worker_name.lower()}-worker\"; ")
    print(f"            在 [tool.uv.sources] 中存在 {worker_name.lower()}-worker =" + " { workspace = true } .")
    print(f"  2. 进入venv: source .venv/bin/activate")
    print(f"  3. 安装依赖: make install-worker WORKER={worker_name.lower()}-worker")
    print(f"  4. 启动开发: make dev-worker WORKER={worker_name.lower()}-worker")
    print(f"  5. 新增 Handler: 在 handlers/ 目录下新增处理器模块，并在 handlers/registry.py 中注册")
    print(f"  6. 扩展 Broker: 在 broker/implementations/ 下新增实现，并在 broker/factory.py 中注册")


if __name__ == "__main__":
    main()