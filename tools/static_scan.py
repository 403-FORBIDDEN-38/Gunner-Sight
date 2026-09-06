"""GS静态扫描工具 - 每次提交前运行
检查: 裸函数引用/重复方法定义/未使用import/except吞没
用法: python tools/static_scan.py
"""
import os, re, sys, ast
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'__pycache__', 'build', 'dist', '.git', 'tools'}

def scan():
    issues = []
    py_files = []
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith('.py'):
                py_files.append(os.path.join(dirpath, fn))

    for fp in py_files:
        rel = os.path.relpath(fp, ROOT)
        with open(fp, encoding='utf-8') as f:
            src = f.read()
            lines = src.split('\n')

        # 1. 裸time.sleep（不带括号），排除注释行
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            if re.search(r'time\.sleep\s*(?!\()', line) and 'def ' not in line:
                issues.append(f'[ERROR] {rel}:{i}: 裸time.sleep引用（无括号）: {line.strip()}')

        # 2. 重复方法定义
        try:
            tree = ast.parse(src)
            methods = defaultdict(list)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if node in parent.body:
                                methods[(parent.name, node.name)].append(node.lineno)
            for (cls, name), linenos in methods.items():
                if len(linenos) > 1:
                    issues.append(f'[ERROR] {rel}: 类{cls}重复方法定义{name} at lines {linenos}')
        except SyntaxError:
            issues.append(f'[ERROR] {rel}: 语法错误无法解析')

        # 3. except:pass（危险操作吞没检测）
        for i, line in enumerate(lines):
            if re.search(r'except\s+(Exception\s*)?:\s*$', line):
                if i+1 < len(lines) and re.match(r'^\s+pass\s*$', lines[i+1]):
                    # 检查上下文：如果是清理/释放操作则合理，否则警告
                    context = '\n'.join(lines[max(0,i-3):i+2])
                    cleanup_keywords = ['close', 'release', 'unhook', 'disconnect', 'deleteLater',
                                       'BlockInput(False)', 'SetCursorPos', 'rename', 'unhook_all',
                                       'UnhookWindowsHookEx', 'PostThreadMessage', 'on_stopped',
                                       'IsUserAnAdmin', 'set_edit_mode']
                    if not any(kw in context for kw in cleanup_keywords):
                        issues.append(f'[WARN] {rel}:{i+1}: except:pass可能是危险操作吞没: {line.strip()}')

        # 4. 未使用的import（简单检查）
        try:
            tree = ast.parse(src)
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.asname or alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name != '*':
                            imports.add(alias.asname or alias.name)
            used = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name):
                        used.add(node.value.id)
            for imp in imports:
                if imp not in used and imp not in ('os', 'sys', 're', 'json', 'time', 'threading'):
                    # 排除可能在字符串或动态使用中的
                    if imp not in src.replace(f'import {imp}', ''):
                        issues.append(f'[INFO] {rel}: 可能未使用的import: {imp}')
        except SyntaxError:
            pass

    return issues

if __name__ == '__main__':
    issues = scan()
    errors = [i for i in issues if i.startswith('[ERROR]')]
    warns = [i for i in issues if i.startswith('[WARN]')]
    infos = [i for i in issues if i.startswith('[INFO]')]
    print(f'=== 静态扫描结果 ===')
    print(f'ERROR: {len(errors)}, WARN: {len(warns)}, INFO: {len(infos)}')
    for i in issues:
        print(i)
    sys.exit(1 if errors else 0)
