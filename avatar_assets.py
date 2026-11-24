"""飞意QQ 默认头像资源（原创 SVG，随项目分发）。

前端通过 /avatar/<id>.svg 使用，不依赖系统 emoji 字体。
用户资料里保存的是头像 id（如 av01），历史 emoji 头像会在启动时迁移。
"""

_AVATARS = {
    # 人物：纯色底 + 白色剪影
    'av01': (
        '<rect width="64" height="64" rx="16" fill="#4F8EF7"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
    ),
    # 人物：眼镜
    'av02': (
        '<rect width="64" height="64" rx="16" fill="#12B7F5"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<g fill="none" stroke="#17527D" stroke-width="1.8">'
        '<circle cx="28.4" cy="24" r="3.3"/><circle cx="35.6" cy="24" r="3.3"/><path d="M31.7 24h.6"/>'
        '</g>'
    ),
    # 人物：客服耳麦
    'av03': (
        '<rect width="64" height="64" rx="16" fill="#6C8CF5"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M22.4 26a9.6 9.6 0 0 1 19.2 0" fill="none" stroke="#2C48A8" stroke-width="2.2"/>'
        '<rect x="20.2" y="23.4" width="3.6" height="7.6" rx="1.8" fill="#2C48A8"/>'
        '<rect x="40.2" y="23.4" width="3.6" height="7.6" rx="1.8" fill="#2C48A8"/>'
    ),
    # 人物：领带
    'av04': (
        '<rect width="64" height="64" rx="16" fill="#F2994A"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M27.6 36.6l4.4 3.2 4.4-3.2" fill="none" stroke="#B4651F" stroke-width="1.8"/>'
        '<path d="M32 38.2l-3.6 4.2 2.2 10.4h2.8l2.2-10.4z" fill="#B4651F"/>'
    ),
    # 人物：短发
    'av05': (
        '<rect width="64" height="64" rx="16" fill="#27AE60"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M23.2 23.4c-.4-6 3.8-9.8 8.8-9.8s9.2 3.8 8.8 9.8c-2.4-2.8-5.2-4.1-8.8-4.1s-6.4 1.3-8.8 4.1z" fill="#145C36"/>'
    ),
    # 人物：棒球帽
    'av06': (
        '<rect width="64" height="64" rx="16" fill="#EB5757"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M22.8 23a9.2 9.2 0 0 1 18.4 0z" fill="#FFE3E3"/>'
        '<rect x="20.4" y="22.4" width="23.2" height="3" rx="1.5" fill="#7E2626"/>'
    ),
    # 人物：胡子
    'av07': (
        '<rect width="64" height="64" rx="16" fill="#2D9CDB"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M24.4 27.6c.3 6.6 3.3 10.2 7.6 10.2s7.3-3.6 7.6-10.2c-2.2 1.4-4.7 2.1-7.6 2.1s-5.4-.7-7.6-2.1z" fill="#14536F"/>'
    ),
    # 人物：围巾
    'av08': (
        '<rect width="64" height="64" rx="16" fill="#9B51E0"/>'
        '<rect x="28.6" y="29" width="6.8" height="9" rx="3.4" fill="#FFFFFF"/>'
        '<circle cx="32" cy="24" r="8.6" fill="#FFFFFF"/>'
        '<path d="M32 36.5c-9.5 0-17.2 7.7-17.2 17.2V64h34.4V53.7c0-9.5-7.7-17.2-17.2-17.2z" fill="#FFFFFF"/>'
        '<path d="M22.4 39.6c3.1 2.5 6.3 3.8 9.6 3.8s6.5-1.3 9.6-3.8l1.8 5.2c-3.5 2.8-7.3 4.2-11.4 4.2s-7.9-1.4-11.4-4.2z" fill="#F2C94C"/>'
    ),
    # 猫
    'av09': (
        '<rect width="64" height="64" rx="16" fill="#F2C94C"/>'
        '<path d="M18.4 18.6l2.8 12.6 7.6-8.6z" fill="#FFFFFF"/>'
        '<path d="M45.6 18.6l-2.8 12.6-7.6-8.6z" fill="#FFFFFF"/>'
        '<circle cx="32" cy="35" r="13.6" fill="#FFFFFF"/>'
        '<circle cx="27" cy="33" r="1.6" fill="#4A3720"/><circle cx="37" cy="33" r="1.6" fill="#4A3720"/>'
        '<path d="M32 37.4l-2 2.2h4z" fill="#F2994A"/>'
        '<path d="M32 39.6c-1 2-3 2.2-4.2 1.2M32 39.6c1 2 3 2.2 4.2 1.2" fill="none" stroke="#4A3720" stroke-width="1.4" stroke-linecap="round"/>'
        '<path d="M14.6 33h4.6M44.8 33h4.6" stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round"/>'
    ),
    # 熊
    'av10': (
        '<rect width="64" height="64" rx="16" fill="#A9745B"/>'
        '<circle cx="19.4" cy="20.4" r="6.6" fill="#FFFFFF"/><circle cx="44.6" cy="20.4" r="6.6" fill="#FFFFFF"/>'
        '<circle cx="19.4" cy="20.4" r="3.2" fill="#E5C7B5"/><circle cx="44.6" cy="20.4" r="3.2" fill="#E5C7B5"/>'
        '<circle cx="32" cy="34.6" r="14" fill="#FFFFFF"/>'
        '<circle cx="27" cy="32.4" r="1.7" fill="#4A3720"/><circle cx="37" cy="32.4" r="1.7" fill="#4A3720"/>'
        '<ellipse cx="32" cy="39.2" rx="5.4" ry="4.2" fill="#EFE0D4"/>'
        '<ellipse cx="32" cy="37.4" rx="2.1" ry="1.5" fill="#4A3720"/>'
        '<path d="M32 38.9v1.6M32 40.5c-.8 1-2.2 1-3 .2M32 40.5c.8 1 2.2 1 3 .2" fill="none" stroke="#6B4B36" stroke-width="1.3" stroke-linecap="round"/>'
    ),
    # 熊猫
    'av11': (
        '<rect width="64" height="64" rx="16" fill="#7BC6E8"/>'
        '<circle cx="19.2" cy="19.6" r="5.8" fill="#2F3A46"/><circle cx="44.8" cy="19.6" r="5.8" fill="#2F3A46"/>'
        '<circle cx="32" cy="34.4" r="14" fill="#FFFFFF"/>'
        '<ellipse cx="26.4" cy="32.4" rx="5" ry="6" fill="#2F3A46" transform="rotate(-18 26.4 32.4)"/>'
        '<ellipse cx="37.6" cy="32.4" rx="5" ry="6" fill="#2F3A46" transform="rotate(18 37.6 32.4)"/>'
        '<circle cx="26.8" cy="32.4" r="1.7" fill="#FFFFFF"/><circle cx="37.2" cy="32.4" r="1.7" fill="#FFFFFF"/>'
        '<ellipse cx="32" cy="39" rx="2.4" ry="1.7" fill="#2F3A46"/>'
        '<path d="M32 40.7v1.4M32 42.1c-.9 1-2.3 1-3.1.1M32 42.1c.9 1 2.3 1 3.1.1" fill="none" stroke="#2F3A46" stroke-width="1.3" stroke-linecap="round"/>'
    ),
    # 机器人
    'av12': (
        '<rect width="64" height="64" rx="16" fill="#6C5CE7"/>'
        '<path d="M32 13.6v4.2" stroke="#FFD166" stroke-width="2" stroke-linecap="round"/>'
        '<circle cx="32" cy="11.4" r="2.6" fill="#FFD166"/>'
        '<rect x="11.6" y="25" width="3.2" height="12" rx="1.6" fill="#D9D4FF"/>'
        '<rect x="49.2" y="25" width="3.2" height="12" rx="1.6" fill="#D9D4FF"/>'
        '<rect x="14.4" y="17.8" width="35.2" height="28" rx="9" fill="#FFFFFF"/>'
        '<rect x="21.6" y="26" width="6.4" height="8.4" rx="3.2" fill="#6C5CE7"/>'
        '<rect x="36" y="26" width="6.4" height="8.4" rx="3.2" fill="#6C5CE7"/>'
        '<rect x="27" y="38.6" width="10" height="3" rx="1.5" fill="#C9C2FF"/>'
    ),
}

DEFAULT_AVATAR = 'av01'
AVATAR_IDS = list(_AVATARS.keys())


def has_avatar(avatar_id):
    return str(avatar_id or '') in _AVATARS


def avatar_svg(avatar_id):
    """返回完整 SVG；未知 id 回退到默认头像。"""
    inner = _AVATARS.get(str(avatar_id or '')) or _AVATARS[DEFAULT_AVATAR]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            'width="64" height="64">' + inner + '</svg>')


def pick_avatar(seed):
    """按序号/字符串稳定地分配一个默认头像。"""
    if isinstance(seed, int):
        return AVATAR_IDS[seed % len(AVATAR_IDS)]
    h = 0
    for ch in str(seed or ''):
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return AVATAR_IDS[h % len(AVATAR_IDS)]
