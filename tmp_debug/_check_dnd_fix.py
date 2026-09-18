"""验证工具箱拖拽修复"""
import ast
import re

with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\tools_page.py', 'r', encoding='utf-8') as f:
    src = f.read()

try:
    ast.parse(src)
    print('[OK] SYNTAX OK')
except SyntaxError as e:
    print(f'[ERR] line {e.lineno}: {e.msg}')

checks = {
    'AddToolDialog 支持预填': 'prefill_name: str' in src and 'prefill_path: str' in src,
    '_on_drop_files 打开对话框': 'prefill_category: str' in src and 'prefill_path=prefill_path' in src,
    '_register_drop_target 注册 DND': '_register_drop_target(self.toolbar_canvas)' in src and 'widget.drop_target_register' in src,
    '_make_category_drop_target 注册 DND': 'prefill_category=n' in src,
    '主 canvas 也绑定 _on_drop_files': "self.canvas.dnd_bind" in src,
}
for k, v in checks.items():
    mark = '[OK]' if v else '[FAIL]'
    print(f'  {mark} {k}')
