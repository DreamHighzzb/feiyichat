"""飞意QQ - Flask + Socket.IO 聊天服务

功能：注册登录、好友/好友申请、群组、私聊/群聊、离线消息、表情、文件发送。
数据以 JSON 文件保存在 data/ 目录，重启不丢。
"""

import hashlib
import json
import mimetypes
import os
import re
import secrets
import sys  # 新增：用于获取打包后的运行路径
import threading
import time
import uuid
from collections import deque
from urllib.parse import quote

from flask import (Flask, Response, jsonify, render_template, request,
                   send_file, send_from_directory)
from flask_socketio import SocketIO, emit

try:
    import emoji_assets
except ImportError:
    emoji_assets = None

try:
    import icon_assets
except ImportError:
    icon_assets = None

try:
    import avatar_assets
except ImportError:
    avatar_assets = None

# ---------------------------------------------------------------------------
# 路径配置（适配开发环境和 PyInstaller 打包后的环境）
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # 运行打包后的 exe 时
    # 1. 模板文件在 PyInstaller 的临时解压目录 (sys._MEIPASS)
    BUNDLE_DIR = sys._MEIPASS
    # 2. 数据文件应在 exe 所在目录，防止重启丢失
    EXE_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BUNDLE_DIR

TEMPLATE_DIR = os.path.join(BUNDLE_DIR, 'templates')
UPLOAD_DIR = os.path.join(EXE_DIR, 'uploads')
# 聊天附件按来源环境分目录：内网 uploads/in，外网 uploads/out
UPLOAD_IN_DIR = os.path.join(UPLOAD_DIR, 'in')
UPLOAD_OUT_DIR = os.path.join(UPLOAD_DIR, 'out')
DATA_DIR = os.path.join(EXE_DIR, 'data')
CONFIG_PATH = os.path.join(EXE_DIR, 'config.json')
# 公共盘 / 个人盘的实际文件目录（文件名用 id，避免路径穿越）
DRIVE_ROOT = os.path.join(EXE_DIR, 'drive')
DRIVE_PUBLIC_DIR = os.path.join(DRIVE_ROOT, 'public')
DRIVE_PRIVATE_DIR = os.path.join(DRIVE_ROOT, 'private')

for _d in (UPLOAD_DIR, UPLOAD_IN_DIR, UPLOAD_OUT_DIR,
           DATA_DIR, DRIVE_PUBLIC_DIR, DRIVE_PRIVATE_DIR):
    os.makedirs(_d, exist_ok=True)

DEFAULT_CONFIG = {
    'server': {
        'host': '0.0.0.0',
        'port': 5222,
    },
    'upload': {
        'internal_max_mb': 20,
        'external_max_mb': 1024,
        'force_scope': None,
        'internal_hosts': ['localhost', '127.0.0.1'],
        'external_hosts': [],
        'internal_ip_prefixes': [
            '127.', '10.', '192.168.', '169.254.',
            '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.',
        ],
    },
    # 盘上传独立上限（MB）。null = 跟随 upload 的内外网限制；填数字则覆盖。
    # 个人盘可再按内外网分别配置；0 = 不限制上传（下载不受影响）。
    'drive': {
        'public_max_mb': None,
        'private_max_mb': None,
        'private_internal_max_mb': None,
        'private_external_max_mb': None,
    },
}


def _deep_merge(base, override):
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    cfg = DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            cfg = _deep_merge(DEFAULT_CONFIG, json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        print('[WARN] 读取 config.json 失败，使用默认配置:', e)
    return cfg


CONFIG = load_config()
UPLOAD_CFG = CONFIG.get('upload') or {}
DRIVE_CFG = CONFIG.get('drive') or {}


def _mb_to_bytes(value, default_mb):
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = float(default_mb)
    if n <= 0:
        n = float(default_mb)
    return int(n * 1024 * 1024)


INTERNAL_UPLOAD_MAX = _mb_to_bytes(UPLOAD_CFG.get('internal_max_mb', 20), 20)
EXTERNAL_UPLOAD_MAX = _mb_to_bytes(UPLOAD_CFG.get('external_max_mb', 1024), 1024)


def _configured_drive_max(scope):
    """读取盘独立配置；未配置或配置无效时返回 None，表示沿用内外网限制。"""
    key = 'public_max_mb' if scope == 'public' else 'private_max_mb'
    raw = DRIVE_CFG.get(key)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    return int(n * 1024 * 1024) if n > 0 else None


def _drive_net_max(scope, net):
    """个人盘内外网专属配置：None=未配置（回退），0=禁止上传，>0=限制字节数。"""
    if scope != 'private' or net not in ('internal', 'external'):
        return None
    raw = DRIVE_CFG.get('private_%s_max_mb' % net)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return 0 if n == 0 else int(n * 1024 * 1024)


MAX_UPLOAD_ENVELOPE = max(INTERNAL_UPLOAD_MAX, EXTERNAL_UPLOAD_MAX,
                          _configured_drive_max('public') or 0,
                          _configured_drive_max('private') or 0) + 8 * 1024 * 1024
MAX_FILE_SIZE = EXTERNAL_UPLOAD_MAX  # 兼容旧变量名

MAX_FILES_PER_MSG = 5
HISTORY_LIMIT = 300
DEFAULT_PASSWORD = '123456'   # 老账号迁移后的初始密码

# 静态资源目录：打包版优先读 exe 同目录的外部 static（存在 app.js 时），
# 这样以后更新前端只需替换 exe 旁边的 static/app.js，无需重新打包 exe。
_STATIC_DIR = os.path.join(BUNDLE_DIR, 'static')
if getattr(sys, 'frozen', False):
    _EXT_STATIC = os.path.join(EXE_DIR, 'static')
    if os.path.isfile(os.path.join(_EXT_STATIC, 'app.js')):
        _STATIC_DIR = _EXT_STATIC
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=_STATIC_DIR)
app.config['SECRET_KEY'] = 'feiyi-chat-secret-key'


def _asset_ver(filename):
    """用静态文件 mtime 生成版本号，改了 JS/CSS 浏览器自动取新版，免手动强刷。"""
    try:
        return str(int(os.path.getmtime(os.path.join(_STATIC_DIR, filename))))
    except OSError:
        return '0'


@app.context_processor
def _inject_asset_ver():
    return {'asset_ver': {
        'js': _asset_ver('app.js'),
        'css': _asset_ver('app.css'),
    }}
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_ENVELOPE


def request_ip():
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or ''


def upload_scope():
    """返回 internal / external。

    严格按客户端真实 IP 判定（与群聊/私聊上传分 in/out 目录共用同一结果）：
    命中 internal_ip_prefixes（默认 192.168.）即内网 -> uploads/in；其余一律外网
    -> uploads/out。host 不参与内外网判定，避免本机访问 / 反向代理时 host 为
    localhost 把外网文件误判成内网。需要强制时用 config 的 force_scope。
    """
    force = str(UPLOAD_CFG.get('force_scope') or '').strip().lower()
    if force in ('internal', 'external'):
        return force
    ip = request_ip()
    prefixes = [str(x).strip() for x in (UPLOAD_CFG.get('internal_ip_prefixes') or []) if str(x).strip()]
    if not prefixes:
        prefixes = ['192.168.']
    if ip and any(ip.startswith(p) for p in prefixes):
        return 'internal'
    return 'external'


def upload_limit_bytes():
    return INTERNAL_UPLOAD_MAX if upload_scope() == 'internal' else EXTERNAL_UPLOAD_MAX


def size_text(n):
    mb = n / float(1024 * 1024)
    return ('%d MB' % int(mb)) if abs(mb - int(mb)) < 0.01 else ('%.1f MB' % mb)


def upload_limit_text():
    return size_text(upload_limit_bytes())


def drive_limit_bytes(scope):
    """公共盘 / 个人盘单文件上限；个人盘按当前内外网分别取配置。
    返回 0 表示禁止上传，正数表示独立上限，未配置时沿用内外网聊天上传限制。"""
    net_max = _drive_net_max(scope, upload_scope())
    if net_max is not None:
        return net_max
    return _configured_drive_max(scope) or upload_limit_bytes()


def drive_limit_text(scope):
    value = drive_limit_bytes(scope)
    return '禁止上传' if value == 0 else size_text(value)

# 强制指定 threading 模式，避免打包后缺少 eventlet/gevent 导致报错。
# CORS 收敛到同源：前端与接口同源部署，无需跨域；通配符会让恶意站点也能调用接口。
socketio = SocketIO(app, cors_allowed_origins=[], async_mode='threading')

COLORS = ['#12B7F5', '#FF6B6B', '#4ECDC4', '#F7B731', '#A55EEA',
          '#26DE81', '#FD9644', '#778BEB', '#E056FD', '#63CDDA',
          '#F368A0', '#5F8FEF']

LOCK = threading.RLock()
USERS = {}       # sid -> uid
UID2SIDS = {}    # uid -> set(sid)，同一账号可内网/外网多端同时在线
TOKENS = {}      # token -> uid，登录签发的会话凭据（内存态，重启后需重新登录）

# 群通知机器人 Webhook：密钥存 groups.json，调用频次只做内存限流
WEBHOOK_PATH = '/api/webhook/'
WEBHOOK_LIMIT_PER_MIN = 30
WEBHOOK_LOCK = threading.Lock()
WEBHOOK_HITS = {}


def issue_token(uid):
    """为 uid 签发一个新 token。同一账号可多端登录，各自持有不同 token。"""
    token = secrets.token_urlsafe(32)
    TOKENS[token] = uid
    return token


def token_uid(token):
    """校验 token 并返回对应 uid；无效/已停用账号返回空串。"""
    token = str(token or '').strip()
    uid = TOKENS.get(token)
    if not uid:
        return ''
    user = USERS_DB.get(uid)
    if not user or user.get('deleted'):
        TOKENS.pop(token, None)
        return ''
    return uid


def revoke_uid_tokens(uid):
    """账号被删除时吊销其全部 token。"""
    for t, u in list(TOKENS.items()):
        if u == uid:
            TOKENS.pop(t, None)


def request_token():
    """从请求头或参数中取 token（兼容 FormData 上传无法自定义 header 的情况）。"""
    return (request.headers.get('X-Token') or
            request.args.get('token') or
            request.cookies.get('feiyi_token') or
            (request.form.get('token') if request.method == 'POST' else '') or '')


def caller_uid():
    """当前请求的真实操作者 uid（来自 token）。未登录返回空串。"""
    return token_uid(request_token())


def is_online(uid):
    return bool(UID2SIDS.get(uid))


def sids_of(uid):
    return list(UID2SIDS.get(uid) or ())


def emit_uid(uid, event, data=None):
    """把事件推给该账号的全部在线端（多端同步的关键）。"""
    payload = data if data is not None else {}
    for sid in sids_of(uid):
        socketio.emit(event, payload, to=sid)


# ---------------------------------------------------------------------------
# 密码：PBKDF2-HMAC-SHA256 + 随机盐，库里只存 salt:hash
# ---------------------------------------------------------------------------
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', str(password).encode('utf-8'),
                                 bytes.fromhex(salt), 120000).hex()
    return salt + ':' + digest


def verify_password(password, stored):
    if not stored or ':' not in stored:
        return False
    salt, _ = stored.split(':', 1)
    try:
        return secrets.compare_digest(hash_password(password, salt), stored)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------
def load_json(name, default):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        print('[WARN] 读取 %s 失败: %s' % (name, exc))
        return default


def save_json(name, data):
    # 紧凑写入：indent 会让消息文件膨胀数倍，且每次全量重写，去掉后体积/CPU 均显著下降
    path = os.path.join(DATA_DIR, name)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


USERS_DB = load_json('users.json', {})
FRIENDS = load_json('friends.json', {})
REQUESTS = load_json('requests.json', [])
GROUPS = load_json('groups.json', {})
MESSAGES = load_json('messages.json', [])
READS = load_json('reads.json', {})
DRIVE = load_json('drive.json', {})

# 老数据迁移：补默认密码、最早注册的账号作为管理员、emoji 头像换成默认头像资源
with LOCK:
    migrated = False
    admin_uid = next((u.get('uid') for u in USERS_DB.values() if u.get('isAdmin')), None)
    ordered = sorted(USERS_DB.values(), key=lambda u: u.get('created', 0))
    for u in ordered:
        if not u.get('pass'):
            u['pass'] = hash_password(DEFAULT_PASSWORD)
            migrated = True
        if not admin_uid:
            u['isAdmin'] = True
            admin_uid = u['uid']
            migrated = True
        if avatar_assets and not avatar_assets.has_avatar(u.get('avatar')):
            u['avatar'] = avatar_assets.pick_avatar(u.get('uid') or u.get('nick') or '')
            migrated = True
    if admin_uid:
        FRIENDS.setdefault(admin_uid, [])
        READS.setdefault(admin_uid, {})
    if migrated:
        try:
            save_json('users.json', USERS_DB)
            save_json('friends.json', FRIENDS)
            save_json('reads.json', READS)
        except OSError as exc:
            print('[WARN] 迁移数据写入失败（将在下次保存时重试）:', exc)


def persist(name):
    save_json(name, {
        'users.json': USERS_DB,
        'friends.json': FRIENDS,
        'requests.json': REQUESTS,
        'groups.json': GROUPS,
        'messages.json': MESSAGES,
        'reads.json': READS,
        'drive.json': DRIVE,
    }[name])


def now():
    return time.strftime('%H:%M')


def public_user(uid, online=True):
    u = USERS_DB.get(uid)
    if not u:
        return None
    out = {
        'uid': uid, 'nick': u.get('nick', ''), 'color': u.get('color', COLORS[0]),
        'avatar': u.get('avatar', '🙂'), 'sig': u.get('sig', ''), 'online': online,
        'isAdmin': bool(u.get('isAdmin')),
    }
    return out


def pair_key(a, b):
    return 'p:' + ':'.join(sorted([a, b]))


def group_key(gid):
    return 'g:' + str(gid)


def channel_title(ch, me):
    if ch.startswith('g:'):
        g = GROUPS.get(ch[2:])
        return {'title': (g or {}).get('name', '群聊'), 'color': (g or {}).get('color', '#12B7F5'),
                'avatar': 'group', 'type': 'group', 'peer': ch[2:]}
    ids = [x for x in ch[2:].split(':') if x and x != me]
    uid = ids[0] if ids else me
    u = public_user(uid, is_online(uid)) or {'nick': '未知用户', 'color': '#999', 'avatar': '🙂'}
    return {'title': u['nick'], 'color': u['color'], 'avatar': u['avatar'],
            'type': 'private', 'peer': uid}


def is_group_manager(uid, g):
    """群主或系统管理员可以配置群机器人。"""
    if not uid or not g:
        return False
    return g.get('owner') == uid or bool((USERS_DB.get(uid) or {}).get('isAdmin'))


def bot_config(g):
    return (g or {}).get('bot') or {}


def find_group_by_webhook_key(key):
    """按密钥反查群；用常量时间比较避免计时侧信道。"""
    if not key:
        return None, None
    for gid, g in GROUPS.items():
        saved = str(bot_config(g).get('key') or '')
        if saved and secrets.compare_digest(saved, str(key)):
            return gid, g
    return None, None


def bot_payload(gid, uid):
    """给前端的机器人配置；密钥只对群主/管理员可见。"""
    g = GROUPS.get(gid) or {}
    bot = bot_config(g)
    can_manage = is_group_manager(uid, g)
    out = {
        'enabled': bool(bot.get('enabled')),
        'name': str(bot.get('name') or '通知机器人'),
        'canManage': can_manage,
    }
    if can_manage:
        key = str(bot.get('key') or '')
        out['key'] = key
        out['url'] = (request.host_url.rstrip('/') + WEBHOOK_PATH + key) if key else ''
    return out


def webhook_text(data):
    """兼容企业微信 text/markdown 格式和简写的 {"text":"..."}。"""
    data = data or {}
    mt = str(data.get('msgtype') or 'text').lower()
    if mt == 'markdown':
        raw = data.get('markdown')
    elif mt == 'text':
        raw = data.get('text')
    else:
        raw = data.get('content') or data.get('text')
    if isinstance(raw, dict):
        raw = raw.get('content')
    return str(raw or '').strip()[:4000]


def my_channels(uid):
    chans = set()
    for fid in FRIENDS.get(uid, []):
        chans.add(pair_key(uid, fid))
    for gid, g in GROUPS.items():
        if uid in g.get('members', []):
            chans.add(group_key(gid))
    for m in MESSAGES:
        if m.get('from') == uid or (m.get('ch', '').startswith('p:') and uid in m['ch'].split(':')):
            chans.add(m['ch'])
    return chans


def chat_state(uid):
    """一次遍历 MESSAGES 同时算出未读数与会话摘要。
    旧实现是「每个会话 × 全部消息」的嵌套循环，50 人群一条消息可达数百万次比较；
    这里把复杂度降到 O(消息数 + 会话数)。返回 (unread_dict, summaries)。
    """
    reads = READS.get(uid, {})
    chans = set()
    for fid in FRIENDS.get(uid, []):
        chans.add(pair_key(uid, fid))
    for gid, g in GROUPS.items():
        if uid in g.get('members', []):
            chans.add(group_key(gid))
    # 先把「属于该用户的会话」完整收集好，再统计。
    # 旧实现边遍历边往 chans 里加，并且对所有消息都计未读，
    # 导致别人群聊/私聊的消息也被算成自己的未读（列表无未读但任务栏有红点）。
    # 私聊只要自己是参与者就保留入口（即使已不是好友）；
    # 群聊只认「当前还在群里」——退群后即使自己发过消息，也不能再留在列表里，
    # 否则点进去会被 can_access_ch 判为无权查看。
    for m in MESSAGES:
        ch = m.get('ch')
        if ch and ch.startswith('p:') and uid in ch[2:].split(':'):
            chans.add(ch)
    last_by_ch = {}
    unread_by_ch = {}
    for m in MESSAGES:
        ch = m.get('ch')
        if not ch or ch not in chans:
            continue
        frm = m.get('from')
        mts = m.get('mts', 0)
        prev = last_by_ch.get(ch)
        if prev is None or mts >= prev.get('mts', 0):
            last_by_ch[ch] = m
        if frm != uid and mts > reads.get(ch, 0):
            unread_by_ch[ch] = unread_by_ch.get(ch, 0) + 1

    items = []
    for ch in chans:
        info = channel_title(ch, uid)
        last = last_by_ch.get(ch)
        if not last:
            if not ch.startswith('g:'):
                continue
            preview = '进入群聊，打个招呼吧'
            last_mts = GROUPS.get(ch[2:], {}).get('created', 0)
            last_from = ''
        else:
            preview = last.get('text') or ('[文件] ' + (last.get('files') or [{}])[0].get('name', ''))
            last_mts = last.get('mts', 0)
            last_from = last.get('from')
        items.append({
            'ch': ch, 'title': info['title'], 'color': info['color'],
            'avatar': info['avatar'], 'type': info['type'], 'peer': info['peer'],
            'last': preview[:80], 'from': last_from, 'mts': last_mts,
            'unread': unread_by_ch.get(ch, 0),
        })
    items.sort(key=lambda x: x['mts'], reverse=True)
    return unread_by_ch, items[:80]


def unread_map(uid):
    return chat_state(uid)[0]


def chat_summaries(uid, state=None):
    if state is not None:
        return state[1]
    return chat_state(uid)[1]


def bootstrap(uid):
    u = USERS_DB.get(uid)
    if not u:
        return None
    friends = [public_user(fid, is_online(fid)) for fid in FRIENDS.get(uid, [])]
    friends = [f for f in friends if f]
    friends.sort(key=lambda f: (not f['online'], f['nick']))
    groups = []
    for gid, g in GROUPS.items():
        if uid in g.get('members', []):
            info = dict(g)
            info['memberInfo'] = [public_user(m, is_online(m)) for m in g.get('members', [])]
            info['memberInfo'] = [m for m in info['memberInfo'] if m]
            bot = bot_config(g)
            # 只下发状态/名称，Webhook 密钥走 /api/group/bot 单独取，避免泄露给普通成员
            info['bot'] = {'enabled': bool(bot.get('enabled')),
                           'name': str(bot.get('name') or '通知机器人'),
                           'canManage': is_group_manager(uid, g)}
            groups.append(info)
    incoming = [dict(r) for r in REQUESTS if r.get('to') == uid and r.get('status') == 'pending']
    outgoing = [dict(r) for r in REQUESTS if r.get('from') == uid and r.get('status') == 'pending']
    for r in incoming + outgoing:
        r['fromInfo'] = public_user(r['from'], is_online(r['from']))
        r['toInfo'] = public_user(r['to'], is_online(r['to']))
    out = {
        'me': public_user(uid, True),
        'friends': friends,
        'groups': groups,
        'requests': {'in': incoming, 'out': outgoing},
        'chats': chat_summaries(uid),
        'unread': unread_map(uid),
    }
    # 联系人直接展示全公司成员；管理员成员管理页也复用这份清单
    members = sorted(USERS_DB.values(), key=lambda x: x.get('created', 0))
    out['members'] = [public_user(x['uid'], is_online(x['uid'])) for x in members
                      if not x.get('deleted')]
    out['members'] = [m for m in out['members'] if m]
    out['members'].sort(key=lambda m: (not m['online'], not m['isAdmin'], m['nick']))
    return out


def notify(uids, event, data=None):
    """通知一组用户；每个 uid 的所有在线端都会收到。"""
    for uid in set(uids):
        emit_uid(uid, event, data)


def refresh_contacts(uids):
    for uid in set(uids):
        if not is_online(uid):
            continue
        payload = bootstrap(uid)
        if payload:
            emit_uid(uid, 'contacts', payload)


def broadcast_presence(uid, online):
    """在线/离线变化只广播一条轻量事件，让所有在线端就地更新状态。

    旧实现只 refresh_contacts(FRIENDS)，但联系人页展示的是全公司成员、群成员栏
    也带在线小绿点，非好友上线时先登录的账号不会收到刷新，会一直显示对方离线。
    """
    socketio.emit('presence', {'uid': uid, 'online': bool(online)})


# ---------------------------------------------------------------------------
# HTTP 接口
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


def api_ok(**kwargs):
    return jsonify(dict(ok=True, **kwargs))


def api_fail(msg, code=400):
    return jsonify({'ok': False, 'msg': msg}), code


@app.after_request
def _security_headers(resp):
    # 防止浏览器把下载的图片/文本误当作可执行内容；降低内联脚本执行风险
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return resp


def body():
    return request.get_json(silent=True) or {}


@app.route('/api/login', methods=['POST'])
def api_login():
    data = body()
    nick = str(data.get('nick') or '').strip()[:20]
    password = str(data.get('password') or '')
    uid = str(data.get('uid') or '').strip()[:64]
    if not nick:
        return api_fail('请输入姓名')
    if not password:
        return api_fail('请输入登录密码')
    with LOCK:
        # 首次启动没有任何账号：当前登录者自动成为管理员
        if not USERS_DB:
            uid = uuid.uuid4().hex
            USERS_DB[uid] = {
                'uid': uid, 'nick': nick, 'color': COLORS[0],
                'avatar': avatar_assets.pick_avatar(uid) if avatar_assets else '🙂',
                'sig': '这个人很懒，什么都没留下',
                'created': int(time.time() * 1000),
                'pass': hash_password(password), 'isAdmin': True,
            }
            FRIENDS[uid] = []
            READS[uid] = {}
            persist('users.json')
            persist('friends.json')
            persist('reads.json')
            return api_ok(uid=uid, token=issue_token(uid),
                          me=public_user(uid, True), firstAdmin=True)

        if uid and uid in USERS_DB and not USERS_DB[uid].get('deleted'):
            user = USERS_DB[uid]
        else:
            user = next((u for u in USERS_DB.values()
                         if not u.get('deleted') and u.get('nick') == nick), None)
            if not user:
                return api_fail('账号不存在，请联系管理员添加')
            uid = user['uid']
        if not verify_password(password, user.get('pass')):
            return api_fail('密码错误')
    return api_ok(uid=uid, token=issue_token(uid), me=public_user(uid, True))


@app.route('/api/admin/add_user', methods=['POST'])
def api_admin_add_user():
    """登录态管理员添加公司成员：管理员身份来自 token。"""
    data = body()
    admin_uid = caller_uid()
    nick = str(data.get('nick') or '').strip()[:20]
    password = str(data.get('password') or '')
    if not admin_uid:
        return api_fail('请先登录', 401)
    if not nick:
        return api_fail('请输入新成员姓名')
    if len(password) < 6:
        return api_fail('初始密码至少 6 位')
    with LOCK:
        admin = USERS_DB.get(admin_uid)
        if not admin or not admin.get('isAdmin'):
            return api_fail('只有管理员可以添加成员')
        if any(u.get('nick') == nick and not u.get('deleted') for u in USERS_DB.values()):
            return api_fail('该姓名已存在，请换一个')
        uid = uuid.uuid4().hex
        USERS_DB[uid] = {
            'uid': uid, 'nick': nick, 'color': COLORS[len(USERS_DB) % len(COLORS)],
            'avatar': avatar_assets.pick_avatar(len(USERS_DB)) if avatar_assets else '🙂',
            'sig': '这个人很懒，什么都没留下',
            'created': int(time.time() * 1000),
            'pass': hash_password(password), 'isAdmin': False,
        }
        FRIENDS[uid] = []
        READS[uid] = {}
        persist('users.json')
        persist('friends.json')
        persist('reads.json')
    refresh_contacts([admin_uid])
    return api_ok(uid=uid, user=public_user(uid, False))


@app.route('/api/admin/delete_user', methods=['POST'])
def api_admin_delete_user():
    """管理员删除成员：账号停用并踢下线；从其所在群移除，群主让位，空群删除；
    历史消息与个人盘文件保留。"""
    data = body()
    admin_uid = caller_uid()
    target = str(data.get('target') or '').strip()[:64]
    if not admin_uid:
        return api_fail('请先登录', 401)
    touched_groups = []  # (gid, 剩余成员列表, 被移除的成员列表)
    with LOCK:
        admin = USERS_DB.get(admin_uid)
        if not admin or not admin.get('isAdmin') or admin.get('deleted'):
            return api_fail('只有管理员可以删除成员')
        if target == admin_uid:
            return api_fail('不能删除自己')
        user = USERS_DB.get(target)
        if not user or user.get('deleted'):
            return api_fail('成员不存在或已删除')
        if user.get('isAdmin'):
            live_admins = [u for u in USERS_DB.values()
                           if u.get('isAdmin') and not u.get('deleted')]
            if len(live_admins) <= 1:
                return api_fail('不能删除最后一个管理员')
        nick = user.get('nick') or target
        user['deleted'] = True
        user['deletedAt'] = int(time.time() * 1000)
        revoke_uid_tokens(target)

        # 清理该成员所在的所有群：移除成员；群主让位给剩余第一位；空群直接删除。
        for gid, g in list(GROUPS.items()):
            members = g.get('members', [])
            if target not in members:
                continue
            remains = [m for m in members if m != target]
            if not remains:
                # 群里只有该成员，直接移除整个群
                GROUPS.pop(gid, None)
                touched_groups.append((gid, [], list(members)))
                continue
            g['members'] = remains
            if g.get('owner') == target:
                g['owner'] = remains[0]
            touched_groups.append((gid, remains, list(members)))
        persist('users.json')
        persist('groups.json')
    # 先通知该账号所有在线端，再断开；聊天历史与个人盘文件保留。
    sids = list(sids_of(target))
    for sid in sids:
        socketio.emit('force_logout', {'msg': '账号已被管理员删除'}, to=sid)
        try:
            socketio.disconnect(sid)
        except Exception:
            pass
    # 断线回调可能异步到达，这里立即清理在线映射，避免残留在线状态
    with LOCK:
        for sid in sids:
            USERS.pop(sid, None)
        UID2SIDS.pop(target, None)
    # 给受影响的群发系统消息，让剩余成员知晓成员变动 / 群主变更
    for gid, remains, _old in touched_groups:
        if remains:
            notify(remains, 'system_message',
                   {'text': '成员「%s」已被管理员移除' % nick, 'ch': group_key(gid)})
    refresh_contacts([uid for uid in USERS_DB
                      if uid != target and not USERS_DB[uid].get('deleted')])
    return api_ok(nick=nick, groupsAffected=len(touched_groups))


@app.route('/api/password', methods=['POST'])
def api_password():
    data = body()
    uid = caller_uid()
    old = str(data.get('oldPass') or '')
    new = str(data.get('newPass') or '')
    if not uid:
        return api_fail('请先登录', 401)
    if len(new) < 6:
        return api_fail('新密码至少 6 位')
    with LOCK:
        if not verify_password(old, USERS_DB[uid].get('pass')):
            return api_fail('原密码错误')
        USERS_DB[uid]['pass'] = hash_password(new)
        persist('users.json')
    return api_ok()


@app.route('/api/profile', methods=['POST'])
def api_profile():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    with LOCK:
        if 'nick' in data:
            nick = str(data['nick'] or '').strip()[:20]
            if not nick:
                return api_fail('昵称不能为空')
            USERS_DB[uid]['nick'] = nick
        if 'avatar' in data:
            aid = str(data['avatar'] or '')[:16]
            if avatar_assets and avatar_assets.has_avatar(aid):
                USERS_DB[uid]['avatar'] = aid
        if 'sig' in data:
            USERS_DB[uid]['sig'] = str(data['sig'] or '')[:80]
        persist('users.json')
    refresh_contacts([uid] + list(FRIENDS.get(uid, [])))
    return api_ok(me=public_user(uid, True))


@app.route('/api/users')
def api_users():
    q = str(request.args.get('q') or '').strip().lower()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    out = []
    for u in USERS_DB.values():
        if u['uid'] == uid or u.get('deleted'):
            continue
        if q and q not in u.get('nick', '').lower() and q not in u['uid'].lower():
            continue
        out.append(public_user(u['uid'], is_online(u['uid'])))
        if len(out) >= 60:
            break
    return api_ok(users=out)


@app.route('/api/members')
def api_members():
    """全公司成员（排除自己），供创建群聊时选择同事，不受搜索上限影响。
    includeDeleted=1 时额外带上已删除成员，仅管理员可用。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    include_deleted = str(request.args.get('includeDeleted') or '') == '1'
    if include_deleted and not USERS_DB.get(uid, {}).get('isAdmin'):
        return api_fail('无权查看已删除成员', 403)
    out = []
    for mid, user in USERS_DB.items():
        if mid == uid or (user.get('deleted') and not include_deleted):
            continue
        item = public_user(mid, is_online(mid))
        if not item:
            continue
        item['deleted'] = bool(user.get('deleted'))
        out.append(item)
    out.sort(key=lambda m: (m['deleted'], not m['online'], not m['isAdmin'], m['nick']))
    return api_ok(members=out)


@app.route('/api/friend/request', methods=['POST'])
def api_friend_request():
    data = body()
    a = caller_uid()
    b = str(data.get('to') or '')
    if not a:
        return api_fail('请先登录', 401)
    if a not in USERS_DB or b not in USERS_DB or a == b:
        return api_fail('用户不存在')
    if b in FRIENDS.get(a, []):
        return api_fail('你们已经是好友了')
    with LOCK:
        exists = next((r for r in REQUESTS if r['from'] == a and r['to'] == b
                       and r['status'] == 'pending'), None)
        if exists:
            return api_fail('好友申请已发送，等待对方确认')
        REQUESTS.append({
            'id': uuid.uuid4().hex, 'from': a, 'to': b,
            'note': str(data.get('note') or '')[:60], 'status': 'pending',
            'mts': int(time.time() * 1000),
        })
        persist('requests.json')
    notify([b], 'friend_request', {'msg': '%s 申请添加你为好友' % USERS_DB[a]['nick']})
    refresh_contacts([a, b])
    return api_ok()


@app.route('/api/friend/respond', methods=['POST'])
def api_friend_respond():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    rid = str(data.get('id') or '')
    accept = bool(data.get('accept'))
    with LOCK:
        r = next((x for x in REQUESTS if x['id'] == rid and x['to'] == uid
                  and x['status'] == 'pending'), None)
        if not r:
            return api_fail('申请不存在或已处理')
        r['status'] = 'accepted' if accept else 'rejected'
        a, b = r['from'], r['to']
        if accept:
            FRIENDS.setdefault(a, [])
            FRIENDS.setdefault(b, [])
            if b not in FRIENDS[a]:
                FRIENDS[a].append(b)
            if a not in FRIENDS[b]:
                FRIENDS[b].append(a)
            persist('friends.json')
        persist('requests.json')
    refresh_contacts([a, b])
    notify([a], 'system_message', {'text': '%s %s了你的好友申请' % (
        USERS_DB[b]['nick'], '同意' if accept else '拒绝')})
    return api_ok()


@app.route('/api/friend/remove', methods=['POST'])
def api_friend_remove():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    fid = str(data.get('fid') or '')
    with LOCK:
        FRIENDS[uid] = [x for x in FRIENDS.get(uid, []) if x != fid]
        FRIENDS[fid] = [x for x in FRIENDS.get(fid, []) if x != uid]
        persist('friends.json')
    refresh_contacts([uid, fid])
    return api_ok()


@app.route('/api/group/create', methods=['POST'])
def api_group_create():
    data = body()
    uid = caller_uid()
    name = str(data.get('name') or '').strip()[:30]
    members = [x for x in (data.get('members') or []) if x in USERS_DB and x != uid]
    if not uid:
        return api_fail('请先登录', 401)
    if not name:
        return api_fail('请输入群名称')
    gid = uuid.uuid4().hex[:12]
    with LOCK:
        GROUPS[gid] = {
            'id': gid, 'name': name, 'owner': uid,
            'members': [uid] + list(dict.fromkeys(members)),
            'color': COLORS[len(GROUPS) % len(COLORS)],
            'created': int(time.time() * 1000),
            'notice': '欢迎加入本群～',
        }
        persist('groups.json')
    refresh_contacts([uid] + members)
    notify([uid] + members, 'system_message', {'text': '群“%s”创建成功' % name, 'ch': group_key(gid)})
    return api_ok(gid=gid)


@app.route('/api/group/invite', methods=['POST'])
def api_group_invite():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    gid = str(data.get('gid') or '')
    g = GROUPS.get(gid)
    if not g or uid not in g.get('members', []):
        return api_fail('你没有权限邀请成员')
    members = [x for x in (data.get('members') or []) if x in USERS_DB and x not in g['members']]
    with LOCK:
        g['members'].extend(members)
        persist('groups.json')
    refresh_contacts([uid] + members)
    return api_ok(members=members)


@app.route('/api/group/leave', methods=['POST'])
def api_group_leave():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    gid = str(data.get('gid') or '')
    g = GROUPS.get(gid)
    if not g or uid not in g.get('members', []):
        return api_fail('你不在该群中')
    with LOCK:
        g['members'] = [x for x in g['members'] if x != uid]
        if not g['members']:
            GROUPS.pop(gid, None)
        elif g.get('owner') == uid:
            g['owner'] = g['members'][0]
        persist('groups.json')
    refresh_contacts([uid] + g.get('members', []))
    return api_ok()


@app.route('/api/group/bot', methods=['GET', 'POST'])
def api_group_bot():
    """群通知机器人配置：群主/管理员可开关、改名、重置密钥。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body() if request.method == 'POST' else {}
    gid = str((request.args.get('gid') if request.method == 'GET' else None)
              or data.get('gid') or '')
    g = GROUPS.get(gid)
    if not g or (uid not in g.get('members', []) and not is_group_manager(uid, g)):
        return api_fail('你不在该群中', 403)
    if request.method == 'GET':
        return api_ok(bot=bot_payload(gid, uid))
    if not is_group_manager(uid, g):
        return api_fail('只有群主或管理员可以配置通知机器人', 403)

    action = str(data.get('action') or 'enable').lower()
    with LOCK:
        bot = g.setdefault('bot', {'enabled': False, 'key': '',
                                   'name': '通知机器人', 'createdAt': int(time.time() * 1000)})
        if not bot.get('key'):
            bot['key'] = secrets.token_urlsafe(24)
        if action == 'enable':
            bot['enabled'] = True
        elif action == 'disable':
            bot['enabled'] = False
        elif action == 'rotate':
            bot['key'] = secrets.token_urlsafe(24)
            bot['enabled'] = True
        elif action == 'name':
            name = str(data.get('name') or '').strip()[:20]
            if not name:
                return api_fail('请输入机器人名称')
            bot['name'] = name
        else:
            return api_fail('未知操作')
        bot['updatedAt'] = int(time.time() * 1000)
        persist('groups.json')
    refresh_contacts(g.get('members', []))
    return api_ok(bot=bot_payload(gid, uid))


@app.route(WEBHOOK_PATH + '<key>', methods=['POST'])
def api_webhook_send(key):
    """外部系统无需登录，凭 Webhook 密钥向群发一条机器人消息。"""
    gid, g = find_group_by_webhook_key(key)
    if not g or not bot_config(g).get('enabled'):
        return jsonify({'ok': False, 'errcode': 1, 'errmsg': 'webhook 不存在或已停用'}), 404

    now_ts = time.time()
    with WEBHOOK_LOCK:
        hits = WEBHOOK_HITS.setdefault(str(key), deque())
        while hits and hits[0] <= now_ts - 60:
            hits.popleft()
        if len(hits) >= WEBHOOK_LIMIT_PER_MIN:
            return jsonify({'ok': False, 'errcode': 2,
                            'errmsg': '发送过于频繁，请稍后再试'}), 429
        hits.append(now_ts)

    data = body() or request.form.to_dict()
    text = webhook_text(data)
    if not text:
        return jsonify({'ok': False, 'errcode': 3, 'errmsg': '消息内容不能为空'}), 400

    bot = bot_config(g)
    msg = {
        'id': uuid.uuid4().hex, 'ch': group_key(gid),
        'from': 'bot:' + gid, 'fromNick': str(bot.get('name') or '通知机器人'),
        'color': '#7B8794', 'text': text, 'files': [], 'quote': None,
        'mentions': [], 'atAll': False, 'ts': now(), 'mts': int(time.time() * 1000),
    }
    with LOCK:
        MESSAGES.append(msg)
        if len(MESSAGES) > 20000:
            del MESSAGES[:2000]
        persist('messages.json')
    members = list(g.get('members') or [])
    notify(members, 'message', msg)
    for p in set(members):
        if p == msg['from'] or not is_online(p):
            continue
        st = chat_state(p)
        notify([p], 'unread', {'unread': st[0], 'chats': st[1]})
    return jsonify({'ok': True, 'errcode': 0, 'errmsg': 'ok'})


def can_access_ch(uid, ch):
    """会话归属校验：私聊双方之一、群聊成员之一才允许读取历史。"""
    if not uid or uid not in USERS_DB or not ch:
        return False
    if ch.startswith('p:'):
        return uid in [x for x in ch[2:].split(':') if x]
    if ch.startswith('g:'):
        g = GROUPS.get(ch[2:])
        return bool(g) and uid in g.get('members', [])
    return False


@app.route('/api/history')
def api_history():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    ch = str(request.args.get('ch') or '')
    if not can_access_ch(uid, ch):
        return api_fail('无权查看该会话', 403)
    msgs = [m for m in MESSAGES if m.get('ch') == ch][-HISTORY_LIMIT:]
    with LOCK:
        READS.setdefault(uid, {})[ch] = int(time.time() * 1000)
        persist('reads.json')
    st = chat_state(uid)
    notify([uid], 'unread', {'unread': st[0], 'chats': st[1]})
    return api_ok(messages=msgs)


@app.route('/api/read', methods=['POST'])
def api_read():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    ch = str(data.get('ch') or '')
    if not can_access_ch(uid, ch):
        return api_fail('无权查看该会话', 403)
    with LOCK:
        READS.setdefault(uid, {})[ch] = int(time.time() * 1000)
        persist('reads.json')
    st = chat_state(uid)
    notify([uid], 'unread', {'unread': st[0], 'chats': st[1]})
    return api_ok(unread=st[0])


def safe_name_part(s, limit=80):
    """把用户名/文件名清理成可安全用作磁盘文件名的片段。"""
    s = str(s or '').replace('\\', '/').split('/')[-1]
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', s)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:limit] or 'file'


# 可在浏览器同源执行的危险扩展名：上传时拒绝，避免存储型 XSS
DANGEROUS_EXTS = {
    # 可在浏览器同源直接执行脚本的类型 —— 存储型 XSS 的主要入口
    '.html', '.htm', '.xhtml', '.shtml', '.svg', '.js', '.mjs', '.jsx',
    '.vbs', '.hta', '.mhtml', '.xml',
    # 服务端脚本 / 可执行文件，聊天工具无理由传输
    '.php', '.php3', '.php4', '.php5', '.phtml', '.asp', '.aspx', '.jsp',
    '.cgi', '.pl', '.py', '.sh', '.bat', '.cmd', '.exe', '.msi', '.scr',
    '.jar', '.com',
}


def is_dangerous_name(name):
    ext = os.path.splitext(str(name or ''))[1].lower()
    return ext in DANGEROUS_EXTS


@app.route('/api/upload_config')
def api_upload_config():
    """让前端按当前访问环境显示并预校验单文件大小上限。"""
    limit = upload_limit_bytes()
    return api_ok(scope=upload_scope(), maxBytes=limit, maxMB=round(limit / (1024 * 1024), 1),
                  text=upload_limit_text(),
                  drive={
                      'public': {'maxBytes': drive_limit_bytes('public'),
                                 'text': drive_limit_text('public')},
                      'private': {'maxBytes': drive_limit_bytes('private'),
                                  'text': drive_limit_text('private')},
                  })


@app.route('/upload', methods=['POST'])
def upload():
    limit = upload_limit_bytes()
    declared = request.content_length or 0
    if declared > limit + 2 * 1024 * 1024:
        return api_fail('文件为空或超过 ' + upload_limit_text())
    f = request.files.get('file')
    if not f or not f.filename:
        return api_fail('没有选择文件')
    if is_dangerous_name(f.filename):
        return api_fail('出于安全考虑，不允许上传该类型文件')
    # 以发送者用户名为前缀，身份来自 token，服务端文件名形如「张三_报告.pdf」
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    user = USERS_DB.get(uid)
    prefix = safe_name_part((user or {}).get('nick') or '未知用户', 24)
    orig_name = f.filename
    ext = os.path.splitext(orig_name)[1].lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,8}', ext):
        ext = ''
    base = safe_name_part(os.path.splitext(orig_name)[0], 80)
    stem = prefix + '_' + base
    stored = stem + ext
    net_scope = upload_scope()
    base_dir = UPLOAD_IN_DIR if net_scope == 'internal' else UPLOAD_OUT_DIR
    url_prefix = 'in/' if net_scope == 'internal' else 'out/'
    path = os.path.join(base_dir, stored)
    if os.path.exists(path):
        n = 2
        while os.path.exists(os.path.join(base_dir, stem + '_' + str(n) + ext)):
            n += 1
        stored = stem + '_' + str(n) + ext
        path = os.path.join(base_dir, stored)
    f.save(path)
    size = os.path.getsize(path)
    if size > limit or size == 0:
        os.remove(path)
        return api_fail('文件为空或超过 ' + upload_limit_text())
    mime = f.mimetype or mimetypes.guess_type(orig_name)[0] or 'application/octet-stream'
    return api_ok(file={'url': '/uploads/' + url_prefix + quote(stored),
                        'name': orig_name, 'size': size, 'mime': mime})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # 新文件按内外网落在 in/out 子目录；旧文件仍在根目录，保持兼容。
    for base in (UPLOAD_IN_DIR, UPLOAD_OUT_DIR, UPLOAD_DIR):
        if os.path.isfile(os.path.join(base, filename)):
            # 历史遗留的危险文件也强制下载，杜绝同源内联执行（存储型 XSS）
            return send_from_directory(base, filename,
                                       as_attachment=is_dangerous_name(filename))
    return ('', 404)


# ---------------------------------------------------------------------------
# 公共盘 / 个人盘
#   元数据存 data/drive.json，实体文件按 id 存放：
#     drive/public/<file_id>         公共盘
#     drive/private/<uid>/<file_id>  个人盘（只有本人能读写）
#   磁盘文件名不含用户输入，彻底避免路径穿越。
# ---------------------------------------------------------------------------
def drive_scope_of(value):
    return value if value in ('public', 'private') else ''


def drive_container(scope, uid, create=False):
    if scope == 'public':
        if create:
            st = DRIVE.setdefault('public', {})
        else:
            st = DRIVE.get('public') or {}
    else:
        if create:
            st = DRIVE.setdefault('private', {}).setdefault(uid, {})
        else:
            st = (DRIVE.get('private') or {}).get(uid) or {}
    if create:
        st.setdefault('folders', {})
        st.setdefault('files', {})
    return st


def drive_disk_dir(scope, uid):
    if scope == 'public':
        return DRIVE_PUBLIC_DIR
    path = os.path.join(DRIVE_PRIVATE_DIR, uid)
    os.makedirs(path, exist_ok=True)
    return path


def clean_drive_name(name, limit=80):
    s = str(name or '').replace('\\', '/').split('/')[-1]
    s = re.sub(r'[\x00-\x1f<>:"|?*]', '', s).strip(' .')
    return s[:limit]


def drive_nick(uid):
    return (USERS_DB.get(uid) or {}).get('nick') or '未知用户'


def drive_auth(uid, sid=None):
    """盘接口鉴权：uid 必须来自 token 会话（调用方用 caller_uid 取得）。
    sid 仅作兼容保留，不再作为信任依据——攻击者可自行 join 拿到 sid。"""
    return bool(uid and uid in USERS_DB and not USERS_DB[uid].get('deleted'))


def drive_target_uid(uid, target):
    """个人盘访问目标：空/自己=本人；其他人仅管理员可读，None 表示拒绝。"""
    target = str(target or '').strip()
    if not target or target == uid:
        return uid
    if not USERS_DB.get(uid, {}).get('isAdmin') or target not in USERS_DB:
        return None
    return target


def drive_folder_chain(st, folder):
    """返回从根到当前目录的路径数组，顺带防止脏数据造成死循环。"""
    folders = st.get('folders') or {}
    chain, cur, seen = [], folder, set()
    while cur and cur in folders and cur not in seen:
        seen.add(cur)
        f = folders[cur]
        chain.append({'id': cur, 'name': f.get('name', '')})
        cur = f.get('parent') or ''
    chain.reverse()
    return chain


def drive_children(st, folder):
    folders = st.get('folders') or {}
    files = st.get('files') or {}
    out_f = [{'id': fid, 'name': f.get('name', ''), 'owner': f.get('owner', ''),
              'ownerNick': drive_nick(f.get('owner', '')), 'mts': f.get('mts', 0)}
             for fid, f in folders.items() if (f.get('parent') or '') == folder]
    out_f.sort(key=lambda x: x['name'].lower())
    out_files = []
    for fid, f in files.items():
        if (f.get('folder') or '') != folder:
            continue
        item = dict(f)
        item['id'] = fid
        item['ownerNick'] = drive_nick(f.get('owner', ''))
        out_files.append(item)
    out_files.sort(key=lambda x: x.get('mts', 0), reverse=True)
    return out_f, out_files


def notify_drive(scope, uid):
    """文件变动后刷新正在看盘的人。"""
    if scope == 'public':
        socketio.emit('drive_changed', {'scope': 'public'})
    else:
        emit_uid(uid, 'drive_changed', {'scope': 'private'})
        # 管理员可能正在查看该成员的个人盘，一起刷新（只读视图）
        for admin_uid, user in USERS_DB.items():
            if admin_uid != uid and user.get('isAdmin') and not user.get('deleted'):
                emit_uid(admin_uid, 'drive_changed', {'scope': 'private'})


@app.route('/api/drive')
def api_drive():
    uid = caller_uid()
    sid = str(request.args.get('sid') or '')
    scope = drive_scope_of(request.args.get('scope') or 'public')
    folder = str(request.args.get('folder') or '')[:32]
    target = str(request.args.get('target') or '')[:64]
    if not uid:
        return api_fail('请先登录', 401)
    if not scope:
        return api_fail('参数错误')
    owner_uid = uid if scope == 'public' else drive_target_uid(uid, target)
    if not owner_uid:
        return api_fail('无权查看该成员的个人盘', 403)
    st = drive_container(scope, owner_uid)
    if folder and folder not in (st.get('folders') or {}):
        folder = ''
    folders, files = drive_children(st, folder)
    total = sum(int(f.get('size') or 0) for f in (st.get('files') or {}).values())
    viewing_other = scope == 'private' and owner_uid != uid
    return api_ok(scope=scope, folder=folder, path=drive_folder_chain(st, folder),
                  folders=folders, files=files, total=total,
                  limitBytes=drive_limit_bytes(scope), limitText=drive_limit_text(scope),
                  isAdmin=bool(USERS_DB[uid].get('isAdmin')),
                  ownerUid=owner_uid, ownerNick=drive_nick(owner_uid),
                  viewingOther=viewing_other)


@app.route('/api/drive/folder', methods=['POST'])
def api_drive_folder():
    data = body()
    uid = caller_uid()
    sid = str(data.get('sid') or '')
    scope = drive_scope_of(data.get('scope'))
    name = clean_drive_name(data.get('name'), 40)
    parent = str(data.get('folder') or '')[:32]
    if not uid:
        return api_fail('请先登录', 401)
    if not scope:
        return api_fail('参数错误')
    if not name:
        return api_fail('请输入文件夹名称')
    with LOCK:
        st = drive_container(scope, uid, create=True)
        if parent and parent not in st['folders']:
            return api_fail('上级文件夹不存在')
        if any((f.get('parent') or '') == parent and f.get('name') == name
               for f in st['folders'].values()):
            return api_fail('当前目录已有同名文件夹')
        fid = uuid.uuid4().hex[:12]
        st['folders'][fid] = {'id': fid, 'name': name, 'parent': parent,
                              'owner': uid, 'mts': int(time.time() * 1000)}
        persist('drive.json')
    notify_drive(scope, uid)
    return api_ok(folder={'id': fid, 'name': name, 'parent': parent, 'owner': uid,
                          'ownerNick': drive_nick(uid), 'mts': int(time.time() * 1000)})


@app.route('/api/drive/upload', methods=['POST'])
def api_drive_upload():
    uid = caller_uid()
    sid = str(request.form.get('sid') or '')
    scope = drive_scope_of(request.form.get('scope') or 'public')
    if not scope:
        return api_fail('参数错误')
    limit = drive_limit_bytes(scope)
    limit_text = drive_limit_text(scope)
    if limit == 0:
        return api_fail('当前环境禁止上传文件到' +
                        ('个人盘' if scope == 'private' else '公共盘'))
    declared = request.content_length or 0
    if limit and declared > limit + 2 * 1024 * 1024:
        return api_fail('文件超过 ' + limit_text)
    parent = str(request.form.get('folder') or '')[:32]
    if not uid:
        return api_fail('请先登录', 401)
    f = request.files.get('file')
    if not f or not f.filename:
        return api_fail('没有选择文件')
    name = clean_drive_name(f.filename, 120)
    if not name:
        return api_fail('文件名无效')
    if is_dangerous_name(name):
        return api_fail('出于安全考虑，不允许上传该类型文件')
    fid = uuid.uuid4().hex
    path = os.path.join(drive_disk_dir(scope, uid), fid)
    f.save(path)
    size = os.path.getsize(path)
    if size == 0:
        os.remove(path)
        return api_fail('文件为空')
    if limit and size > limit:
        os.remove(path)
        return api_fail('文件超过 ' + limit_text)
    mime = f.mimetype or mimetypes.guess_type(name)[0] or 'application/octet-stream'
    meta = {'id': fid, 'name': name, 'folder': parent, 'size': size, 'mime': mime,
            'owner': uid, 'mts': int(time.time() * 1000)}
    with LOCK:
        st = drive_container(scope, uid, create=True)
        if parent and parent not in st['folders']:
            os.remove(path)
            return api_fail('上级文件夹不存在')
        st['files'][fid] = meta
        persist('drive.json')
    notify_drive(scope, uid)
    out = dict(meta)
    out['ownerNick'] = drive_nick(uid)
    return api_ok(file=out)


@app.route('/api/drive/download')
def api_drive_download():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    sid = str(request.args.get('sid') or '')
    scope = drive_scope_of(request.args.get('scope') or 'public')
    fid = str(request.args.get('id') or '')
    target = str(request.args.get('target') or '')[:64]
    if not scope:
        return api_fail('参数错误')
    owner_uid = uid if scope == 'public' else drive_target_uid(uid, target)
    if not owner_uid:
        return api_fail('无权查看该成员的个人盘', 403)
    if not re.fullmatch(r'[0-9a-f]{6,40}', fid or ''):
        return api_fail('文件不存在', 404)
    st = drive_container(scope, owner_uid)
    meta = (st.get('files') or {}).get(fid)
    if not meta:
        return api_fail('文件不存在或已删除', 404)
    path = os.path.join(drive_disk_dir(scope, owner_uid), fid)
    if not os.path.isfile(path):
        return api_fail('文件已被清理', 404)
    return send_file(path, as_attachment=True, download_name=meta.get('name') or fid,
                     mimetype=meta.get('mime') or 'application/octet-stream')


@app.route('/api/drive/delete', methods=['POST'])
def api_drive_delete():
    data = body()
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    sid = str(data.get('sid') or '')
    scope = drive_scope_of(data.get('scope'))
    target = str(data.get('target') or '')[:64]
    ident = str(data.get('id') or '')
    kind = 'folder' if data.get('kind') == 'folder' else 'file'
    if not scope:
        return api_fail('参数错误')
    owner_uid = uid if scope == 'public' else drive_target_uid(uid, target)
    if not owner_uid:
        return api_fail('无权删除该成员的个人盘文件', 403)
    with LOCK:
        st = drive_container(scope, owner_uid)
        if kind == 'file':
            meta = (st.get('files') or {}).get(ident)
            if not meta:
                return api_fail('文件不存在或已删除', 404)
            if scope == 'public' and not USERS_DB[uid].get('isAdmin'):
                return api_fail('只有管理员可以删除公共盘文件')
            st['files'].pop(ident, None)
            try:
                os.remove(os.path.join(drive_disk_dir(scope, owner_uid), ident))
            except OSError:
                pass
        else:
            folders = st.get('folders') or {}
            if ident not in folders:
                return api_fail('文件夹不存在', 404)
            if scope == 'public' and not USERS_DB[uid].get('isAdmin'):
                return api_fail('只有管理员可以删除公共盘文件夹')
            # 递归收集子目录（避免脏数据死循环）
            targets, stack, seen = [], [ident], set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                targets.append(cur)
                stack.extend([fid for fid, f in folders.items() if (f.get('parent') or '') == cur])
            for fid, f in list((st.get('files') or {}).items()):
                if (f.get('folder') or '') in targets:
                    st['files'].pop(fid, None)
                    try:
                        os.remove(os.path.join(drive_disk_dir(scope, owner_uid), fid))
                    except OSError:
                        pass
            for fid in targets:
                folders.pop(fid, None)
        persist('drive.json')
    notify_drive(scope, owner_uid)
    return api_ok()


@app.route('/emoji/<code>.svg')
def emoji_file(code):
    """从服务端表情资源输出 SVG（前端图标走此 URL，不依赖系统字体）。"""
    if not re.fullmatch(r'[0-9a-f]{4,8}', code or ''):
        return ('', 404)
    if not emoji_assets or not emoji_assets.has_emoji(code):
        return ('', 404)
    return Response(emoji_assets.emoji_svg(code), mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=86400'})


@app.route('/avatar/<avatar_id>.svg')
def avatar_file(avatar_id):
    """默认头像资源，客户端所有头像都走这里。"""
    if not avatar_assets or not re.fullmatch(r'av[0-9]{2}', avatar_id or ''):
        return ('', 404)
    return Response(avatar_assets.avatar_svg(avatar_id), mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=604800'})


@app.route('/icon/<name>.svg')
def icon_file(name):
    """从服务端输出 Tabler Icons 子集（前端界面图标统一走这里）。"""
    if not re.fullmatch(r'[a-z0-9-]{1,40}', name or ''):
        return ('', 404)
    if not icon_assets or not icon_assets.has_icon(name):
        return ('', 404)
    return Response(icon_assets.icon_svg(name), mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=86400'})


@app.errorhandler(413)
def too_large(e):
    try:
        if request.path.startswith('/api/drive'):
            tip = '文件太大，盘上传最多 ' + drive_limit_text(
                'private' if (request.form.get('scope') or request.args.get('scope')) == 'private' else 'public')
        else:
            tip = '文件太大，最多 ' + upload_limit_text()
    except Exception:
        tip = '文件太大'
    return api_fail(tip, 413)


# ---------------------------------------------------------------------------
# Socket.IO
# ---------------------------------------------------------------------------
def normalize_file(f):
    if not isinstance(f, dict):
        return None
    url = str(f.get('url') or '')
    if not url.startswith('/uploads/') or '..' in url:
        return None
    try:
        size = int(f.get('size') or 0)
    except (TypeError, ValueError):
        size = 0
    return {'url': url[:500], 'name': str(f.get('name') or 'file')[:200], 'size': size,
            'mime': str(f.get('mime') or 'application/octet-stream')[:100]}


def normalize_files(raw):
    if not isinstance(raw, list):
        return []
    return [x for x in (normalize_file(f) for f in raw[:MAX_FILES_PER_MSG]) if x]


def normalize_quote(raw, ch):
    """引用回复：以服务端原消息为准，避免伪造昵称和内容。"""
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get('id') or '').strip()[:64]
    if not mid:
        return None
    original = next((m for m in MESSAGES if m.get('id') == mid and m.get('ch') == ch), None)
    if not original:
        return None
    text = original.get('text') or ''
    if not text and original.get('files'):
        text = '[文件] ' + str(original['files'][0].get('name') or '')
    return {
        'id': mid,
        'from': original.get('from'),
        'fromNick': original.get('fromNick') or '',
        'text': text[:200],
    }


def normalize_mentions(raw, ch, uid, at_all=False):
    """@成员：只保留真实群成员并回填服务端昵称，防止伪造 uid / 昵称。
    @all 仅群主或系统管理员可用，通过后展开为全体群成员；返回 (mentions, at_all)。
    """
    if not ch.startswith('g:'):
        return [], False
    g = GROUPS.get(ch[2:])
    if not g or uid not in g.get('members', []):
        return [], False
    members = g.get('members', [])
    out, seen = [], set()

    # @all：仅群主可用，普通成员或系统管理员伪造 at_all 都不生效
    can_all = g.get('owner') == uid
    if at_all and can_all:
        for mid in members:
            if mid == uid or mid in seen or mid not in USERS_DB:
                continue
            if USERS_DB[mid].get('deleted'):
                continue
            seen.add(mid)
            out.append({'uid': mid, 'nick': USERS_DB[mid].get('nick') or '用户'})
        return out, True

    if not isinstance(raw, list):
        return [], False
    for x in raw[:20]:
        mid = str(x or '').strip()[:64]
        if not mid or mid == uid or mid in seen:
            continue
        if mid not in members or mid not in USERS_DB:
            continue
        seen.add(mid)
        out.append({'uid': mid, 'nick': USERS_DB[mid].get('nick') or '用户'})
    return out, False


@socketio.on('join')
def on_join(data):
    data = data or {}
    # 身份必须来自登录签发的 token，且 token 与声明的 uid 一致，杜绝冒用他人身份
    token = str(data.get('token') or '')
    uid = token_uid(token)
    claim_uid = str(data.get('uid') or '')
    if not uid or (claim_uid and claim_uid != uid):
        return emit('join_error', {'msg': '登录信息失效，请重新登录'})
    was_offline = not is_online(uid)
    USERS[request.sid] = uid
    UID2SIDS.setdefault(uid, set()).add(request.sid)
    emit('joined', {'uid': uid, 'sessions': len(UID2SIDS.get(uid) or ())})
    emit('contacts', bootstrap(uid))
    notify([uid], 'unread', {'unread': unread_map(uid), 'chats': chat_summaries(uid)})
    if was_offline:
        # 从离线变在线：广播给所有在线端（不只好友），A 先上线也能看到后上线的 B
        broadcast_presence(uid, True)


@socketio.on('chat')
def on_chat(data):
    uid = USERS.get(request.sid)
    if not uid:
        return
    data = data or {}
    ch = str(data.get('ch') or '')
    text = str(data.get('text') or '').strip()[:2000]
    files = normalize_files(data.get('files') or [])
    if not text and not files:
        return

    peers = []
    if ch.startswith('g:'):
        g = GROUPS.get(ch[2:])
        if not g or uid not in g.get('members', []):
            return emit('system_message', {'text': '你已不在该群中'})
        peers = [m for m in g['members'] if m != uid]
    elif ch.startswith('p:'):
        ids = [x for x in ch[2:].split(':') if x]
        if uid not in ids or len(ids) != 2:
            return emit('system_message', {'text': '会话无效'})
        other = ids[0] if ids[0] != uid else ids[1]
        # 公司成员之间不需要先加好友，联系人里点谁都能直接私聊
        if other not in USERS_DB or USERS_DB[other].get('deleted'):
            return emit('system_message', {'text': '对方账号不存在，无法发消息'})
        peers = [other]
    else:
        return

    quote = normalize_quote(data.get('quote'), ch)
    mentions, at_all = normalize_mentions(data.get('mentions'), ch, uid,
                                          bool(data.get('atAll')))
    me = public_user(uid, True)
    msg = {
        'id': uuid.uuid4().hex, 'ch': ch, 'from': uid, 'fromNick': me['nick'],
        'color': me['color'], 'text': text, 'files': files, 'quote': quote,
        'mentions': mentions, 'atAll': at_all,
        'ts': now(), 'mts': int(time.time() * 1000),
    }
    with LOCK:
        MESSAGES.append(msg)
        if len(MESSAGES) > 20000:
            del MESSAGES[:2000]
        persist('messages.json')
        # 只把发送者自己标记为已读（多端同步不会误报未读）。
        # 收件人必须由自己的客户端真正打开会话后调用 /api/read 才算已读，
        # 否则离线期间的消息会被提前标成已读，红点永远不出现。
        READS.setdefault(uid, {})[ch] = msg['mts']
        persist('reads.json')

    # 发送者的所有端都收到（内网发、外网同步显示），接收方同理
    emit_uid(uid, 'message', msg)
    notify(peers, 'message', msg)
    # 未读推送：去重；发送者自己不计未读；离线成员的未读在下次登录时重算，无需推送。
    # 每个收件人只做一次 chat_state 遍历（旧实现每人重复全表扫描 3 次）。
    for p in set(peers):
        if p == uid or not is_online(p):
            continue
        st = chat_state(p)
        notify([p], 'unread', {'unread': st[0], 'chats': st[1]})


@socketio.on('typing')
def on_typing(data):
    uid = USERS.get(request.sid)
    if not uid:
        return
    data = data or {}
    ch = str(data.get('ch') or '')
    if not ch.startswith(('p:', 'g:')):
        return
    peers = []
    if ch.startswith('g:'):
        g = GROUPS.get(ch[2:])
        if not g or uid not in g.get('members', []):
            return
        peers = [m for m in g['members'] if m != uid]
    else:
        ids = [x for x in ch[2:].split(':') if x]
        if uid not in ids or len(ids) != 2:
            return
        peers = [x for x in ids if x != uid]
    notify(peers, 'typing', {'ch': ch, 'uid': uid})


@socketio.on('disconnect')
def on_disconnect():
    uid = USERS.pop(request.sid, None)
    if not uid:
        return
    sids = UID2SIDS.get(uid)
    if sids:
        sids.discard(request.sid)
        if not sids:
            UID2SIDS.pop(uid, None)
    if not is_online(uid):
        # 只有该账号最后一端退出时才广播离线；所有在线端同步更新
        broadcast_presence(uid, False)


def _server_bind():
    """从 config.json 读取监听地址与端口，非法值回退默认。"""
    raw = CONFIG.get('server') or {}
    host = str(raw.get('host') or '0.0.0.0').strip() or '0.0.0.0'
    try:
        port = int(raw.get('port', 5222))
    except (TypeError, ValueError):
        port = 5222
    if not (1 <= port <= 65535):
        port = 5222
    return host, port


if __name__ == '__main__':
    bind_host, bind_port = _server_bind()
    print('[INFO] 模板目录:', TEMPLATE_DIR)
    print('[INFO] 数据目录:', DATA_DIR)
    print('[INFO] 服务地址: http://localhost:%d' % bind_port)
    socketio.run(app, host=bind_host, port=bind_port, allow_unsafe_werkzeug=True)