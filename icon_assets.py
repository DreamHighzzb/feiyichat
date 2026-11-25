"""Tabler Icons 子集（MIT License），供飞意QQ界面图标使用。

原始数据：https://cdn.jsdelivr.net/npm/@tabler/icons@3.34.1/icons/outline/
仅保留项目需要的图标，压缩后内嵌，避免运行时依赖外网。
"""
import base64
import json
import lzma

_ICONS_B64 = (
    '/Td6WFoAAATm1rRGAgAhARwAAAAQz1jM4CUBBNxdAD2IiYZUoLrZjz9ldTYRhZwUqmfT4RNVl43bgXTzBRTJzTh7wjLwXAGEVckx'
    '4v75ICbeZ2cW62HoRXxhAGesiTh1qLx9ikt17HSdNGBHkSBHpBYCFjMPW24fcaGTbjo0bDOwqkYW7gjMJYQthvyOiFYldt/7DqWq'
    '/t43H2lFt2OLnRw5AYypgyC9TtcYhMDaZgzlurDpG0IbpJGlqAPz+zLUub88/8cg8dBcWyZo81RZC16UWR7E+15o6hVC5K1AmGYg'
    'P8eXj0Y54BjTFM4HZ0cMGp+9vuZTMrnEnNW2HA2bIdNifDWh+WjKcJIfIcevzLRzHSElu5qgpzyRKyOc9BG6Sk/XJJy3KZHJf78Z'
    'cXDaaDJiR3sEtLCRWfAg3XRc1poH2r+mfwG8GEZZjPVmv8OS6jM91piRsQ9HRzTaADBlpl4fR7NraO0ycFTumEVwozTu6AQPiZIW'
    '3RvtudiSy2+Yev+oklzGy1sF2XAq9A9Tb7QNyevfLaGCbURHyeI+lytvYcAjiGrfyJQRzhgutRnhgmRecjYShctnFuzXaQD5WhvJ'
    '62DB9sYC6pI5FbC7FUtp/+z6LW+jnIZ8oKZ+NMcqB0eRaEgvsv/TyKmAjR72196coWmSCaP31fpjHkyrjhyl288y12tPAMm3Ldyb'
    'Bg+Gjb8xUxOFros13vJAqu5gQYkiegBkNHe9NlhZJ5BXv6TmLValkCOd/Qt+vt2SveH1cb3LzZtuqiOG1Ro8uqYBL8n9MY4nX1VH'
    'HoSJqLGgt9giwN8ITkrnQpjlWF6jz4kClfG6HDuP8+6RsvKdyH3pU6SVCk8G43JD0NUhJcVD9oYNH9EJOtvSBjusvpU0m0uNZRSo'
    '6f+QfUAv30E07eOPUMHCJDgpZkkYkrTXAqJYma5Q2hg/xf7p0rsyvm8DmM3GiBK7yERT0o0HzDjzTWKtvwS+cleOPGwfgufCPCTo'
    'aaePn6mvvBU7/D+zpW41wKwwODMc9Etdr/uz3oIzhr/fmzV8FD/5VzgHpakFCB6DEg8yyy4JNL9sVjb+VzIISeWlY8P5dkY/zaEJ'
    '6CwHzjsoQAdZjwQuMn/3qoCG8f1CgeeAM4/Ff3txv6i7i2ZClbcbAfSJ5UNCSBBFKQrVj2oCji5djLFod3WmEr8GPypDajnTLgzd'
    'dWed67zu7MaSqBcyIr6b/KCbKdQiqCIW2McBn6fuHWyBvnq0HIVjKh5+E/TtLnkTiIXtjPohpdI4Ygp96RdCCXLX53kHWgrg/9p+'
    'ZLaWkx3i22S8MJxrVXZ5KKX6AwSP5a/Pl3gmsgr97fe3KjuZM0KtIGaLvWlpQq0BmbUcrZyqO31OfSCS5t0BTXYffEd7V6OtjG3t'
    '6NQvdN2VH41I3zDx/LlhDmJhcnAR7bQ20AGqgM5Oj2W+nqHPceN9ncuuf6ud5eyenwhIlCmkH1PTMspJH+MvMtp4aS+lZs7aQP3w'
    'tiAa9EOOWv89UTKZ3Dizrts/bnSug/hcuNFmhx7KTkLzRVmFajDh9gvou9aVC7K/rBVl46XcZR13KduA6YiMjJQQYL+3noVlVJ1k'
    'vRmc97OoIQrbJEhYAEffwUHJgUcNox//pUQOY7UZvIR9dMyzrVYBoWRU+b4iTiGF5gji/Oujztj9zkDf5J3vDgsahv09ah0v4RYA'
    'ABeRDy7aMFqCAAH4CYJKAAB+W9kNscRn+wIAAAAABFla'
)

ICONS = json.loads(lzma.decompress(base64.b64decode(_ICONS_B64)).decode('utf-8'))

# 云盘相关图标（Tabler Icons v3.34.1，MIT），直接内联便于维护
_EXTRA_PATHS = {
    'folder': '<path d="M5 4h4l3 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2"/>',
    'folder-open': '<path d="M5 19l2.757 -7.351a1 1 0 0 1 .936 -.649h12.307a1 1 0 0 1 .986 1.164l-.996 5.211a2 2 0 0 1 -1.964 1.625h-14.026a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2h4l3 3h7a2 2 0 0 1 2 2v2"/>',
    'folder-plus': ('<path d="M12 19h-7a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2h4l3 3h7a2 2 0 0 1 2 2v3.5"/>'
                    '<path d="M16 19h6"/><path d="M19 16v6"/>'),
    'upload': ('<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"/>'
               '<path d="M7 9l5 -5l5 5"/><path d="M12 4l0 12"/>'),
    'trash': ('<path d="M4 7l16 0"/><path d="M10 11l0 6"/><path d="M14 11l0 6"/>'
              '<path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/>'
              '<path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>'),
    'arrow-left': '<path d="M5 12l14 0"/><path d="M5 12l6 6"/><path d="M5 12l6 -6"/>',
    'cloud': '<path d="M6.657 18c-2.572 0 -4.657 -2.007 -4.657 -4.483c0 -2.475 2.085 -4.482 4.657 -4.482c.393 -1.762 1.794 -3.2 3.675 -3.773c1.88 -.572 3.956 -.193 5.444 1c1.488 1.19 2.162 3.007 1.77 4.769h.99c1.913 0 3.464 1.56 3.464 3.486c0 1.927 -1.551 3.487 -3.465 3.487h-11.878"/>',
    'user': '<path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0"/><path d="M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/>',
    # 工单 —— 剪贴板勾选
    'ticket': ('<path d="M9 5h6a2 2 0 0 1 2 2v1h1a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-9a2 2 0 0 1 2 -2h1v-1a2 2 0 0 1 2 -2"/>'
               '<path d="M9 5a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v1H9z"/>'
               '<path d="M9 14l2 2l4 -4"/>'),
}
_ICON_TPL = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round">{}</svg>')
for _name, _paths in _EXTRA_PATHS.items():
    ICONS[_name] = _ICON_TPL.format(_paths)

# 完整 SVG（实心徽标，不走上面的描边模板）：favicon 闪动 + 未读/新消息红点。
# 通过现有 /icon/<name>.svg 路由输出，前端统一引用服务端资源。
_FULL_SVGS = {
    'msg-normal': ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                   '<rect width="64" height="64" rx="16" fill="#12b7f5"/>'
                   '<path d="M18 21h28a6 6 0 0 1 6 6v14a6 6 0 0 1-6 6H31l-11 8v-8h-2a6 6 0 0 1-6-6V27a6 6 0 0 1 6-6z" fill="#fff"/>'
                   '<circle cx="32" cy="34" r="5" fill="#12b7f5"/></svg>'),
    'msg-alert': ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                  '<rect width="64" height="64" rx="16" fill="#ff2d2d"/>'
                  '<path d="M14 20h36a6 6 0 0 1 6 6v15a6 6 0 0 1-6 6H31l-12 9v-9h-5a6 6 0 0 1-6-6V26a6 6 0 0 1 6-6z" fill="#fff"/></svg>'),
    'dot-red': ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                '<circle cx="32" cy="32" r="26" fill="#ff2d2d" stroke="#fff" stroke-width="4"/></svg>'),
}

# 设置页菜单图标：蓝底圆角方块 + 白色线性图形（与截图同风格）。
# 图形采用 Tabler Icons（MIT）的路径思路，内嵌服务端，离线可用。
_SET_STROKE = ('fill="none" stroke="#fff" stroke-width="2.4" '
               'stroke-linecap="round" stroke-linejoin="round"')
_SET_BG = '<rect width="64" height="64" rx="16" fill="#12b7f5"/>'


def _set_svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' +
            _SET_BG + '<g transform="translate(14 14) scale(1.5)" ' +
            _SET_STROKE + '>' + body + '</g></svg>')


_FULL_SVGS.update({
    # 个人资料 —— 手机/设备
    'set-profile': _set_svg('<rect x="7" y="3" width="10" height="18" rx="2"/>'
                            '<path d="M11 18h2"/>'),
    # 修改密码 —— 钥匙
    'set-password': _set_svg('<circle cx="12" cy="7" r="4"/>'
                             '<path d="M12 11v9"/><path d="M12 16h3"/><path d="M12 19h2"/>'),
    # 桌面通知 —— 铃铛
    'set-notify': _set_svg('<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>'
                           '<path d="M10 21h4"/>'),
    # 消息提示音 —— 音符
    'set-sound': _set_svg('<path d="M10 18V5l9-2v13"/>'
                          '<ellipse cx="7" cy="18" rx="3" ry="2.5"/>'
                          '<ellipse cx="16" cy="16" rx="3" ry="2.5"/>'),
    # 外观主题 —— 调色板（带斜杠，对应截图）
    'set-theme': _set_svg('<path d="M12 3a9 9 0 1 0 0 18c1 0 2-1 2-2s-1-2-2-2h-1a2 2 0 0 1 0-4h5a5 5 0 0 0 5-5c0-3.9-4-5-9-5z"/>'
                          '<circle cx="7.5" cy="11" r=".8" fill="#fff"/>'
                          '<circle cx="10" cy="7" r=".8" fill="#fff"/>'
                          '<circle cx="15" cy="7.5" r=".8" fill="#fff"/>'
                          '<path d="M3 3l18 18"/>'),
    # 退出登录 —— 门
    'set-logout': _set_svg('<rect x="6" y="3" width="10" height="18" rx="1"/>'
                           '<path d="M13 12h1"/><path d="M18 9l3 3-3 3"/><path d="M21 12h-6"/>'),
    # 诊断日志 —— 列表（管理员设置页入口）
    'set-diag': _set_svg('<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/>'
                         '<circle cx="4" cy="6" r=".8" fill="#fff"/>'
                         '<circle cx="4" cy="12" r=".8" fill="#fff"/>'
                         '<circle cx="4" cy="18" r=".8" fill="#fff"/>'),
    # 权限与限制 —— 滑杆
    'set-permission': _set_svg('<path d="M4 7h16"/><path d="M4 17h16"/>'
                               '<circle cx="9" cy="7" r="2.2" fill="#1e88c7" stroke="#fff"/>'
                               '<circle cx="15" cy="17" r="2.2" fill="#1e88c7" stroke="#fff"/>'),
    # 文件审核 —— 勾选清单
    'set-review': _set_svg('<rect x="5" y="4" width="14" height="16" rx="2"/>'
                           '<path d="M8 9l1.5 1.5L12 8"/><path d="M8 15l1.5 1.5L12 14"/>'
                           '<path d="M14 9h3"/><path d="M14 15h3"/>'),
})
for _n, _s in _FULL_SVGS.items():
    ICONS[_n] = _s


def icon_svg(name):
    """返回指定图标的完整 SVG 字符串；不存在时返回空串。"""
    return ICONS.get(str(name or ''), '')


def has_icon(name):
    return str(name or '') in ICONS
