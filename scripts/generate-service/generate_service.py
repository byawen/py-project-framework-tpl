#!/usr/bin/env python3
"""Generate Service - 从模板生成新服务"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# ============================================================
# Tip: 前期基础框架使用脚本方式 + pingpong-service 服务模板生成
# 后期有机会再封装成脚本架工具
# written by @awen
# ============================================================

# 基础路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
SERVICES_DIR = PROJECT_ROOT / "services"
TEMPLATE_SERVICE = SERVICES_DIR / "pingpong-service"
SCRIPT_DIR = Path(__file__).parent


def to_snake_case(name: str) -> str:
    """转换为 snake_case: NewApp -> new_app, new-app -> new_app"""
    # 处理连字符
    name = name.replace('-', '_')
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def toPascalCase(name: str) -> str:
    """转换为 PascalCase: new-app -> NewApp"""
    return ''.join(word.capitalize() for word in name.replace('-', ' ').split())


def check_service_exists(service_name: str) -> bool:
    """检查服务是否已存在"""
    kebab_name = service_name.lower()  # new-app -> new-app
    service_dir = SERVICES_DIR / f"{kebab_name}-service"
    if service_dir.exists():
        return True
    return False


def check_prefix_exists(prefix: str) -> bool:
    """检查 SHORT_PREFIX 是否已存在"""
    for service_dir in SERVICES_DIR.iterdir():
        if not service_dir.is_dir():
            continue
        
        metadata_file = service_dir / "service.metadata"
        if not metadata_file.exists():
            continue
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                if metadata.get("service_prefix") == prefix:
                    return True
        except (json.JSONDecodeError, IOError):
            continue
    
    return False


def get_all_replacements(service_name: str, short_prefix: str, port: str = "8000") -> list:
    """获取所有需要替换的内容（按顺序）"""
    snake_name = to_snake_case(service_name)
    pascal_name = toPascalCase(service_name)
    kebab_name = snake_name.replace('_', '-')  # new_app -> new-app
    display_name = service_name.replace('-', ' ').title()  # new-app -> New App
    
    return [
        # 精确匹配（避免误替换）
        
        # 数据库名替换 (保持 kebab 格式) - 必须在 "pingpong" 替换之前
        ("pingpong-db", f"{kebab_name}-db"),
        
        # 服务名称显示替换 (必须在 "pingpong" 替换之前)
        ("pingpong Service", f"{display_name} Service"),
        ("pingpong service", f"{display_name} service"),
        ("pingpong-Service", f"{display_name}-Service"),
        
        # 端口替换 - 必须在 "8000" 替换之前
        ("8001", port),  # 默认端口替换
        
        # FastAPI 标题替换
        ("Ping Pong Service", f"{display_name} Service"),
        ("PingPong Service", f"{display_name} Service"),
        
        # 显示名称替换 (PascalCase)
        ("PingPong", pascal_name),
        ("PingpPong", pascal_name),
        
        # 服务名称替换 (目录名使用 kebab 格式)
        ("pingpong-service", f"{kebab_name}-service"),
        ("pingpong_service", f"{snake_name}_service"),
        
        # 前缀替换
        ("pipo", short_prefix),
        
        # 表名前缀
        ("pipo_", f"{short_prefix}_"),
        
        # 类名替换
        ("PingPongCache", f"{pascal_name}Cache"),
        ("PingPongRedisCache", f"{pascal_name}RedisCache"),
        ("PingPongService", f"{pascal_name}Service"),
        
        # 文件名替换
        ("ping_pong", snake_name),
        
        # 通用替换 (放最后)
        ("pingpong", snake_name),
        
        # 修复被误替换的显示名称 (如 PingPong -> new_app 后变成 new_app Service)
        ("new_app Service", f"{display_name} Service"),
    ]


def replace_content(content: str, replacements: list) -> str:
    """替换内容中的占位符（按顺序替换）"""
    for old, new in replacements:
        content = content.replace(old, new)
    return content


def should_skip_file(file_path: Path) -> bool:
    """检查是否应该跳过该文件"""
    # 跳过二进制文件和特定文件
    if file_path.suffix in ['.pyc', '.pyo', '.so', '.egg-info', '.md5', '.pyo']:
        return True
    
    # 跳过缓存目录
    if '__pycache__' in str(file_path) or '.pytest_cache' in str(file_path):
        return True
    
    # 跳过 .ruff_cache 等缓存目录
    if '.ruff_cache' in str(file_path):
        return True
    
    return False


def process_file(file_path: Path, replacements: dict) -> None:
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


def rename_directory(dir_path: Path, replacements: dict) -> None:
    """递归重命名目录（自底向上）"""
    if not dir_path.is_dir():
        return
    if should_skip_file(dir_path):
        return
    
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


def process_service(service_name: str, short_prefix: str, port: str = "8000") -> None:
    """处理服务生成"""
    snake_name = to_snake_case(service_name)
    kebab_name = service_name.lower()  # new-app -> new-app
    new_service_dir = SERVICES_DIR / f"{kebab_name}-service"
    
    print(f"从模板复制到: {new_service_dir}")
    
    # 复制整个目录（忽略 .env 文件和缓存目录）
    def ignore_func(src, names):
        ignored = set()
        # 忽略 .env 文件
        if '.env' in names:
            ignored.add('.env')
        # 忽略缓存目录
        if '__pycache__' in names:
            ignored.add('__pycache__')
        if '.pytest_cache' in names:
            ignored.add('.pytest_cache')
        if '.ruff_cache' in names:
            ignored.add('.ruff_cache')
        # 忽略 .DS_Store
        if '.DS_Store' in names:
            ignored.add('.DS_Store')
        return ignored
    
    shutil.copytree(TEMPLATE_SERVICE, new_service_dir, dirs_exist_ok=False, ignore=ignore_func)
    
    # 获取替换规则
    replacements = get_all_replacements(service_name, short_prefix, port)
    
    # 重命名所有目录
    rename_directory(new_service_dir, replacements)

    # 处理所有文件（包括重命名和内容替换）
    for item in new_service_dir.rglob('*'):
        if item.is_file():
            process_file(item, replacements)
    
    # 删除不必要的缓存文件
    for pattern in ['__pycache__', '.pytest_cache', '*.pyc', '.ruff_cache']:
        for item in new_service_dir.rglob(pattern):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass


def check_port_exists(port: str) -> bool:
    """检查端口是否已被占用"""
    for service_dir in SERVICES_DIR.iterdir():
        if not service_dir.is_dir():
            continue
        
        metadata_file = service_dir / "service.metadata"
        if not metadata_file.exists():
            continue
        
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                if metadata.get("port") == port:
                    return True
        except (json.JSONDecodeError, IOError):
            continue
    
    return False


def create_metadata(service_name: str, short_prefix: str, port: str) -> None:
    """创建 service.metadata 文件"""
    kebab_name = service_name.lower()  # new-app -> new-app
    snake_name = to_snake_case(service_name)
    metadata_file = SERVICES_DIR / f"{kebab_name}-service" / "service.metadata"
    
    metadata = {
        "service_name": snake_name,
        "service_prefix": short_prefix,
        "port": port
    }
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    
    print(f"已创建: {metadata_file}")


def backup_and_update_root_pyproject(service_name: str) -> None:
    """备份并更新根目录的 pyproject.toml"""
    kebab_name = service_name.lower()
    root_pyproject = PROJECT_ROOT / "pyproject.toml"
    backup_dir = PROJECT_ROOT / ".cache" / "generate-bak"
    
    # 创建备份目录
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 备份原文件
    backup_file = backup_dir / "pyproject.toml"
    if root_pyproject.exists():
        shutil.copy2(root_pyproject, backup_file)
        print(f"已备份: {backup_file}")
    
    # 读取并更新 pyproject.toml
    if not root_pyproject.exists():
        print(f"警告: 根目录 pyproject.toml 不存在，跳过更新")
        return
    
    content = root_pyproject.read_text(encoding='utf-8')
    
    # 更新 [project].dependencies
    if f'{kebab_name}-service' not in content:
        import re
        # 匹配 dependencies = [ ... ] 块
        pattern = r'(dependencies\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            old_deps = match.group(2)
            # 在最后一个依赖后添加新服务
            if old_deps.strip():
                new_deps = old_deps.rstrip().rstrip(',') + f',\n    "{kebab_name}-service",'
            else:
                new_deps = f'\n    "{kebab_name}-service",'
            content = content[:match.start(1)] + match.group(1) + new_deps + match.group(3) + content[match.end():]
            print(f"已更新 [project].dependencies: {kebab_name}-service")
        else:
            print(f"警告: 未找到 [project].dependencies 配置")
    
    # 更新 [tool.uv.workspace].members
    if f'"services/{kebab_name}-service"' not in content:
        # 查找 members = [ 后面最后一行的位置
        import re
        # 匹配 members = [ ... ] 块
        pattern = r'(members\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            # 获取当前 members 内容
            old_members = match.group(2)
            # 检查最后一行是否已有成员
            if old_members.strip():
                # 在最后一个成员后添加新成员
                new_members = old_members.rstrip() + f'\n    "services/{kebab_name}-service",'
            else:
                new_members = f'\n    "services/{kebab_name}-service",'
            content = content[:match.start(1)] + match.group(1) + new_members + match.group(3) + content[match.end():]
            print(f"已更新 [tool.uv.workspace].members: services/{kebab_name}-service")
        else:
            print(f"警告: 未找到 [tool.uv.workspace].members 配置")
    
    # 更新 [tool.uv.sources]
    source_entry = f'{kebab_name}-service = {{ workspace = true, editable = true }}'
    if source_entry not in content:
        # 在 [tool.uv.sources] 后添加
        if '[tool.uv.sources]' in content:
            content = content.replace(
                '[tool.uv.sources]',
                f'[tool.uv.sources]\n{kebab_name}-service = {{ workspace = true, editable = true }}'
            )
            print(f"已更新 [tool.uv.sources]: {source_entry}")
        else:
            # 如果没有 sources 部分，添加到文件末尾
            content += f"\n[tool.uv.sources]\n{kebab_name}-service = {{ workspace = true, editable = true }}\n"
            print(f"已创建 [tool.uv.sources]: {source_entry}")
    
    # 写回文件
    root_pyproject.write_text(content, encoding='utf-8')
    print(f"已更新: {root_pyproject}")


def main():
    parser = argparse.ArgumentParser(description="生成新服务")
    parser.add_argument("service_name", help="服务名称 (例如: new-app)")
    parser.add_argument("short_prefix", help="短前缀 (例如: na)")
    parser.add_argument("port", nargs="?", default="8000", help="服务端口 (例如: 8001)")
    
    args = parser.parse_args()
    
    service_name = args.service_name
    short_prefix = args.short_prefix
    port = args.port
    
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9-]*$', service_name):
        print(f"错误: 服务名称 '{service_name}' 格式不正确")
        print("应使用字母、数字和连字符，不能以数字开头")
        sys.exit(1)
    
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', short_prefix):
        print(f"错误: 短前缀 '{short_prefix}' 格式不正确")
        print("应使用字母和数字，不能以数字开头")
        sys.exit(1)
    
    if len(short_prefix) < 2 or len(short_prefix) > 10:
        print(f"错误: 短前缀长度应在 2-10 之间")
        sys.exit(1)
    
    # 验证端口
    try:
        port_int = int(port)
        if port_int < 1 or port_int > 65535:
            print(f"错误: 端口 '{port}' 必须在 1-65535 之间")
            sys.exit(1)
    except ValueError:
        print(f"错误: 端口 '{port}' 必须是数字")
        sys.exit(1)
    
    # 检查服务是否已存在
    if check_service_exists(service_name):
        print(f"错误: 服务 '{service_name}' 已存在于 services 目录中")
        sys.exit(1)
    
    # 检查前缀是否已存在
    if check_prefix_exists(short_prefix):
        print(f"错误: 前缀 '{short_prefix}' 已被其他服务使用")
        sys.exit(1)
    
    # 检查端口是否已被占用
    if check_port_exists(port):
        print(f"错误: 端口 '{port}' 已被其他服务占用")
        sys.exit(1)
    
    print(f"\n开始生成服务: {service_name} (前缀: {short_prefix}, 端口: {port})")
    print("=" * 50)
    
    process_service(service_name, short_prefix, port)
    create_metadata(service_name, short_prefix, port)
    
    # 备份并更新根目录 pyproject.toml
    backup_and_update_root_pyproject(service_name)
    
    print("=" * 50)
    print(f"服务生成完成!")
    print(f"服务目录: services/{service_name.lower()}-service")
    print(f"\n接下来可以:")
    print(f"  1. 前置检查: 确保根目录 pyproject.toml 文件，【当删除服务时请手动反向操作去除】")
    print(f"            在 [tool.uv.workspace].dependencies 中存在 \"{service_name.lower()}-service\"; ")
    print(f"            在 [tool.uv.workspace].members 中存在 \"services/{service_name.lower()}-service \"; ")
    print(f"            在 [tool.uv.sources] 中存在 {service_name.lower()}-service =" + " { workspace = true, editable = true } .")
    print(f"  2. 进入venv: source .venv/bin/activate")
    print(f"  3. 安装依赖: make install-service SERVICE={service_name.lower()}-service")
    print(f"  4. 启动开发: make dev SERVICE={service_name.lower()}-service")
    print(f"  5. AllInOne支持: 【可选】需要 AllInOne 时，手动注册服务到该模式下")
    print(f"            在 all-in-one/src/all_in_one/config.py 注册 {service_name.lower()}-service 的相关配置;")
    print(f"            在 all-in-one/src/all_in_one/services.py 注册 {service_name.lower()}-service;")
    print(f"            执行 make all-in-one 启动服务")


if __name__ == "__main__":
    main()
