"""飞意QQ - Flask + Socket.IO 聊天服务

功能：注册登录、好友/好友申请、群组、私聊/群聊、离线消息、表情、文件发送。
数据以 JSON 文件保存在 data/ 目录，重启不丢。
"""

import hashlib
import json
import mimetypes
import os
import posixpath
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
        # 内网前缀：本环境内网为 192.168.*，外网为 172.16.*。
        # 注意：172.16.~172.31. 属于 RFC1918 私有段，但本环境是外网段，
        # 绝不能列入，否则一旦 config.json 丢失/重建，外网会被误判为内网，
        # 导致 external_enabled=false 的下载限制失效。
        'internal_ip_prefixes': [
            '127.', '10.', '192.168.', '169.254.',
        ],
        # 可信反向代理网段。默认为空 = 完全忽略 X-Forwarded-For（防伪造）。
        # 仅当服务确实部署在 nginx 等反代后，才填入代理机 IP 前缀，
        # 此时才会从 XFF 链路中解析真实客户端 IP。
        'trusted_proxy_prefixes': [],
    },
    # 盘上传上限（MB），支持内外网独立；0 = 禁止上传（下载不受影响）。
    # 旧字段 public_max_mb / private_max_mb / private_<net>_max_mb 仍兼容。
    'drive': {
        'public_max_mb': None,
        'public_internal_max_mb': None,
        'public_external_max_mb': None,
        'private_max_mb': None,
        'private_internal_max_mb': None,
        'private_external_max_mb': None,
    },
    # 下载开关：聊天附件 / 公共盘 / 个人盘，内外网独立。false 关闭下载。
    'download': {
        'internal_enabled': True,
        'external_enabled': True,
        'drive_public_internal_enabled': True,
        'drive_public_external_enabled': True,
        'drive_private_internal_enabled': True,
        'drive_private_external_enabled': True,
    },
    # 上传审核：enabled=true 时，超过 max_mb 的文件需管理员审核通过才可下载；
    # max_mb=0 表示所有文件都要审核。
    'review': {
        'enabled': False,
        'max_mb': 10,
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


def save_config(cfg):
    """原子写回 config.json（保留原文件里的中文 _说明 字段）。"""
    path = CONFIG_PATH
    tmp = path + '.tmp'
    try:
        # 尽量保留已有说明字段，避免管理员在文件里写的注释丢失
        try:
            with open(path, encoding='utf-8') as f:
                old = json.load(f)
            for k, v in old.items():
                if k.startswith('_') and k not in cfg:
                    cfg[k] = v
                elif isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    for sk, sv in v.items():
                        if sk.startswith('_') and sk not in cfg[k]:
                            cfg[k][sk] = sv
        except Exception:
            pass
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print('[WARN] 写回 config.json 失败:', e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


CONFIG = load_config()
UPLOAD_CFG = CONFIG.get('upload') or {}
DRIVE_CFG = CONFIG.get('drive') or {}
DOWNLOAD_CFG = CONFIG.get('download') or {}
REVIEW_CFG = CONFIG.get('review') or {}


def _mb_to_bytes(value, default_mb):
    """MB -> 字节。0 表示禁止上传（保留 0）；负数/无效值回退默认。"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = float(default_mb)
    if n < 0:
        n = float(default_mb)
    return 0 if n == 0 else int(n * 1024 * 1024)


def _cfg_num(dct, key):
    """取配置数值；None/空串/非数值返回 None。"""
    raw = dct.get(key)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    return None if n < 0 else int(n * 1024 * 1024)


def _chat_upload_max(net):
    """聊天附件上传上限（字节）。0=禁止上传（只能发文本/表情）。实时读取，支持热更新。"""
    key = 'internal_max_mb' if net == 'internal' else 'external_max_mb'
    default = 20 if net == 'internal' else 1024
    return _mb_to_bytes(UPLOAD_CFG.get(key, default), default)


def _drive_upload_max(scope, net):
    """盘上传上限（字节）。0=禁止上传；None=未配置（回退聊天限制）。实时读取。"""
    prefix = 'public' if scope == 'public' else 'private'
    # 新版：内外网独立字段优先；旧版：<scope>_max_mb 兜底
    value = _cfg_num(DRIVE_CFG, '%s_%s_max_mb' % (prefix, net))
    if value is None:
        value = _cfg_num(DRIVE_CFG, '%s_max_mb' % prefix)
    return value


def max_upload_envelope():
    """Flask MAX_CONTENT_LENGTH 用：取所有上传上限最大值 + 余量，实时计算。"""
    limits = [_chat_upload_max('internal'), _chat_upload_max('external')]
    for scope in ('public', 'private'):
        for net in ('internal', 'external'):
            v = _drive_upload_max(scope, net)
            limits.append(v if v is not None else _chat_upload_max(net))
    return max(limits) + 8 * 1024 * 1024

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
app.config['MAX_CONTENT_LENGTH'] = max_upload_envelope()


def request_ip():
    """客户端真实 IP（安全版）。

    X-Forwarded-For 是客户端可任意伪造的请求头。旧版无条件采信首段，
    导致外网用户加一个 `X-Forwarded-For: 192.168.1.1` 就被判为内网，
    直接绕过外网下载开关 / 上传限制。

    现在默认**完全忽略 XFF**，只认 TCP 层的 remote_addr。
    只有当 remote_addr 命中 upload.trusted_proxy_prefixes（显式配置的
    可信反向代理）时，才解析 XFF，并从右往左取第一个不属于代理网段的 IP
    （XFF 链路格式：client, proxy1, proxy2；右侧为后追加的代理）。
    """
    remote = request.remote_addr or ''
    proxies = [str(x).strip() for x in
               (UPLOAD_CFG.get('trusted_proxy_prefixes') or []) if str(x).strip()]
    trusted = any(remote.startswith(p) for p in proxies) if proxies else False
    if not trusted:
        return remote
    xff = request.headers.get('X-Forwarded-For', '')
    if not xff:
        return remote
    parts = [x.strip() for x in xff.split(',') if x.strip()]
    for ip in reversed(parts):
        if not any(ip.startswith(p) for p in proxies):
            return ip
    return remote


# ---------------------------------------------------------------------------
# 诊断日志：排查「外网下载被拒 / 内外网误判 / 代理 XFF 传错」。
# 记录到 data/diag.log（单行 JSON，滚动保留最近 N 条），同时输出到 stdout。
# 只记录影响判定的关键节点，并对相同结论做节流，避免刷屏。
# ---------------------------------------------------------------------------
DIAG_LOG_MAX = 500
DIAG_LOG_PATH = os.path.join(DATA_DIR, 'diag.log')
_diag_lock = threading.Lock()
_diag_last = {}


def _diag(event, **fields):
    rec = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'event': event}
    rec.update(fields)
    line = json.dumps(rec, ensure_ascii=False, separators=(',', ':'))
    try:
        with _diag_lock:
            # 节流：同 event + 同结论 2 秒内只写一条，避免每个附件都刷日志
            key = (event, str(fields.get('scope')), str(fields.get('allowed')),
                   str(fields.get('ip')))
            now = time.time()
            if now - _diag_last.get(key, 0) < 2:
                return
            _diag_last[key] = now
            with open(DIAG_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            try:
                if os.path.getsize(DIAG_LOG_PATH) > 512 * 1024:
                    with open(DIAG_LOG_PATH, encoding='utf-8') as f:
                        tail = f.readlines()[-DIAG_LOG_MAX:]
                    with open(DIAG_LOG_PATH, 'w', encoding='utf-8') as f:
                        f.writelines(tail)
            except OSError:
                pass
        print('[DIAG] ' + line, flush=True)
    except Exception:
        pass


def diag_recent(limit=100):
    try:
        with _diag_lock:
            with open(DIAG_LOG_PATH, encoding='utf-8') as f:
                lines = f.readlines()
        out = []
        for line in lines[-max(1, min(int(limit), DIAG_LOG_MAX)):]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(out))
    except Exception:
        return []


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
    hit = next((p for p in prefixes if ip and ip.startswith(p)), None)
    scope = 'internal' if hit else 'external'
    # 诊断：把 XFF 原始链路、remote_addr、命中前缀一起记下，便于排查代理误判。
    # 节流由 _diag 内部按 (event, scope, ip) 完成。
    _diag('scope', ip=ip, xff=request.headers.get('X-Forwarded-For', ''),
          remote=request.remote_addr or '', hit=hit or '', scope=scope,
          prefixes=','.join(prefixes))
    return scope


def _config_bool(value):
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', 'no', 'off', '')
    return value is not False


def download_allowed(channel='chat'):
    """下载开关：chat / drive_public / drive_private，内外网独立，实时读取。

    旧版只有 download.external_enabled（聊天附件外网）；新配置默认沿用并扩展。
    """
    net = upload_scope()
    if channel == 'chat':
        key = 'internal_enabled' if net == 'internal' else 'external_enabled'
        default = True
    else:
        prefix = 'drive_public' if channel == 'drive_public' else 'drive_private'
        key = '%s_%s_enabled' % (prefix, net)
        default = True
    value = DOWNLOAD_CFG.get(key, default)
    # 兼容旧配置：聊天外网仍用 external_enabled
    if channel == 'chat' and net == 'external' and 'external_enabled' not in DOWNLOAD_CFG and key != 'external_enabled':
        value = DOWNLOAD_CFG.get('external_enabled', True)
    allowed = _config_bool(value)
    _diag('download', scope=net, channel=channel, allowed=allowed,
          key=key, value=value, ip=request_ip())
    return allowed


DOWNLOAD_DENY_TIP = '当前为外网访问，管理员已关闭外网下载权限'


def download_deny_tip(channel='chat'):
    if channel == 'chat':
        return DOWNLOAD_DENY_TIP
    name = '公共盘' if channel == 'drive_public' else '个人盘'
    net = '外网' if upload_scope() == 'external' else '内网'
    return '管理员已关闭%s%s下载权限' % (net, name)


def upload_limit_bytes():
    return _chat_upload_max(upload_scope())


# ---------------------------------------------------------------------------
# 上传审核：开关打开后，达到阈值的文件需管理员审核通过才可下载。
# ---------------------------------------------------------------------------
def review_enabled():
    return _config_bool(REVIEW_CFG.get('enabled', False))


def review_threshold_bytes():
    n = REVIEW_CFG.get('max_mb', 10)
    try:
        n = float(n)
    except (TypeError, ValueError):
        n = 10
    return int(n * 1024 * 1024)  # 0=全部文件都需审核


def review_required(size):
    """是否需要对该文件审核。"""
    if not review_enabled():
        return False
    threshold = review_threshold_bytes()
    return threshold == 0 or (size or 0) >= threshold


def review_key_upload(stored_name):
    return 'upload:' + str(stored_name)


def review_key_drive(scope, owner_uid, fid):
    return 'drive:%s:%s:%s' % (scope, owner_uid, fid)


def review_status(key):
    """返回文件审核状态：approved / pending / rejected / none（无记录=历史文件，放行）。"""
    rec = REVIEW_FILES.get(key)
    if not rec:
        return 'approved'  # 审核功能开启前上传的历史文件默认放行
    return rec.get('status') or 'pending'


def review_set(key, meta, status='pending'):
    with LOCK:
        rec = dict(meta or {})
        rec['status'] = status
        rec['mts'] = int(time.time() * 1000)
        REVIEW_FILES[key] = rec
        persist('review.json')


def review_pending_count():
    return sum(1 for r in REVIEW_FILES.values() if r.get('status') == 'pending')


def notify_review_pending(key, name, owner_uid):
    """提醒所有在线管理员有新文件待审核。"""
    admins = [u.get('uid') for u in USERS_DB.values()
              if u.get('isAdmin') and not u.get('deleted') and u.get('uid')]
    payload = {'key': key, 'name': name, 'owner': owner_uid,
               'count': review_pending_count()}
    for uid in admins:
        emit_uid(uid, 'review_pending', payload)


def size_text(n):
    mb = n / float(1024 * 1024)
    return ('%d MB' % int(mb)) if abs(mb - int(mb)) < 0.01 else ('%.1f MB' % mb)


def upload_limit_text():
    return size_text(upload_limit_bytes())


def drive_limit_bytes(scope):
    """盘单文件上限（实时）。0=禁止上传，正数=上限，未配置回退聊天内外网限制。"""
    net = upload_scope()
    value = _drive_upload_max(scope, net)
    if value is None:
        value = _chat_upload_max(net)
    return value


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
TICKETS = load_json('tickets.json', {})   # 工单：tid -> 工单详情（含跟踪记录）
TICKET_READS = load_json('ticket_reads.json', {})  # uid -> {tid: 已读到的更新时间}
# 上传审核：key(文件标识) -> {name,size,mime,owner,status:pending|approved|rejected,mts,channel,path}
REVIEW_FILES = load_json('review.json', {})

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
        'tickets.json': TICKETS,
        'ticket_reads.json': TICKET_READS,
        'review.json': REVIEW_FILES,
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


# ---------------------------------------------------------------------------
# 工单：创建直派成员、需求编辑、状态流转、跟踪记录。
# 权限矩阵：
#   查看/跟踪：创建者、被指派人、管理员
#   编辑内容（标题/需求/优先级）：创建者或管理员（创建后仍可再次编辑）
#   改状态/改指派：管理员可改全部；普通成员只能改「指派给自己」的工单，
#                 且只能把指派改给其他成员（转派）
#   关闭/删除：创建者或管理员
# ---------------------------------------------------------------------------
TICKET_STATUSES = ('open', 'doing', 'done', 'closed')
TICKET_STATUS_TEXT = {'open': '待处理', 'doing': '处理中', 'done': '已完成', 'closed': '已关闭'}
TICKET_PRIORITIES = ('low', 'normal', 'high')
TICKET_PRIORITY_TEXT = {'low': '低', 'normal': '普通', 'high': '高'}
TICKET_DESC_MAX = 12000  # 需求正文长度（支持嵌入图片链接，放宽上限）


def is_admin_uid(uid):
    return bool((USERS_DB.get(uid) or {}).get('isAdmin'))


def ticket_people(t):
    """该工单的相关人：创建者 + 被指派人。"""
    return {x for x in (t.get('creator'), t.get('assignee')) if x}


def can_view_ticket(uid, t):
    """查看：所有登录成员都能看到全部工单（列表「全部」筛选看到所有）。"""
    return bool(uid and t)


def can_track_ticket(uid, t):
    """跟踪/操作：仅相关人（创建者、被指派人、管理员）。可见不等于可操作。"""
    if not uid or not t:
        return False
    if is_admin_uid(uid):
        return True
    return uid in ticket_people(t)


def can_edit_ticket(uid, t):
    """编辑工单内容（标题/需求/优先级）：创建者可再次编辑，管理员可改全部。"""
    if not uid or not t:
        return False
    return is_admin_uid(uid) or t.get('creator') == uid


def can_manage_assignment(uid, t):
    """改状态/改指派：管理员改全部；普通成员仅限指派给自己的工单（转派给别人）。"""
    if not uid or not t:
        return False
    if is_admin_uid(uid):
        return True
    return bool(t.get('assignee')) and t.get('assignee') == uid


def can_close_ticket(uid, t):
    """关闭/删除：仅创建者或系统管理员。"""
    if not uid or not t:
        return False
    if is_admin_uid(uid):
        return True
    return t.get('creator') == uid


def ticket_public(t, uid=None):
    """序列化单条工单给前端：补 nick/权限标记，隐藏内部字段。"""
    out = dict(t)
    out['creatorInfo'] = public_user(t.get('creator'), is_online(t.get('creator'))) or {
        'uid': t.get('creator'), 'nick': '未知用户', 'color': '#999', 'avatar': '🙂',
        'sig': '', 'online': False, 'isAdmin': False}
    out['assigneeInfo'] = public_user(t.get('assignee'), is_online(t.get('assignee'))) or {
        'uid': t.get('assignee'), 'nick': '未知用户', 'color': '#999', 'avatar': '🙂',
        'sig': '', 'online': False, 'isAdmin': False}
    tracks = []
    for tr in t.get('tracks', []):
        item = dict(tr)
        item['userInfo'] = public_user(tr.get('uid'), is_online(tr.get('uid'))) or {
            'uid': tr.get('uid'), 'nick': '未知用户', 'color': '#999', 'avatar': '🙂',
            'sig': '', 'online': False, 'isAdmin': False}
        tracks.append(item)
    out['tracks'] = tracks
    out['statusText'] = TICKET_STATUS_TEXT.get(t.get('status'), t.get('status'))
    out['priorityText'] = TICKET_PRIORITY_TEXT.get(t.get('priority'), t.get('priority'))
    if uid:
        out.update(ticket_flags(uid, t))
    return out


def ticket_flags(uid, t):
    """给单个工单附上当前用户的权限位。"""
    return {
        'canManage': can_close_ticket(uid, t),
        'canTrack': can_track_ticket(uid, t),
        'canEdit': can_edit_ticket(uid, t),
        'canManageAssign': can_manage_assignment(uid, t),
    }


def ticket_unread(uid):
    """每个用户相对已读时间有更新的相关工单 id 列表。"""
    reads = TICKET_READS.get(uid, {}) or {}
    out = []
    for tid, t in TICKETS.items():
        if uid not in ticket_people(t):
            continue
        if (t.get('updated') or 0) > (reads.get(tid) or 0):
            out.append(tid)
    return out


def ticket_notify(t, event, action, msg, exclude=(), assign_to=None, actor=None):
    """把工单变更推给相关人的所有在线端（含创建者/被指派人/管理员）。

    assign_to/actor 用于前端识别「这次是把我指派为新负责人」并弹出强提醒。
    """
    targets = set(ticket_people(t)) | {uid for uid, u in USERS_DB.items()
                                       if u.get('isAdmin') and not u.get('deleted')}
    targets -= {x for x in exclude if x}
    actor = actor or ''
    payload = {'id': t.get('id'), 'event': event, 'action': action,
               'msg': msg, 'title': t.get('title', ''),
               'assignTo': assign_to or '', 'actor': actor,
               'actorNick': ((USERS_DB.get(actor) or {}).get('nick') or actor)}
    for uid in targets:
        emit_uid(uid, 'ticket', payload)


def ticket_unread_all():
    return {uid: ticket_unread(uid) for uid in USERS_DB if not USERS_DB[uid].get('deleted')}


def notify_ticket_unread():
    """仅把每个人的未读工单 id 推给自己，便于清红点。"""
    for uid, ids in ticket_unread_all().items():
        emit_uid(uid, 'ticket_unread', {'ids': ids})


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
    net = upload_scope()
    return api_ok(
        scope=net, maxBytes=limit, maxMB=round(limit / (1024 * 1024), 1),
        text=('禁止上传，只能发文字和表情' if limit == 0 else upload_limit_text()),
        download={'allowed': download_allowed('chat'), 'tip': download_deny_tip('chat')},
        review={'enabled': review_enabled(), 'maxBytes': review_threshold_bytes(),
                'maxMB': round(review_threshold_bytes() / (1024 * 1024), 1),
                # 仅管理员拿待审数量：普通成员登录后不该看到审核红点
                'pending': review_pending_count() if (caller_uid() and is_admin_uid(caller_uid())) else 0},
        drive={
            'public': {'maxBytes': drive_limit_bytes('public'),
                       'text': drive_limit_text('public'),
                       'download': {'allowed': download_allowed('drive_public'),
                                    'tip': download_deny_tip('drive_public')}},
            'private': {'maxBytes': drive_limit_bytes('private'),
                        'text': drive_limit_text('private'),
                        'download': {'allowed': download_allowed('drive_private'),
                                     'tip': download_deny_tip('drive_private')}},
        })


def _cfg_mb(value, lo=0, hi=1024 * 1024):
    """把前端传来的 MB 值规范化为 float，非法返回 None。0 合法（表示禁止）。"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n


@app.route('/api/admin/config')
def api_admin_config_get():
    """管理员读取全部可配置项。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    if not is_admin_uid(uid):
        return api_fail('只有管理员可以查看设置', 403)
    return api_ok(config={
        'upload': {
            'internal_max_mb': _chat_upload_max('internal') / (1024 * 1024),
            'external_max_mb': _chat_upload_max('external') / (1024 * 1024),
        },
        'download': {k: _config_bool(DOWNLOAD_CFG.get(k, True))
                     for k in ('internal_enabled', 'external_enabled',
                               'drive_public_internal_enabled', 'drive_public_external_enabled',
                               'drive_private_internal_enabled', 'drive_private_external_enabled')},
        'review': {
            'enabled': _config_bool(REVIEW_CFG.get('enabled', False)),
            'max_mb': float(REVIEW_CFG.get('max_mb', 10) or 0),
        },
        'drive': {
            '%s_%s_max_mb' % (s, n):
                (_drive_upload_max(s, n) / (1024 * 1024)) if _drive_upload_max(s, n) is not None else None
            for s in ('public', 'private') for n in ('internal', 'external')
        },
    })


@app.route('/api/admin/config', methods=['POST'])
def api_admin_config_set():
    """管理员保存配置：白名单字段 + 原地更新（保持 dict 引用，实现热更新）+ 原子写回。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    if not is_admin_uid(uid):
        return api_fail('只有管理员可以修改设置', 403)
    data = body()
    incoming = data.get('config') if isinstance(data.get('config'), dict) else data
    errors = []

    # 聊天附件上传上限（MB，0=仅文本/表情）
    up = incoming.get('upload') or {}
    for net in ('internal', 'external'):
        if net + '_max_mb' in up:
            v = _cfg_mb(up[net + '_max_mb'])
            if v is None:
                errors.append('聊天附件%s上传大小非法' % ('内网' if net == 'internal' else '外网'))
            else:
                UPLOAD_CFG[net + '_max_mb'] = v

    # 下载开关（6 个布尔）
    dl = incoming.get('download') or {}
    for k in ('internal_enabled', 'external_enabled',
              'drive_public_internal_enabled', 'drive_public_external_enabled',
              'drive_private_internal_enabled', 'drive_private_external_enabled'):
        if k in dl:
            DOWNLOAD_CFG[k] = bool(dl[k])

    # 上传审核
    rv = incoming.get('review') or {}
    if 'enabled' in rv:
        REVIEW_CFG['enabled'] = bool(rv['enabled'])
    if 'max_mb' in rv:
        v = _cfg_mb(rv['max_mb'])
        if v is None:
            errors.append('审核大小阈值非法')
        else:
            REVIEW_CFG['max_mb'] = v

    # 盘上传上限（4 组）
    dr = incoming.get('drive') or {}
    for scope in ('public', 'private'):
        for net in ('internal', 'external'):
            k = '%s_%s_max_mb' % (scope, net)
            if k in dr:
                v = None if dr[k] is None or str(dr[k]).strip() == '' else _cfg_mb(dr[k])
                if v is None and dr[k] is not None and str(dr[k]).strip() != '':
                    errors.append('%s%s上传大小非法' % ('公共盘' if scope == 'public' else '个人盘',
                                                     '内网' if net == 'internal' else '外网'))
                else:
                    DRIVE_CFG[k] = v

    if errors:
        return api_fail('；'.join(errors))
    # 保持 CONFIG 内层 dict 引用不变，只更新内容
    CONFIG['upload'] = UPLOAD_CFG
    CONFIG['download'] = DOWNLOAD_CFG
    CONFIG['review'] = REVIEW_CFG
    CONFIG['drive'] = DRIVE_CFG
    if not save_config(CONFIG):
        return api_fail('配置保存到文件失败')
    # 同步 Flask 的请求体上限（管理员调大上限后需放宽）
    app.config['MAX_CONTENT_LENGTH'] = max_upload_envelope()
    _diag('config-saved', uid=uid, ip=request_ip(),
          upload=UPLOAD_CFG, download=DOWNLOAD_CFG, review=REVIEW_CFG, drive=DRIVE_CFG)
    # 通知所有在线端重新拉取配置（开关/限额即时生效）
    for _uid in list(USERS_DB.keys()):
        emit_uid(_uid, 'config_changed', {})
    return api_ok(config={
        'upload': {'internal_max_mb': _chat_upload_max('internal') / (1024 * 1024),
                   'external_max_mb': _chat_upload_max('external') / (1024 * 1024)},
        'review': {'enabled': _config_bool(REVIEW_CFG.get('enabled', False)),
                   'max_mb': float(REVIEW_CFG.get('max_mb', 10) or 0)},
    })


@app.route('/api/admin/review/list')
def api_admin_review_list():
    """管理员查看上传审核列表。status: pending/all。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    if not is_admin_uid(uid):
        return api_fail('只有管理员可以查看审核列表', 403)
    status = str(request.args.get('status') or 'pending')
    rows = []
    for key, rec in REVIEW_FILES.items():
        st = rec.get('status') or 'pending'
        if status == 'pending' and st != 'pending':
            continue
        item = dict(rec)
        item['key'] = key
        item['ownerNick'] = (USERS_DB.get(rec.get('owner')) or {}).get('nick') or rec.get('owner') or ''
        rows.append(item)
    rows.sort(key=lambda x: x.get('mts', 0), reverse=True)
    return api_ok(files=rows, pending=review_pending_count(),
                  enabled=review_enabled(), maxMB=review_threshold_bytes() / (1024 * 1024))


@app.route('/api/admin/review/approve', methods=['POST'])
def api_admin_review_approve():
    """管理员通过/拒绝文件审核。action: approve|reject。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    if not is_admin_uid(uid):
        return api_fail('只有管理员可以审核文件', 403)
    data = body()
    key = str(data.get('key') or '')[:300]
    action = str(data.get('action') or '')
    if action not in ('approve', 'reject'):
        return api_fail('无效的审核操作')
    with LOCK:
        rec = REVIEW_FILES.get(key)
        if not rec:
            return api_fail('文件记录不存在', 404)
        rec['status'] = 'approved' if action == 'approve' else 'rejected'
        rec['reviewer'] = uid
        rec['reviewMts'] = int(time.time() * 1000)
        persist('review.json')
    # 通知上传者审核结果
    owner = rec.get('owner')
    if owner:
        emit_uid(owner, 'review_result', {
            'key': key, 'name': rec.get('name', ''),
            'approved': action == 'approve',
            'msg': ('文件「%s」已通过审核' if action == 'approve' else '文件「%s」未通过审核') % rec.get('name', ''),
        })
    # 通知管理员刷新待审列表
    for admin_uid in [u.get('uid') for u in USERS_DB.values()
                      if u.get('isAdmin') and not u.get('deleted') and u.get('uid')]:
        emit_uid(admin_uid, 'review_pending', {'count': review_pending_count()})
    return api_ok(status=rec['status'], name=rec.get('name', ''))


@app.route('/api/diag')
def api_diag():
    """管理员诊断：返回当前判定依据、配置项与最近日志，排查内外网误判/下载被拒。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    if not USERS_DB.get(uid, {}).get('isAdmin'):
        return api_fail('只有管理员可以查看诊断日志', 403)
    prefixes = [str(x).strip() for x in (UPLOAD_CFG.get('internal_ip_prefixes') or []) if str(x).strip()]
    return api_ok(
        now=request_ip(),
        current={
            'ip': request_ip(),
            'xff': request.headers.get('X-Forwarded-For', ''),
            'remote': request.remote_addr or '',
            'scope': upload_scope(),
            'download_allowed': download_allowed(),
        },
        config={
            'force_scope': UPLOAD_CFG.get('force_scope'),
            'internal_ip_prefixes': prefixes,
            'external_download_enabled': DOWNLOAD_CFG.get('external_enabled', True),
            'internal_max_mb': round(_chat_upload_max('internal') / (1024 * 1024), 1),
            'external_max_mb': round(_chat_upload_max('external') / (1024 * 1024), 1),
        },
        log=diag_recent(100),
    )


# ---------------------------------------------------------------------------
# 工单接口
# ---------------------------------------------------------------------------
@app.route('/api/tickets')
def api_tickets():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    admin = is_admin_uid(uid)
    mine = []
    for tid, t in TICKETS.items():
        if can_view_ticket(uid, t):
            item = ticket_public(t)
            item.update(ticket_flags(uid, t))
            mine.append(item)
    # 默认按创建时间倒序（最新的在前），前端可再按状态/成员筛选与切换排序
    mine.sort(key=lambda x: -(x.get('created') or 0))
    reads = TICKET_READS.get(uid, {}) or {}
    unread = [tid for tid in ticket_unread(uid)]
    return api_ok(tickets=mine, unread=unread, isAdmin=admin,
                  statuses=list(TICKET_STATUSES), statusText=TICKET_STATUS_TEXT,
                  priorities=list(TICKET_PRIORITIES), priorityText=TICKET_PRIORITY_TEXT,
                  reads=reads)


@app.route('/api/ticket/create', methods=['POST'])
def api_ticket_create():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    title = str(data.get('title') or '').strip()[:120]
    desc = str(data.get('desc') or '').strip()[:TICKET_DESC_MAX]
    assignee = str(data.get('assignee') or '').strip()[:64]
    priority = str(data.get('priority') or 'normal').strip()
    if not title:
        return api_fail('请填写工单标题')
    if priority not in TICKET_PRIORITIES:
        priority = 'normal'
    # 直派对象必须是现存且未删除的成员
    target = USERS_DB.get(assignee)
    if not target or target.get('deleted'):
        return api_fail('指派的成员不存在或已删除')
    ts = int(time.time() * 1000)
    tid = 'T' + uuid.uuid4().hex[:12]
    with LOCK:
        t = {
            'id': tid, 'title': title, 'desc': desc,
            'creator': uid, 'assignee': assignee, 'priority': priority,
            'status': 'open', 'created': ts, 'updated': ts,
            'closedAt': 0, 'closedBy': '',
            'tracks': [{
                'uid': uid, 'ts': ts, 'type': 'create',
                'text': '创建工单并指派给「%s」' % (target.get('nick') or assignee),
                'status': 'open',
            }],
        }
        TICKETS[tid] = t
        TICKET_READS.setdefault(uid, {})[tid] = ts  # 创建者自己算已读
        persist('tickets.json')
        persist('ticket_reads.json')
    nick = (USERS_DB.get(uid) or {}).get('nick') or uid
    # 创建者自己不弹「指派给你」提醒；仅被指派人收到强提醒
    ticket_notify(t, 'created', '新建工单', '%s 指派工单给你：%s' % (nick, title),
                  exclude=(uid,), assign_to=assignee, actor=uid)
    notify_ticket_unread()
    return api_ok(id=tid, ticket=ticket_public(t, uid))


def _load_ticket(tid, uid):
    t = TICKETS.get(str(tid or '').strip())
    if not t:
        return None, api_fail('工单不存在', 404)
    if not can_view_ticket(uid, t):
        return None, api_fail('无权查看该工单', 403)
    return t, None


@app.route('/api/ticket/status', methods=['POST'])
def api_ticket_status():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    t, err = _load_ticket(data.get('id'), uid)
    if err:
        return err
    status = str(data.get('status') or '').strip()
    if status not in TICKET_STATUSES:
        return api_fail('无效的工单状态')
    if not can_manage_assignment(uid, t):
        return api_fail('只有管理员或被指派人可以修改状态')
    if t.get('status') == 'closed' and status != 'closed':
        return api_fail('已关闭的工单不能再改状态')
    if status == 'closed':
        return api_fail('关闭工单请使用关闭操作')
    ts = int(time.time() * 1000)
    old = t.get('status')
    if old == status:
        return api_ok(ticket=ticket_public(t, uid))
    with LOCK:
        t['status'] = status
        t['updated'] = ts
        t['tracks'].append({
            'uid': uid, 'ts': ts, 'type': 'status',
            'text': '状态由「%s」改为「%s」' % (TICKET_STATUS_TEXT.get(old, old),
                                           TICKET_STATUS_TEXT.get(status, status)),
            'status': status,
        })
        TICKET_READS.setdefault(uid, {})[t['id']] = ts  # 操作者算已读
        persist('tickets.json')
        persist('ticket_reads.json')
    nick = (USERS_DB.get(uid) or {}).get('nick') or uid
    ticket_notify(t, 'status', '状态更新', '%s 将工单「%s」改为%s' %
                  (nick, t.get('title'), TICKET_STATUS_TEXT.get(status, status)), exclude=(uid,))
    notify_ticket_unread()
    return api_ok(ticket=ticket_public(t, uid))


@app.route('/api/ticket/update', methods=['POST'])
def api_ticket_update():
    """编辑工单：创建者可再次编辑标题/需求/优先级；指派变更按权限矩阵校验。"""
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    t, err = _load_ticket(data.get('id'), uid)
    if err:
        return err
    if not (can_edit_ticket(uid, t) or can_manage_assignment(uid, t)):
        return api_fail('你无权编辑该工单', 403)
    if t.get('status') == 'closed':
        return api_fail('已关闭的工单不能再编辑')

    title = str(data.get('title') or '').strip()[:120]
    desc = str(data.get('desc') or '').strip()[:TICKET_DESC_MAX]
    priority = str(data.get('priority') or t.get('priority') or 'normal').strip()
    if not title:
        return api_fail('请填写工单标题')
    if priority not in TICKET_PRIORITIES:
        priority = 'normal'
    content_changed = (t.get('title') != title or t.get('desc') != desc or t.get('priority') != priority)
    if content_changed and not can_edit_ticket(uid, t):
        return api_fail('只有创建者或管理员可以编辑需求内容', 403)

    # 指派变更：管理员可改任意成员；普通成员只能把「指派给自己」的工单转派给其他成员
    new_assignee = str(data.get('assignee') or t.get('assignee') or '').strip()[:64]
    old_assignee = t.get('assignee') or ''
    assignee_changed = new_assignee != old_assignee
    if assignee_changed:
        if not can_manage_assignment(uid, t):
            return api_fail('只有管理员或被指派人可以修改指派', 403)
        target = USERS_DB.get(new_assignee)
        if not target or target.get('deleted'):
            return api_fail('指派的成员不存在或已删除')
        if not is_admin_uid(uid) and new_assignee == uid:
            return api_fail('不能把工单指派给自己')

    changes = []
    if t.get('title') != title:
        changes.append('标题')
    if t.get('desc') != desc:
        changes.append('需求')
    if t.get('priority') != priority:
        changes.append('优先级')
    assignee_nick = ((USERS_DB.get(new_assignee) or {}).get('nick') or new_assignee)
    if assignee_changed:
        changes.append('指派改为「%s」' % assignee_nick)
    if not changes:
        return api_ok(ticket=ticket_public(t, uid))

    ts = int(time.time() * 1000)
    with LOCK:
        t['title'] = title
        t['desc'] = desc
        t['priority'] = priority
        if assignee_changed:
            t['assignee'] = new_assignee
        t['updated'] = ts
        t['tracks'].append({
            'uid': uid, 'ts': ts, 'type': 'edit',
            'text': '编辑了工单：' + '、'.join(changes),
            'status': t.get('status'),
        })
        TICKET_READS.setdefault(uid, {})[t['id']] = ts  # 编辑者算已读
        persist('tickets.json')
        persist('ticket_reads.json')
    nick = (USERS_DB.get(uid) or {}).get('nick') or uid
    ticket_notify(t, 'edited', '需求更新', '%s 更新了工单「%s」' % (nick, title),
                  exclude=(uid,), assign_to=(new_assignee if assignee_changed else ''), actor=uid)
    notify_ticket_unread()
    return api_ok(ticket=ticket_public(t, uid))


@app.route('/api/ticket/comment', methods=['POST'])
def api_ticket_comment():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    t, err = _load_ticket(data.get('id'), uid)
    if err:
        return err
    text = str(data.get('text') or '').strip()[:2000]
    if not text:
        return api_fail('请填写跟踪内容')
    if not can_track_ticket(uid, t):
        return api_fail('你无权跟踪该工单')
    ts = int(time.time() * 1000)
    with LOCK:
        t['tracks'].append({'uid': uid, 'ts': ts, 'type': 'comment', 'text': text,
                            'status': t.get('status')})
        t['updated'] = ts
        TICKET_READS.setdefault(uid, {})[t['id']] = ts
        persist('tickets.json')
        persist('ticket_reads.json')
    nick = (USERS_DB.get(uid) or {}).get('nick') or uid
    ticket_notify(t, 'comment', '跟踪更新', '%s 跟踪了工单「%s」：%s' %
                  (nick, t.get('title'), text[:60]), exclude=(uid,))
    notify_ticket_unread()
    return api_ok(ticket=ticket_public(t, uid))


@app.route('/api/ticket/close', methods=['POST'])
def api_ticket_close():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    t, err = _load_ticket(data.get('id'), uid)
    if err:
        return err
    if not can_close_ticket(uid, t):
        return api_fail('只有创建者或管理员可以关闭工单', 403)
    if t.get('status') == 'closed':
        return api_ok(ticket=ticket_public(t, uid))
    ts = int(time.time() * 1000)
    with LOCK:
        t['status'] = 'closed'
        t['closedAt'] = ts
        t['closedBy'] = uid
        t['updated'] = ts
        t['tracks'].append({
            'uid': uid, 'ts': ts, 'type': 'close', 'text': '关闭了工单', 'status': 'closed',
        })
        TICKET_READS.setdefault(uid, {})[t['id']] = ts
        persist('tickets.json')
        persist('ticket_reads.json')
    nick = (USERS_DB.get(uid) or {}).get('nick') or uid
    ticket_notify(t, 'closed', '工单关闭', '%s 关闭了工单「%s」' % (nick, t.get('title')),
                  exclude=(uid,))
    notify_ticket_unread()
    return api_ok(ticket=ticket_public(t, uid))


@app.route('/api/ticket/delete', methods=['POST'])
def api_ticket_delete():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    t, err = _load_ticket(data.get('id'), uid)
    if err:
        return err
    if not can_close_ticket(uid, t):
        return api_fail('只有创建者或管理员可以删除工单', 403)
    tid = t['id']
    title = t.get('title', '')
    with LOCK:
        TICKETS.pop(tid, None)
        for reads in TICKET_READS.values():
            reads.pop(tid, None)
        persist('tickets.json')
        persist('ticket_reads.json')
    ticket_notify(t, 'deleted', '工单删除', '工单「%s」已被删除' % title, exclude=(uid,))
    notify_ticket_unread()
    return api_ok(id=tid)


@app.route('/api/ticket/read', methods=['POST'])
def api_ticket_read():
    uid = caller_uid()
    if not uid:
        return api_fail('请先登录', 401)
    data = body()
    tid = str(data.get('id') or '').strip()
    t = TICKETS.get(tid)
    if not t or not can_view_ticket(uid, t):
        return api_ok()
    with LOCK:
        TICKET_READS.setdefault(uid, {})[tid] = t.get('updated') or 0
        persist('ticket_reads.json')
    emit_uid(uid, 'ticket_unread', {'ids': ticket_unread(uid)})
    return api_ok()


@app.route('/upload', methods=['POST'])
def upload():
    limit = upload_limit_bytes()
    if limit == 0:
        return api_fail('管理员已关闭当前环境的聊天附件上传，只能发送文字和表情')
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
    # 审核：按当前开关与阈值决定是否需要管理员审核
    status = 'approved'
    if review_required(size):
        key = review_key_upload(url_prefix + stored)
        review_set(key, {'name': orig_name, 'size': size, 'mime': mime,
                         'owner': uid, 'channel': 'chat', 'path': url_prefix + stored})
        status = 'pending'
        notify_review_pending(key, orig_name, uid)
    return api_ok(file={'url': '/uploads/' + url_prefix + quote(stored),
                        'name': orig_name, 'size': size, 'mime': mime,
                        'reviewStatus': status})


def normalize_upload_path(filename):
    """规范化附件相对路径，防路径穿越与审核 key 变形绕过。

    上传时审核 key = 'upload:' + 'in/文件名' 或 'out/文件名'，
    若下载时用 `in/./文件名`、`in/../in/文件名` 等变形，原始字符串
    匹配不到审核记录 -> review_status 默认放行 -> 绕过审核。
    这里统一 normpath 并强制白名单结构，返回 None 表示非法路径。
    """
    name = str(filename or '').replace('\\', '/')
    if not name or name.startswith('/') or ':' in name:
        return None
    # normpath 折叠 ./ 与 ../，例如 in/../in/a.png -> in/a.png
    name = posixpath.normpath(name)
    if name in ('.', '..') or name.startswith('../') or '/..' in name:
        return None
    # 合法结构：新文件 in/xxx 或 out/xxx；旧文件根目录 xxx（无斜杠）
    if '/' in name and not re.fullmatch(r'(in|out)/[^/]+', name):
        return None
    return name


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # 先规范化路径：既防穿越，也保证审核 key 与上传时完全一致
    safe_path = normalize_upload_path(filename)
    if not safe_path:
        _diag('download-denied', channel='attachment', filename=filename,
              scope=upload_scope(), ip=request_ip(), reason='非法路径')
        return jsonify({'ok': False, 'error': '文件不存在'}), 404

    tip = download_deny_tip('chat')
    if not download_allowed('chat'):
        # 聊天附件里图片/视频/音频的内联预览也走此路由，外网禁用时一并返回 403
        _diag('download-denied', channel='attachment', filename=safe_path,
              scope=upload_scope(), allowed=False, ip=request_ip(), reason=tip)
        return jsonify({'ok': False, 'error': tip}), 403
    # 先定位文件真实落点，再按「实际目录」反推规范审核 key。
    # 关键：不能用请求里的 safe_path 直接拼 key —— 请求 `zzb_x.png`（无前缀）时
    # 会拼出 upload:zzb_x.png（无记录->默认放行），但文件其实在 uploads/in/ 下，
    # 于是待审文件被绕过下载。必须按命中的目录还原成 in/xxx 或 out/xxx 的规范 key。
    # 新文件在 in/out 子目录；旧文件在根目录（无前缀，保持兼容）。
    found = None          # (base, rel_path, key_prefix)
    if '/' in safe_path:
        # 请求带 in/ 或 out/ 前缀：只允许到对应子目录取，key 前缀即请求前缀
        prefix = safe_path.split('/', 1)[0]  # in 或 out
        base = UPLOAD_IN_DIR if prefix == 'in' else UPLOAD_OUT_DIR
        rel = safe_path.split('/', 1)[1]
        if os.path.isfile(os.path.join(base, rel)):
            found = (base, rel, prefix + '/')
    else:
        # 无前缀请求：先查根目录的历史文件；为兼容旧客户端也接受 in/out 里同名新文件，
        # 但无论命中哪里，审核 key 都按真实目录还原，杜绝「无前缀绕过」。
        for base, prefix in ((UPLOAD_DIR, ''), (UPLOAD_IN_DIR, 'in/'), (UPLOAD_OUT_DIR, 'out/')):
            if os.path.isfile(os.path.join(base, safe_path)):
                found = (base, safe_path, prefix)
                break
    if not found:
        return ('', 404)
    base, rel, key_prefix = found

    # 审核拦截：一律用文件真实目录对应的规范 key 校验（与上传时一致）
    key = review_key_upload(key_prefix + rel)
    rstatus = review_status(key)
    if rstatus != 'approved':
        diag_msg = '文件待管理员审核' if rstatus == 'pending' else '文件未通过审核'
        _diag('download-denied', channel='review', filename=safe_path,
              key=key, scope=upload_scope(), status=rstatus, ip=request_ip(), reason=diag_msg)
        return jsonify({'ok': False, 'error': diag_msg}), 403
    # 历史遗留的危险文件也强制下载，杜绝同源内联执行（存储型 XSS）
    return send_from_directory(base, rel, as_attachment=is_dangerous_name(rel))


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
    # 注入实时审核状态（管理员可能已通过/拒绝，需每次读取最新值）
    # 审核 key 在上传时按「文件真实 owner」生成（见 api_drive_upload），这里必须用
    # 同一个 owner，不能用 owner_uid（公共盘 owner_uid 是当前访问者，个人盘是目标成员）。
    # 否则别人查看公共盘时 key 拼错 -> 查不到记录 -> review_status 默认放行 -> 绕过审核。
    for item in files:
        item['reviewStatus'] = review_status(
            review_key_drive(scope, item.get('owner') or owner_uid, item.get('id', '')))
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
    status = 'approved'
    if review_required(size):
        rkey = review_key_drive(scope, uid, fid)
        review_set(rkey, {'name': name, 'size': size, 'mime': mime, 'owner': uid,
                          'channel': 'drive_' + scope, 'path': '%s/%s' % (scope, fid)})
        meta['reviewStatus'] = 'pending'
        status = 'pending'
    with LOCK:
        st = drive_container(scope, uid, create=True)
        if parent and parent not in st['folders']:
            os.remove(path)
            if status == 'pending':
                with LOCK:
                    REVIEW_FILES.pop(review_key_drive(scope, uid, fid), None)
                    persist('review.json')
            return api_fail('上级文件夹不存在')
        st['files'][fid] = meta
        persist('drive.json')
    if status == 'pending':
        notify_review_pending(review_key_drive(scope, uid, fid), name, uid)
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
    channel = 'drive_public' if scope == 'public' else 'drive_private'
    tip = download_deny_tip(channel)
    if not download_allowed(channel):
        _diag('download-denied', channel=channel, uid=uid,
              scope=upload_scope(), allowed=False, ip=request_ip(), reason=tip)
        return api_fail(tip, 403)
    owner_uid = uid if scope == 'public' else drive_target_uid(uid, target)
    if not owner_uid:
        return api_fail('无权查看该成员的个人盘', 403)
    if not re.fullmatch(r'[0-9a-f]{6,40}', fid or ''):
        return api_fail('文件不存在', 404)
    st = drive_container(scope, owner_uid)
    meta = (st.get('files') or {}).get(fid)
    if not meta:
        return api_fail('文件不存在或已删除', 404)
    # 审核 key 必须与上传时一致：按文件真实 owner 生成，而不是访问者 owner_uid。
    # 公共盘 owner_uid=当前访问者，用它拼 key 会查不到审核记录而默认放行，绕过审核。
    file_owner = meta.get('owner') or owner_uid
    rstatus = review_status(review_key_drive(scope, file_owner, fid))
    if rstatus != 'approved':
        _diag('download-denied', channel='review', uid=uid, owner=file_owner,
              scope=scope, fid=fid, status=rstatus, ip=request_ip(),
              reason='文件待审核或未通过')
        msg = '文件待管理员审核，暂不可下载' if rstatus == 'pending' else '文件未通过审核'
        return api_fail(msg, 403)
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