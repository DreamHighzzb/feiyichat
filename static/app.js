/* ======================= 常量 ======================= */
/* 每个 emoji 用 Twemoji code 标识，图标走服务端 /emoji/<code>.svg */
const UNICODE_EMOJIS = [
  ['😀','1f600'],['😃','1f603'],['😄','1f604'],['😁','1f601'],['😆','1f606'],['😅','1f605'],['😂','1f602'],['🤣','1f923'],
  ['😊','1f60a'],['😇','1f607'],['🙂','1f642'],['🙃','1f643'],['😉','1f609'],['😌','1f60c'],['😍','1f60d'],['🥰','1f970'],
  ['😘','1f618'],['😗','1f617'],['😙','1f619'],['😚','1f61a'],['😋','1f60b'],['😛','1f61b'],['😜','1f61c'],['🤪','1f92a'],
  ['😝','1f61d'],['🤑','1f911'],['🤗','1f917'],['🤭','1f92d'],['🤫','1f92b'],['🤔','1f914'],['🤐','1f910'],['🤨','1f928'],
  ['😐','1f610'],['😑','1f611'],['😶','1f636'],['😏','1f60f'],['😒','1f612'],['🙄','1f644'],['😬','1f62c'],['🤥','1f925'],
  ['😴','1f634'],['😵','1f631'],['🤠','1f608'],['😎','1f60f'],['🤓','1f914'],['😕','1f626'],['😮','1f62e'],['😳','1f633'],
  ['😢','1f622'],['😭','1f62d'],['😱','1f631'],['😤','1f624'],['😡','1f621'],['🤬','1f92c'],['😈','1f608'],['💀','1f480'],
  ['💩','1f4a9'],['👻','1f47b'],['👽','1f47d'],['🤖','1f916'],['❤️','2764'],['💔','1f494'],['👍','1f44d'],['👎','1f44e'],
  ['👌','1f44c'],['✌️','270c'],['🤞','1f91e'],['🤝','1f91d'],['👏','1f44f'],['🙏','1f64f'],['💪','1f4aa'],['👋','1f44b'],
  ['🔥','1f525'],['✨','2728'],['🎉','1f389'],['🎊','1f38a'],['🎁','1f381'],['⭐','2b50'],['🌈','1f308'],['☕','2615']
];
/* Unicode 字符 -> code，用于把历史消息里的 emoji 字符渲染成服务端图标 */
const EMOJI_CHAR_CODE = {};
UNICODE_EMOJIS.forEach(p => { if (!EMOJI_CHAR_CODE[p[0]]) EMOJI_CHAR_CODE[p[0]] = p[1]; });
/* 默认头像资源 id，对应服务端 /avatar/<id>.svg */
const AVATAR_CHOICES = ['av01','av02','av03','av04','av05','av06',
                        'av07','av08','av09','av10','av11','av12'];
/* [中文名, Twemoji code] —— 图标全部走服务端 /emoji/<code>.svg */
const FACE_DEFS = [
  ['微笑','1f60a'],['撇嘴','1f61e'],['色','1f60d'],['发呆','1f626'],
  ['得意','1f60f'],['流泪','1f622'],['害羞','1f633'],['闭嘴','1f636'],
  ['睡','1f634'],['大哭','1f62d'],['尴尬','1f605'],['发怒','1f620'],
  ['调皮','1f61c'],['呲牙','1f601'],['惊讶','1f62e'],['难过','1f61e'],
  ['抓狂','1f92c'],['吐','1f92e'],['偷笑','1f61a'],['可爱','1f60d'],
  ['白眼','1f644'],['傲慢','1f60f'],['困','1f634'],['惊恐','1f631'],
  ['流汗','1f605'],['大笑','1f602']
];
const FACE_CODE_SET = {};
const FACE_URLS = {};

FACE_DEFS.forEach(function (d) {
  FACE_CODE_SET[d[0]] = true;
  FACE_URLS[d[0]] = '/emoji/' + d[1] + '.svg';
});

/* ======================= 状态 ======================= */
const state = {
  uid: null, sid: null, token: '', me: null, view: 'chats', current: null,
  data: { friends: [], groups: [], requests: {in: [], out: []}, chats: [], unread: {} },
  histories: {}, pending: [], sending: false, search: '', quote: null,
  uploadLimit: {maxBytes: 20 * 1024 * 1024, text: '20 MB', scope: 'internal'},
  driveLimit: {
    public: {maxBytes: 20 * 1024 * 1024, text: '20 MB'},
    private: {maxBytes: 20 * 1024 * 1024, text: '20 MB'},
  },
  groupPanelOpen: true, groupSearch: '',
  mentions: [], mentionAll: false, autoAt: null,
  mention: {open: false, start: 0, query: '', items: [], index: 0},
  drive: {scope: 'public', folder: '', path: [], folders: [], files: [], total: 0, q: '', busy: false,
          target: '', members: [], viewingOther: false, ownerNick: ''},
};
let socket = null;
let typingTimer = null, lastTyping = 0, toastTimer = null;
const $ = id => document.getElementById(id);

/* 本机保存的账号（只存 uid 和姓名，不存密码） */
function savedAccounts() {
  try { return JSON.parse(localStorage.getItem('feiyi_accounts') || '[]'); }
  catch (e) { return []; }
}
function rememberAccount(uid, nick) {
  const list = savedAccounts().filter(a => a.uid !== uid);
  list.unshift({uid, nick});
  localStorage.setItem('feiyi_accounts', JSON.stringify(list.slice(0, 10)));
  localStorage.setItem('feiyi_uid', uid);
  localStorage.setItem('feiyi_nick', nick);
  renderSavedAccounts();
}
function renderSavedAccounts() {
  const box = $('saved-accounts');
  if (!box) return;
  box.innerHTML = '';
  savedAccounts().forEach(a => {
    const btn = document.createElement('button');
    btn.className = 'account';
    btn.textContent = a.nick;
    btn.title = '点击填入账号：' + a.nick;
    btn.onclick = () => { $('nick-input').value = a.nick; $('pass-input').value = ''; $('pass-input').focus(); };
    box.appendChild(btn);
  });
}
function updateSavedNick(uid, nick) {
  const list = savedAccounts().map(a => a.uid === uid ? Object.assign({}, a, {nick}) : a);
  localStorage.setItem('feiyi_accounts', JSON.stringify(list));
  if (localStorage.getItem('feiyi_uid') === uid) localStorage.setItem('feiyi_nick', nick);
  renderSavedAccounts();
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtTime(ms) {
  if (!ms) return '';
  const d = new Date(ms), now = new Date();
  const p = n => String(n).padStart(2, '0');
  if (d.toDateString() === now.toDateString()) return p(d.getHours()) + ':' + p(d.getMinutes());
  return (d.getMonth() + 1) + '/' + d.getDate();
}
function fmtFull(ms) {
  const d = new Date(ms || Date.now()), p = n => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth()+1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
function dayKey(ms) { return new Date(ms || Date.now()).toDateString(); }
function sizeText(n) {
  n = Number(n) || 0;
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n/1024).toFixed(1) + ' KB';
  return (n/1048576).toFixed(1) + ' MB';
}
function fileIcon(mime) {
  mime = mime || '';
  if (mime.startsWith('image/')) return '🖼️';
  if (mime.startsWith('video/')) return '🎬';
  if (mime.startsWith('audio/')) return '🎵';
  if (mime.includes('pdf')) return '📕';
  if (mime.includes('zip') || mime.includes('compressed')) return '🗜️';
  if (mime.includes('sheet') || mime.includes('excel')) return '📊';
  return '📄';
}
function toast(text) {
  const el = $('toast'); el.textContent = text; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 2300);
}

/* ======================= 桌面通知（右下角） ======================= */
let notifyEnabled = localStorage.getItem('feiyi_notify') !== '0';
let notifySound = localStorage.getItem('feiyi_sound') !== '0';
let audioCtx = null, lastSoundAt = 0;
function requestNotifyPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    try {
      const p = Notification.requestPermission();
      if (p && typeof p.catch === 'function') p.catch(() => {});
    } catch (e) {}
  }
}
/* 借登录点击解锁音频，否则浏览器会拦截后续自动播放 */
function unlockNotifySound() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    audioCtx = audioCtx || new AC();
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  } catch (e) {}
}
function playNotifySound(atMe) {
  if (!notifySound) return;
  const t0 = Date.now();
  if (t0 - lastSoundAt < 700) return; // 消息轰炸时限流，避免一片杂音
  lastSoundAt = t0;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    if (!audioCtx) audioCtx = new AC();
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    const t = audioCtx.currentTime;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    // @ 用双音上扬，普通消息单音，听起来能分辨
    osc.frequency.setValueAtTime(atMe ? 880 : 660, t);
    if (atMe) osc.frequency.setValueAtTime(1180, t + 0.14);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.38);
    osc.connect(gain); gain.connect(audioCtx.destination);
    osc.start(t); osc.stop(t + 0.4);
  } catch (e) {}
}
/* 标签页/任务栏闪动：标题与 favicon 交替切换，窗口聚焦/未读清零后复位。
   注意：普通浏览器窗口的任务栏按钮显示浏览器图标，网页无权更改；
   但标签页标题会一直闪、Windows 通知会常驻，不需要应用模式也能看到。 */
// favicon 红点/图标资源统一走服务端 SVG（/icon/*.svg），与 emoji/icon/avatar 一致
const FAV_NORMAL = '/icon/msg-normal.svg';   // 蓝底白气泡
const FAV_ALERT = '/icon/msg-alert.svg';     // 红底白气泡，视觉醒目
const DOT_RED = '/icon/dot-red.svg';         // 纯红点，供通知气泡使用
function faviconEl() {
  let el = $('favicon');
  if (!el) {
    el = document.createElement('link');
    el.id = 'favicon'; el.rel = 'icon'; el.type = 'image/svg+xml';
    document.head.appendChild(el);
  }
  return el;
}
faviconEl().href = FAV_NORMAL;

let deskNotifyTimer = null, baseTitle = document.title;
let flashTimer = null, flashOn = false;
function stopFlash() {
  if (flashTimer) { clearInterval(flashTimer); flashTimer = null; }
  flashOn = false;
  document.title = baseTitle;
  const el = faviconEl(); if (el.href !== FAV_NORMAL) el.href = FAV_NORMAL;
}
function startFlash(label) {
  if (!state.uid || (!document.hidden && document.hasFocus())) return;
  if (flashTimer) clearInterval(flashTimer);
  flashOn = false;
  // 任务栏标题是纯文本：emoji 在任务栏会显示成方框，故用普通文本标记；
  // 真正的“红色”由 favicon（应用模式下即任务栏图标）红蓝交替实现。
  // 不再 10 秒自动停：只要没读就一直闪，回到窗口或未读清零才停。
  const title = '【' + (label || '新消息') + '】' + baseTitle;
  const tick = () => {
    flashOn = !flashOn;
    document.title = flashOn ? title : baseTitle;
    const el = faviconEl();
    const href = flashOn ? FAV_ALERT : FAV_NORMAL;
    if (el.href !== href) el.href = href;
  };
  tick();
  flashTimer = setInterval(tick, 500);
}
function showDeskBubble(title, body, ch) {
  const el = $('desk-notify');
  // 标题前加服务端红点图，【新消息】等中括号标记用红色显示
  const marked = esc(title).replace(/【([^】]+)】/g,
    '<i class="dn-dot" style="background-image:url(' + DOT_RED + ')"></i>' +
    '【<em class="dn-hot">$1</em>】');
  el.innerHTML = '<b>' + marked + '</b><span>' + esc(body) + '</span>';
  el.classList.add('show');
  el.onclick = () => { el.classList.remove('show'); window.focus(); openChat(ch); };
  clearTimeout(deskNotifyTimer);
  deskNotifyTimer = setTimeout(() => el.classList.remove('show'), 6000);
}
// 是否被 @（含 @all 展开）：群消息且 mentions 含自己
function isMentioned(m) {
  if (!m || m.from === state.uid) return false;
  const info = chatInfo(m.ch);
  return !!(info && info.type === 'group' &&
    (m.mentions || []).some(x => x.uid === state.uid));
}
function desktopNotify(m) {
  if (!m || m.from === state.uid) return;
  // 页面隐藏、失焦（最小化/被其它窗口遮住），或当前不在该会话时才提示
  const away = document.hidden || !document.hasFocus() || state.view !== 'chats' || state.current !== m.ch;
  if (!away) return;
  const info = chatInfo(m.ch);
  const who = m.fromNick || '同事';
  const atMe = isMentioned(m);
  const title = atMe
    ? '【@新消息】' + who + ' 在「' + info.title + '」@了你'
    : (info.type === 'group' ? who + ' 在「' + info.title + '」' : who);
  let body = m.text || '';
  if (!body && Array.isArray(m.files) && m.files.length) body = '[文件] ' + m.files[0].name;
  body = body.replace(/\[([^\[\]]{1,8})\]/g, '$1').slice(0, 120);
  if (atMe) body = '[有人@你] ' + body;
  playNotifySound(atMe);
  if (!notifyEnabled) return;
  // 优先用浏览器系统通知（Windows 右下角）；非安全上下文/被拒时用页内兜底
  if ('Notification' in window && Notification.permission === 'granted') {
    const logo = document.querySelector('.logo-bubble');
    try {
      // requireInteraction：通知常驻到用户点掉，不再 6 秒自动消失；
      // renotify：同一会话连续来消息也会重新弹，不会只替换静默掉。
      const n = new Notification(title, {
        body: body || '发来一条消息',
        tag: 'feiyi-' + m.ch,
        icon: logo ? logo.src : undefined,
        requireInteraction: true,
        renotify: true,
        silent: true,
      });
      n.onclick = () => { window.focus(); openChat(m.ch); n.close(); };
      return;
    } catch (e) {}
  }
  if (!document.hidden) showDeskBubble(title, body || '发来一条消息', m.ch);
}
window.addEventListener('focus', () => {
  stopFlash();
  const el = $('desk-notify'); if (el) el.classList.remove('show');
  markRead(state.current);
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) { stopFlash(); markRead(state.current); }
});
function toggleNotify() {
  notifyEnabled = !notifyEnabled;
  localStorage.setItem('feiyi_notify', notifyEnabled ? '1' : '0');
  if (notifyEnabled) {
    requestNotifyPermission();
    unlockNotifySound();
    if ('Notification' in window && Notification.permission === 'denied') {
      toast('浏览器已阻止通知，请在地址栏权限设置里允许');
    } else toast('桌面通知已开启');
  } else toast('桌面通知已关闭');
  renderList();
}
function toggleNotifySound() {
  notifySound = !notifySound;
  localStorage.setItem('feiyi_sound', notifySound ? '1' : '0');
  if (notifySound) { unlockNotifySound(); playNotifySound(false); }
  toast(notifySound ? '提示音已开启' : '提示音已关闭');
  renderList();
}
function renderText(text, nicks) {
  let s = esc(text || '');
  // markdown 引用行首 ">"（企业微信风格）：转义后为 &gt;
  s = s.replace(/(^|\n)&gt;\s?/g, '$1› ');
  // markdown 链接 [文字](http...)：必须在裸 URL 自动链接之前处理，否则会被拆开
  s = s.replace(/\[([^\[\]\n]{1,120})\]\((https?:\/\/[^\s)]+)\)/gi, function (full, label, url) {
    const href = url.replace(/&amp;/g, '&').replace(/"/g, '%22').replace(/'/g, '%27');
    return '<a href="' + href + '" target="_blank" rel="noopener">' + label + '</a>';
  });
  // 企业微信风格彩色文字 <font color="#ff0000">文字</font>，仅允许 hex 颜色防注入
  s = s.replace(/&lt;font\s+color=&quot;(#[0-9a-fA-F]{3,8})&quot;&gt;([\s\S]*?)&lt;\/font&gt;/gi,
    '<span style="color:$1">$2</span>');
  // @成员高亮：放在表情/链接替换之前，避免被后续替换拆开
  const meNick = (state.me && state.me.nick) || '';
  (nicks || []).slice().filter(Boolean).sort((a, b) => b.length - a.length).forEach(nick => {
    const key = '@' + esc(nick);
    if (s.indexOf(key) < 0) return;
    const cls = nick === meNick ? 'at-mention me' : 'at-mention';
    s = s.split(key).join('<span class="' + cls + '">' + key + '</span>');
  });
  s = s.replace(/\[([^\[\]]{1,8})\]/g, function (full, code) {
    return FACE_URLS[code] ? '<img class="face" src="' + FACE_URLS[code] + '" alt="[' + esc(code) + ']" title="[' + esc(code) + ']">' : full;
  });
  // 直接输入的 Unicode emoji 也换成服务端图标（历史消息兼容）
  const keys = Object.keys(EMOJI_CHAR_CODE).sort((a, b) => b.length - a.length);
  keys.forEach(ch => {
    const code = EMOJI_CHAR_CODE[ch];
    const img = '<img class="face" src="/emoji/' + code + '.svg" alt="' + esc(ch) + '">';
    s = s.split(esc(ch)).join(img);
  });
  // 裸 URL 自动链接：跳过已在 href=" 里的（markdown 链接已转换），避免嵌套 <a>
  s = s.replace(/(?<!href=")(https?:\/\/[^\s<"]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return s.replace(/\n/g, '<br>');
}
function chatInfo(ch) {
  const found = (state.data.chats || []).find(c => c.ch === ch);
  if (found) return found;
  if (ch && ch.startsWith('g:')) {
    const g = (state.data.groups || []).find(x => x.id === ch.slice(2));
    if (g) return {ch, title: g.name, color: g.color, avatar: 'group', type: 'group', peer: g.id, unread: 0};
  }
  if (ch && ch.startsWith('p:')) {
    const uid = ch.slice(2).split(':').find(x => x !== state.uid) || state.uid;
    const f = (state.data.members || []).find(x => x.uid === uid) ||
      (state.data.friends || []).find(x => x.uid === uid);
    if (f) return {ch, title: f.nick, color: f.color, avatar: f.avatar, type: 'private', peer: uid, unread: 0};
  }
  return {ch, title: '未知会话', color: '#9aa0a8', avatar: '🙂', type: 'private', peer: '', unread: 0};
}
function avatarInner(av) {
  av = av || '';
  if (/^av[0-9]{2}$/.test(av)) return '<img src="/avatar/' + av + '.svg" alt="">';
  if (av === 'group') return '<i class="ico i-group"></i>';
  return esc(av || '🙂');
}
function avatarHTML(u, size) {
  return '<div class="avatar" style="background:' + esc(u.color || '#12b7f5') + ';' + (size ? 'width:'+size+'px;height:'+size+'px;' : '') + '">' +
    avatarInner(u.avatar) + (u.online === true ? '<i class="online-dot"></i>' : '') + '</div>';
}

/* 会话失效统一回登录页（强制下线 / 登录过期共用） */
function forceLogout(msg) {
  stopFlash();
  try { socket.disconnect(); } catch (e) {}
  socket = null; state.uid = null; state.sid = null; state.token = ''; state.me = null;
  state.data = {friends: [], groups: [], requests: {in: [], out: []}, chats: [], unread: {}};
  state.histories = {}; state.current = null; clearQuote();
  $('app').classList.remove('show'); $('login').style.display = 'flex';
  $('pass-input').value = '';
  $('login-err').textContent = msg || '登录已失效，请重新登录';
  $('join-btn').disabled = false;
}

/* ======================= HTTP 请求 ======================= */
async function api(path, options) {
  const opt = Object.assign({headers: {'Content-Type': 'application/json'}}, options || {});
  opt.headers = Object.assign({}, opt.headers);
  if (state.token) opt.headers['X-Token'] = state.token;
  if (opt.body && typeof opt.body !== 'string') opt.body = JSON.stringify(opt.body);
  const res = await fetch(path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  // 登录过期/未登录：跳回登录页，避免用失效身份继续请求
  if (res.status === 401 && state.uid) forceLogout('登录已过期，请重新登录');
  if (!res.ok || data.ok === false) throw new Error(data.msg || ('请求失败 ' + res.status));
  return data;
}

function loadUploadConfig() {
  api('/api/upload_config').then(d => {
    state.uploadLimit = {
      maxBytes: Number(d.maxBytes) || 20 * 1024 * 1024,
      text: d.text || '20 MB',
      scope: d.scope || 'internal',
    };
    ['public', 'private'].forEach(k => {
      const cfg = (d.drive || {})[k] || {};
      const raw = cfg.maxBytes;
      state.driveLimit[k] = {
        maxBytes: (raw === null || raw === undefined || isNaN(Number(raw)))
          ? state.uploadLimit.maxBytes : Number(raw),
        text: cfg.text || state.uploadLimit.text,
      };
    });
    const hint = $('upload-hint');
    if (hint) hint.textContent = '单文件 ≤ ' + state.uploadLimit.text + ' · 可拖入/粘贴';
    if (state.view === 'public-drive' || state.view === 'private-drive') renderDrive();
  }).catch(() => {
    const hint = $('upload-hint');
    if (hint) hint.textContent = '单文件 ≤ 20 MB · 可拖入/粘贴';
  });
}

/* ======================= 登录 ======================= */
$('join-btn').onclick = async () => {
  const nick = $('nick-input').value.trim();
  const password = $('pass-input').value;
  if (!nick) { $('login-err').textContent = '请输入姓名'; return; }
  if (!password) { $('login-err').textContent = '请输入登录密码'; return; }
  requestNotifyPermission(); // 借登录点击这个用户手势申请桌面通知权限
  unlockNotifySound();       // 同一个手势解锁提示音，避免浏览器拦截自动播放
  $('login-err').textContent = ''; $('join-btn').disabled = true;
  try {
    // 通过姓名匹配本机保存的账号，避免切换账号时误用上一个 uid
    const account = savedAccounts().find(a => a.nick === nick);
    const uid = account ? account.uid : '';
    const r = await api('/api/login', {method: 'POST', body: {nick, password, uid}});
    state.uid = r.uid;
    state.token = r.token || '';
    rememberAccount(r.uid, r.me.nick);
    $('nick-input').value = r.me.nick;
    $('pass-input').value = '';
    if (r.firstAdmin) toast('管理员账号已创建');
    if (socket && socket.connected) socket.emit('join', {uid: state.uid, token: state.token});
    else connect();
  } catch (e) {
    $('login-err').textContent = e.message; $('join-btn').disabled = false;
  }
};
$('nick-input').addEventListener('keydown', e => { if (e.key === 'Enter') $('pass-input').focus(); });
$('pass-input').addEventListener('keydown', e => { if (e.key === 'Enter') $('join-btn').click(); });

function connect() {
  if (typeof io === 'undefined') { $('login-err').textContent = '组件加载失败，请刷新页面'; $('join-btn').disabled = false; return; }
  socket = io({transports: ['websocket', 'polling']});
  socket.on('connect', () => {
    state.sid = socket.id || '';
    if (state.uid && state.token) socket.emit('join', {uid: state.uid, token: state.token});
  });
  socket.on('joined', () => {
    state.sid = socket.id || '';
    $('login').style.display = 'none';
    $('app').classList.add('show');
    $('join-btn').disabled = false;
    loadUploadConfig();
  });
  socket.on('join_error', d => {
    $('login').style.display = 'flex'; $('app').classList.remove('show');
    $('login-err').textContent = d.msg || '登录失败'; $('join-btn').disabled = false;
  });
  socket.on('force_logout', d => forceLogout((d && d.msg) || '账号已被管理员删除，请联系管理员'));
  socket.on('contacts', d => {
    state.data = d; state.me = d.me;
    updateSavedNick(d.me.uid || state.uid, d.me.nick);
    $('me-nick-top').textContent = d.me.nick;
    $('me-avatar-top').innerHTML = avatarInner(d.me.avatar);
    $('rail-avatar').title = (d.me.nick || '我的资料') + ' · 我的资料';
    const admin = !!d.me.isAdmin;
    $('rail-members').style.display = admin ? '' : 'none';
    if (!admin && state.view === 'members') switchView('chats');
    // 被移出群/群被解散后，当前打开的会话会立刻从列表消失，
    // 同步清掉当前会话和缓存，避免留着已无权查看的聊天窗口。
    let dropped = false;
    if (state.current && !(d.chats || []).some(c => c.ch === state.current)) {
      delete state.histories[state.current];
      state.current = null; dropped = true;
    }
    updateRailBadge(); renderList();
    if (dropped) renderChat(); else updateChatHeader();
  });
  socket.on('message', onMessage);
  socket.on('presence', applyPresence);
  socket.on('unread', d => {
    state.data.unread = d.unread || {}; state.data.chats = d.chats || [];
    updateRailBadge(); renderList();
    // 未读清零时立即停止标题/favicon 闪动，不必等用户切回窗口
    if (!(state.data.chats || []).some(c => Number(c.unread) > 0)) stopFlash();
  });
  socket.on('friend_request', d => {
    toast(d.msg || '收到好友申请');
    startFlash('好友申请');
  });
  socket.on('system_message', d => {
    toast(d.text || '系统消息');
    if (d.ch) startFlash('系统消息');
    if (d.ch && state.current === d.ch) appendSys(d.text);
  });
  socket.on('drive_changed', d => {
    if (!d) return;
    if (d.scope === 'public' && state.view === 'public-drive') loadDrive();
    if (d.scope === 'private' && state.view === 'private-drive') loadDrive();
  });
  socket.on('typing', d => {
    if (d.ch !== state.current || d.uid === state.uid) return;
    $('typing-hint').style.display = 'block';
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => $('typing-hint').style.display = 'none', 2500);
  });
  socket.on('connect_error', () => {
    if (!$('app').classList.contains('show')) { $('login-err').textContent = '无法连接服务器，请确认服务已启动'; $('join-btn').disabled = false; }
  });
}
/* 在线状态变化：服务端只广播一条 presence，本地就地更新各个列表，
   不重新拉整份联系人数据。A 先上线、B 后上线（或 B 下线）都会实时同步。 */
function applyPresence(d) {
  if (!state.uid || !d || !d.uid) return;
  const uid = d.uid, online = !!d.online;
  const touch = arr => (arr || []).forEach(x => { if (x && x.uid === uid) x.online = online; });
  touch(state.data.members);
  touch(state.data.friends);
  (state.data.groups || []).forEach(g => touch(g.memberInfo));
  if (state.me && state.me.uid === uid) state.me.online = online;
  renderList(); updateChatHeader(); renderGroupPanel();
}
function setDot(id, n) {
  const el = $(id); if (!el) return;
  el.textContent = n > 99 ? '99+' : n; el.style.display = n ? 'block' : 'none';
}
/* 红点数量只按会话列表里真实可见的未读计算，
   避免服务端 unread 里残留的旧会话导致「列表没未读、任务栏却一直有红点」。 */
function updateRailBadge() {
  const chats = state.data.chats || [];
  const all = chats.reduce((n, c) => n + (Number(c.unread) || 0), 0);
  // 联系人页已改为全体成员，不再展示好友申请红点
  const reqN = 0;
  let groupN = 0;
  chats.forEach(c => {
    if (c.type === 'group') groupN += Number(c.unread) || 0;
  });
  setDot('rail-badge', all);
  setDot('rail-badge-contacts', reqN);
  setDot('rail-badge-groups', groupN);
}
/* 只有正在看该会话、且窗口可见时才真正标已读；
   连续消息合并到一次请求，避免刷接口。 */
const readTimers = {};
function markRead(ch) {
  if (!state.uid || !ch || state.view !== 'chats' || document.hidden || !document.hasFocus()) return;
  clearTimeout(readTimers[ch]);
  readTimers[ch] = setTimeout(() => {
    api('/api/read', {method: 'POST', body: {uid: state.uid, ch}}).catch(() => {});
  }, 150);
}

/* ======================= 视图切换 / 列表 ======================= */
document.querySelectorAll('.rail-btn').forEach(btn => {
  btn.onclick = () => switchView(btn.dataset.view);
});
function switchView(view) {
  stopFlash();
  state.view = view;
  document.querySelectorAll('.rail-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $('list-search').value = ''; state.search = '';
  const isDrive = view === 'public-drive' || view === 'private-drive';
  $('workbench').classList.toggle('drive-mode', isDrive);
  if (isDrive) {
    const scope = view === 'public-drive' ? 'public' : 'private';
    if (state.drive.scope !== scope) {
      state.drive.scope = scope;
      state.drive.folder = '';
      state.drive.q = '';
      state.drive.target = '';
      state.drive.viewingOther = false;
      state.drive.ownerNick = '';
      $('drive-search').value = '';
    }
    if (scope === 'private' && state.me && state.me.isAdmin) loadDriveMembers();
    state.current = null; clearQuote();
    updateDriveHead();
    loadDrive();
    return;
  }
  if (view !== 'chats') { state.current = null; clearQuote(); }
  renderList(); renderChat();
}
function actionButton(icon, title, fn) {
  const b = document.createElement('button');
  b.className = 'icon-btn'; b.innerHTML = icon; b.title = title; b.onclick = fn;
  return b;
}
function renderList() {
  const titles = {chats: '消息', contacts: '联系人', groups: '群聊', members: '成员管理',
                  settings: '设置', 'public-drive': '公共盘', 'private-drive': '个人盘'};
  $('list-title').textContent = titles[state.view];
  $('list-search').placeholder = state.view === 'chats' ? '搜索会话' : state.view === 'contacts' ? '搜索同事' : state.view === 'members' ? '搜索成员' : '搜索群聊';
  const actions = $('list-actions'); actions.innerHTML = '';
  if (state.view === 'chats' || state.view === 'contacts') actions.appendChild(actionButton('<i class="ico i-plus"></i>', '发起会话', openNewChat));
  if (state.view === 'groups') actions.appendChild(actionButton('<i class="ico i-plus"></i>', '创建群聊', openCreateGroup));
  if (state.view === 'members') actions.appendChild(actionButton('<i class="ico i-plus"></i>', '添加成员', openAddUser));
  const q = state.search.trim().toLowerCase();
  const box = $('list-scroll'); box.innerHTML = '';

  if (state.view === 'chats') {
    const chats = (state.data.chats || []).filter(c => !q || (c.title || '').toLowerCase().includes(q));
    if (!chats.length) return void (box.innerHTML = '<div class="empty-hint">暂无会话<br>去联系人里找个同事聊聊吧</div>');
    chats.forEach(c => {
      const row = document.createElement('div');
      row.className = 'row' + (state.current === c.ch ? ' active' : '');
      row.innerHTML =
        '<div class="avatar" style="background:' + esc(c.color) + '">' + avatarInner(c.avatar) + '</div>' +
        '<div class="info"><div class="line1"><span class="name">' + esc(c.title) + '</span>' +
        '<span class="time">' + fmtTime(c.mts) + '</span></div>' +
        '<div class="preview">' + (c.unread ? '<b style="color:var(--accent)">[未读] </b>' : '') + esc(c.last || '开始聊天吧') + '</div></div>' +
        (c.unread ? '<span class="badge">' + (c.unread > 99 ? '99+' : c.unread) + '</span>' : '');
      row.onclick = () => openChat(c.ch);
      box.appendChild(row);
    });
  } else if (state.view === 'contacts') {
    // 公司同事默认都是联系人，不需要先加好友
    const all = (state.data.members || []).filter(m => m.uid !== state.uid &&
      (!q || (m.nick || '').toLowerCase().includes(q) || (m.uid || '').toLowerCase().includes(q)));
    box.appendChild(sectionLabel('全部同事 (' + all.length + ')'));
    if (!all.length) {
      const hint = document.createElement('div');
      hint.className = 'empty-hint'; hint.textContent = '暂无其他成员';
      box.appendChild(hint);
    }
    all.forEach(m => {
      const row = document.createElement('div'); row.className = 'row';
      const tag = m.isAdmin ? '<span class="admin-tag">管理员</span>' : '';
      row.innerHTML = avatarHTML(m) + '<div class="info"><div class="line1"><span class="name">' + esc(m.nick) + '</span>' + tag + '</div>' +
        '<div class="preview">' + (m.online ? '[在线]' : '[离线]') + (m.sig ? ' · ' + esc(m.sig) : '') + '</div></div>' +
        '<div class="extra-actions"><button class="chat">聊天</button></div>';
      row.querySelector('.chat').onclick = e => { e.stopPropagation(); startPrivate(m.uid); };
      row.onclick = () => showFriendCard(m);
      box.appendChild(row);
    });
  } else if (state.view === 'groups') {
    const groups = (state.data.groups || []).filter(g => !q || g.name.toLowerCase().includes(q));
    box.appendChild(sectionLabel('我的群聊 (' + groups.length + ')'));
    if (!groups.length) {
      const hint = document.createElement('div');
      hint.className = 'empty-hint'; hint.textContent = '还没有群聊，点右上角创建一个吧';
      box.appendChild(hint);
    }
    groups.forEach(g => {
      const row = document.createElement('div'); row.className = 'row' + (state.current === groupKey(g.id) ? ' active' : '');
      const ch = state.data.chats.find(c => c.ch === groupKey(g.id));
      row.innerHTML = '<div class="avatar" style="background:' + esc(g.color) + '">' + avatarInner('group') + '</div>' +
        '<div class="info"><div class="line1"><span class="name">' + esc(g.name) + '</span><span class="time">' + (g.members || []).length + ' 人</span></div>' +
        '<div class="preview">' + esc(ch ? ch.last : (g.notice || '点击进入群聊')) + '</div></div>';
      row.onclick = () => openChat(groupKey(g.id));
      box.appendChild(row);
    });
  } else if (state.view === 'members') {
    const members = (state.data.members || []).filter(m => !q || m.nick.toLowerCase().includes(q));
    box.appendChild(sectionLabel('全部成员 (' + members.length + ')', '+ 添加', openAddUser));
    if (!members.length) {
      const hint = document.createElement('div');
      hint.className = 'empty-hint'; hint.textContent = '还没有成员数据';
      box.appendChild(hint);
    }
    members.forEach(m => {
      const row = document.createElement('div'); row.className = 'row';
      const tag = m.isAdmin ? '<span class="admin-tag">管理员</span>' : '';
      row.innerHTML = avatarHTML(m) +
        '<div class="info"><div class="line1"><span class="name">' + esc(m.nick) + '</span>' + tag + '</div>' +
        '<div class="preview">' + (m.uid === state.uid ? '我 · ' : '') + (m.online ? '[在线]' : '[离线]') + '</div></div>';
      if (m.uid !== state.uid) {
        const del = document.createElement('button');
        del.className = 'icon-btn danger'; del.title = '删除成员';
        del.innerHTML = '<i class="ico i-trash"></i>';
        del.onclick = e => { e.stopPropagation(); deleteUser(m); };
        row.appendChild(del);
      }
      box.appendChild(row);
    });
  } else if (state.view === 'settings') {
    const items = [
      ['个人资料', '修改昵称、头像和签名'],
      ['修改密码', '输入原密码后设置新密码'],
      ['桌面通知', notifyEnabled ? '已开启：系统通知常驻右下角，需点击关闭' : '已关闭：点击开启'],
      ['消息提示音', notifySound ? '已开启：来消息响一声，@你响双音' : '已关闭：点击开启'],
      ['外观主题', '切换亮色 / 暗色'],
      ['退出登录', '保留账号数据，下次输入密码继续'],
    ];
    items.forEach((it, i) => {
      const row = document.createElement('div'); row.className = 'row';
      row.innerHTML = '<div class="avatar" style="background:var(--accent)">' + ['🙂','🔑','🔔','🎵','🎨','🚪'][i] + '</div>' +
        '<div class="info"><div class="line1"><span class="name">' + it[0] + '</span></div><div class="preview">' + it[1] + '</div></div>';
      row.onclick = () => {
        if (i === 0) showSettings();
        if (i === 1) showChangePassword();
        if (i === 2) toggleNotify();
        if (i === 3) toggleNotifySound();
        if (i === 4) toggleTheme();
        if (i === 5) logout();
      };
      box.appendChild(row);
    });
  }
}
function sectionLabel(text, linkText, linkFn) {
  const el = document.createElement('div'); el.className = 'section-label';
  el.innerHTML = '<span>' + esc(text) + '</span>' + (linkText ? '<span class="link">' + esc(linkText) + '</span>' : '');
  if (linkFn) el.querySelector('.link').onclick = linkFn;
  return el;
}
$('list-search').addEventListener('input', e => { state.search = e.target.value; renderList(); });
$('top-search').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const q = e.target.value.trim(); if (!q) return;
  switchView('contacts'); state.search = q; $('list-search').value = q; renderList();
});

/* ======================= 弹窗 ======================= */
function closeModal() { $('modal-root').classList.remove('show'); }
$('modal-mask').onclick = closeModal;
function copyText(text) {
  const done = () => toast('已复制到剪贴板');
  const fallback = () => {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); }
    catch (e) { toast('复制失败，请手动选中地址'); }
    document.body.removeChild(ta);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  } else fallback();
}
function showModal(title, bodyHTML, buttons) {
  $('modal-box').innerHTML =
    '<div class="modal-head"><h3>' + esc(title) + '</h3><button class="icon-btn" data-close>×</button></div>' +
    '<div class="modal-body">' + bodyHTML + '</div>' +
    '<div class="modal-foot"></div>';
  $('modal-box').querySelector('[data-close]').onclick = closeModal;
  const foot = $('modal-box').querySelector('.modal-foot');
  (buttons || []).forEach(b => {
    const btn = document.createElement('button');
    btn.className = 'btn ' + (b.cls || ''); btn.textContent = b.text; btn.onclick = b.onClick;
    foot.appendChild(btn);
  });
  $('modal-root').classList.add('show');
  return $('modal-box').querySelector('.modal-body');
}
function confirmBox(title, msg, yes) {
  showModal(title, '<div style="line-height:1.8">' + esc(msg) + '</div>', [
    {text: '取消', onClick: closeModal},
    {text: '确定', cls: 'primary', onClick: () => { closeModal(); yes(); }}
  ]);
}

/* ---------- 管理员在成员管理页添加公司成员 ---------- */
function openAddUser() {
  if (!state.me || !state.me.isAdmin) return toast('只有管理员可以添加成员');
  const body = showModal('添加公司成员',
    '<div class="field"><label>成员姓名</label><input id="au-name" maxlength="20" placeholder="成员登录时使用的姓名"></div>' +
    '<div class="field"><label>初始密码（至少 6 位）</label><input id="au-pass" type="password" maxlength="64" placeholder="请告知该成员"></div>' +
    '<div class="login-tip" style="margin-top:-4px">添加后成员即可用「姓名 + 初始密码」登录，密码可在设置中自行修改。</div>',
    [{text: '取消', onClick: closeModal},
     {text: '添加', cls: 'primary', onClick: async () => {
       const nick = body.querySelector('#au-name').value.trim();
       const password = body.querySelector('#au-pass').value;
       if (!nick || password.length < 6) return toast('请填写姓名和至少 6 位密码');
       try {
         const r = await api('/api/admin/add_user', {
           method: 'POST', body: {uid: state.uid, nick, password}
         });
         closeModal();
         toast('成员「' + r.user.nick + '」已添加，初始密码：' + password);
       } catch (e) { toast(e.message); }
     }}]);
}

/* ---------- 管理员删除公司成员 ---------- */
function deleteUser(m) {
  if (!state.me || !state.me.isAdmin) return toast('只有管理员可以删除成员');
  confirmBox('删除成员',
    '确定删除「' + m.nick + '」吗？该成员会立即退出且无法再登录；聊天记录和个人盘文件会保留。',
    async () => {
      try {
        await api('/api/admin/delete_user', {method: 'POST',
          body: {uid: state.uid, target: m.uid}});
        state.data.members = (state.data.members || []).filter(x => x.uid !== m.uid);
        if (state.drive.target === m.uid) {
          state.drive.target = ''; state.drive.viewingOther = false; state.drive.ownerNick = '';
          if (state.view === 'private-drive') loadDrive();
        }
        renderList();
        toast('成员「' + m.nick + '」已删除');
      } catch (e) { toast(e.message); }
    });
}

/* ---------- 添加好友 ---------- */
function openAddFriend() {
  const body = showModal('添加好友',
    '<div class="field"><label>搜索昵称或账号</label><input id="f-search" placeholder="输入对方昵称"></div>' +
    '<div class="field"><label>验证消息</label><input id="f-note" placeholder="你好，我是…"></div>' +
    '<div id="f-results" class="mini-list"></div>', []);
  const results = body.querySelector('#f-results');
  const render = list => {
    if (!list.length) { results.innerHTML = '<div class="empty-hint">没有找到用户</div>'; return; }
    results.innerHTML = '';
    list.forEach(u => {
      const row = document.createElement('div'); row.className = 'mini-row';
      row.innerHTML = avatarHTML(u) + '<div class="grow">' + esc(u.nick) + '<div class="preview">' + (u.online ? '在线' : '离线') + '</div></div>' +
        '<button class="btn primary add">添加</button>';
      row.querySelector('.add').onclick = async () => {
        try {
          await api('/api/friend/request', {method: 'POST', body: {from: state.uid, to: u.uid, note: body.querySelector('#f-note').value.trim()}});
          toast('已发送好友申请'); closeModal();
        } catch (e) { toast(e.message); }
      };
      results.appendChild(row);
    });
  };
  const search = async () => {
    try {
      const r = await api('/api/users?q=' + encodeURIComponent(body.querySelector('#f-search').value.trim()) + '&uid=' + state.uid);
      render(r.users);
    } catch (e) { toast(e.message); }
  };
  body.querySelector('#f-search').addEventListener('input', search);
  search();
}
async function respond(id, accept) {
  try {
    await api('/api/friend/respond', {method: 'POST', body: {uid: state.uid, id, accept}});
    toast(accept ? '已添加好友' : '已忽略申请');
  } catch (e) { toast(e.message); }
}
function removeFriend(f) {
  confirmBox('删除好友', '确定要删除好友「' + f.nick + '」吗？聊天记录会保留。', async () => {
    try { await api('/api/friend/remove', {method: 'POST', body: {uid: state.uid, fid: f.uid}}); toast('已删除好友'); }
    catch (e) { toast(e.message); }
  });
}

/* ---------- 好友名片 ---------- */
function showFriendCard(f) {
  const body = showModal('成员资料',
    '<div style="text-align:center;padding:8px 0 16px">' +
    '<div class="avatar" style="width:64px;height:64px;margin:0 auto 10px;font-size:32px;background:' + esc(f.color) + '">' + avatarInner(f.avatar) + '</div>' +
    '<b style="font-size:16px">' + esc(f.nick) + '</b><div class="preview" style="margin-top:6px">' + esc(f.sig || '这个人很懒') + '</div></div>',
    [{text: '发消息', cls: 'primary', onClick: () => { closeModal(); startPrivate(f.uid); }},
     {text: '关闭', onClick: closeModal}]);
}

/* ---------- 创群 ---------- */
async function openCreateGroup() {
  let members = [];
  try {
    const r = await api('/api/members?uid=' + encodeURIComponent(state.uid));
    members = r.members || [];
  } catch (e) { toast(e.message); return; }
  const body = showModal('创建群聊',
    '<div class="field"><label>群名称</label><input id="g-name" maxlength="30" placeholder="例如：飞意科技"></div>' +
    '<div class="field"><label>选择同事（默认全选，可取消勾选）</label>' +
      '<div class="pick-tools">' +
        '<input id="g-search" class="pick-search" placeholder="搜索同事">' +
        '<button type="button" class="pick-btn" id="g-all">全选</button>' +
        '<button type="button" class="pick-btn" id="g-none">清空</button>' +
        '<span class="pick-count" id="g-count"></span>' +
      '</div>' +
      '<div id="g-members" class="mini-list">' +
        (members.length ? members.map(u =>
          '<label class="mini-row mini-row-label" data-key="' + esc(((u.nick || '') + ' ' + (u.uid || '')).toLowerCase()) + '">' +
            '<input type="checkbox" value="' + esc(u.uid) + '" checked>' +
            avatarHTML(u) +
            '<div class="grow">' + esc(u.nick) + (u.isAdmin ? ' <span class="admin-tag">管理员</span>' : '') + '</div>' +
            '<span class="mini-state' + (u.online ? ' on' : '') + '">' + (u.online ? '在线' : '离线') + '</span>' +
          '</label>').join('') : '<div class="empty-hint">公司还没有其他成员</div>') +
      '</div></div>', [
      {text: '取消', onClick: closeModal},
      {text: '创建', cls: 'primary', onClick: async () => {
        const name = body.querySelector('#g-name').value.trim();
        if (!name) return toast('请输入群名称');
        const picked = Array.from(body.querySelectorAll('#g-members input:checked')).map(x => x.value);
        try {
          const r = await api('/api/group/create', {method: 'POST', body: {uid: state.uid, name, members: picked}});
          closeModal(); toast('群聊创建成功'); switchView('chats'); openChat(groupKey(r.gid));
        } catch (e) { toast(e.message); }
      }}
    ]);
  const rows = () => Array.from(body.querySelectorAll('#g-members .mini-row-label'));
  const boxes = () => Array.from(body.querySelectorAll('#g-members input[type="checkbox"]'));
  const updateCount = () => {
    const c = body.querySelector('#g-count');
    if (c) c.textContent = '已选 ' + boxes().filter(b => b.checked).length + ' / ' + boxes().length;
  };
  boxes().forEach(b => b.addEventListener('change', updateCount));
  body.querySelector('#g-all').onclick = () => { boxes().forEach(b => b.checked = true); updateCount(); };
  body.querySelector('#g-none').onclick = () => { boxes().forEach(b => b.checked = false); updateCount(); };
  body.querySelector('#g-search').addEventListener('input', e => {
    const q = e.target.value.trim().toLowerCase();
    rows().forEach(r => { r.style.display = (!q || r.dataset.key.indexOf(q) >= 0) ? '' : 'none'; });
  });
  updateCount();
}
async function botAction(gid, action, extra) {
  return api('/api/group/bot', {method: 'POST',
    body: Object.assign({gid, action}, extra || {})});
}
function openBotConfig(g) {
  const draw = d => {
    const url = d.url || (location.origin + '/api/webhook/' + (d.key || ''));
    let body = null;
    const buttons = [
      {text: '复制地址', onClick: () => copyText(url)},
      {text: d.enabled ? '停用' : '启用', cls: d.enabled ? '' : 'primary', onClick: async () => {
        try { const r = await botAction(g.id, d.enabled ? 'disable' : 'enable');
              toast(d.enabled ? '机器人已停用' : '机器人已启用'); draw(r.bot); }
        catch (e) { toast(e.message); }
      }},
      {text: '重置密钥', cls: 'danger', onClick: () => confirmBox('重置 Webhook 密钥',
        '重置后旧地址立即失效，外部系统需要改用新地址。确定继续？', async () => {
          try { const r = await botAction(g.id, 'rotate'); toast('密钥已重置'); draw(r.bot); }
          catch (e) { toast(e.message); }
        })},
      {text: '保存名称', onClick: async () => {
        const name = (body.querySelector('#bot-name') || {}).value || '';
        try { const r = await botAction(g.id, 'name', {name: name.trim()});
              toast('名称已保存'); draw(r.bot); }
        catch (e) { toast(e.message); }
      }},
      {text: '关闭', onClick: closeModal},
    ];
    body = showModal('通知机器人 · ' + g.name,
      '<div class="field"><label>状态：' + (d.enabled ? '已启用，外部可直接发送通知' : '已停用') + '</label></div>' +
      '<div class="field"><label>机器人名称</label><input id="bot-name" maxlength="20" value="' + esc(d.name || '') + '"></div>' +
      '<div class="field"><label>Webhook 地址（外部系统 POST 这个地址）</label>' +
        '<input id="bot-url" readonly value="' + esc(url) + '" onclick="this.select()"></div>' +
      '<div class="login-tip" style="margin-top:0">支持企业微信格式 <b>{"msgtype":"text","text":{"content":"内容"}}</b>，' +
        '也支持简写 <b>{"text":"内容"}</b> 与 markdown。消息会以机器人身份发到本群，限 30 次/分钟。</div>' +
      '<div class="login-tip" style="margin-top:4px">例：curl -X POST &lt;上面的地址&gt; -H \'Content-Type: application/json\' -d \'{"text":"部署完成"}\'</div>',
      buttons);
  };
  api('/api/group/bot?gid=' + encodeURIComponent(g.id)).then(d => draw(d.bot)).catch(e => toast(e.message));
}
function openGroupInfo(g) {
  const ch = groupKey(g.id);
  const friends = (state.data.members || []).filter(f => f.uid !== state.uid && !(g.members || []).includes(f.uid));
  const buttons = [
    {text: '退出群聊', cls: 'danger', onClick: () => confirmBox('退出群聊', '确定退出「' + g.name + '」吗？', async () => {
        try { await api('/api/group/leave', {method: 'POST', body: {uid: state.uid, gid: g.id}}); closeModal(); toast('已退出群聊'); switchView('groups'); }
        catch (e) { toast(e.message); }
      })},
    {text: '关闭', onClick: closeModal},
    {text: '邀请', cls: 'primary', onClick: async () => {
      const picks = Array.from(body.querySelectorAll('#invite-list input:checked')).map(x => x.value);
      if (!picks.length) return toast('请先勾选同事');
      try { await api('/api/group/invite', {method: 'POST', body: {uid: state.uid, gid: g.id, members: picks}}); closeModal(); toast('邀请成功'); }
      catch (e) { toast(e.message); }
    }},
  ];
  if (g.bot && g.bot.canManage) {
    buttons.splice(1, 0, {text: '通知机器人', onClick: () => openBotConfig(g)});
  }
  const body = showModal('群资料',
    '<div class="field"><label>群名称：' + esc(g.name) + '（' + (g.members || []).length + ' 人）</label></div>' +
    (g.bot && g.bot.enabled ? '<div class="field"><label>通知机器人：' + esc(g.bot.name || '通知机器人') + ' 已启用</label></div>' : '') +
    '<div class="field"><label>群成员</label><div class="mini-list">' +
      (g.memberInfo || []).map(m => '<div class="mini-row">' + avatarHTML(m) + '<div class="grow">' + esc(m.nick) + (m.uid === g.owner ? '（群主）' : '') + '</div>' +
        '<span class="preview">' + (m.online ? '在线' : '离线') + '</span></div>').join('') + '</div></div>' +
    (friends.length ? '<div class="field"><label>邀请同事入群</label><div id="invite-list" class="mini-list">' +
      friends.map(f => '<label class="mini-row"><input type="checkbox" value="' + f.uid + '">' + avatarHTML(f) + '<div class="grow">' + esc(f.nick) + '</div></label>').join('') + '</div></div>' : ''),
    buttons);
}

/* ---------- 设置 ---------- */
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('feiyi_theme', next);
  toast(next === 'dark' ? '已切换到暗色主题' : '已切换到亮色主题');
}
function showSettings() {
  const me = state.me || {};
  const body = showModal('个人资料',
    '<div class="field"><label>头像</label><div id="avatar-picks" class="avatar-picks">' +
      AVATAR_CHOICES.map(a => '<span class="' + (a === me.avatar ? 'sel' : '') + '" data-a="' + a + '" title="默认头像">' +
        '<img src="/avatar/' + a + '.svg" alt=""></span>').join('') + '</div></div>' +
    '<div class="field"><label>昵称</label><input id="p-nick" maxlength="20" value="' + esc(me.nick) + '"></div>' +
    '<div class="field"><label>个性签名</label><input id="p-sig" maxlength="80" value="' + esc(me.sig) + '"></div>', [
      {text: '取消', onClick: closeModal},
      {text: '保存', cls: 'primary', onClick: async () => {
        const pick = body.querySelector('.avatar-picks .sel');
        try {
          const newNick = body.querySelector('#p-nick').value.trim();
          await api('/api/profile', {method: 'POST', body: {
            uid: state.uid, nick: newNick,
            avatar: pick ? pick.dataset.a : 'av01', sig: body.querySelector('#p-sig').value.trim()
          }});
          updateSavedNick(state.uid, newNick);
          $('nick-input').value = newNick;
          closeModal(); toast('资料已保存');
        } catch (e) { toast(e.message); }
      }}
    ]);
  body.querySelectorAll('.avatar-picks span').forEach(s => {
    s.onclick = () => {
      body.querySelectorAll('.avatar-picks span').forEach(x => x.classList.remove('sel'));
      s.classList.add('sel');
    };
  });
}
function showChangePassword() {
  const body = showModal('修改密码',
    '<div class="field"><label>原密码</label><input id="pw-old" type="password" placeholder="当前登录密码"></div>' +
    '<div class="field"><label>新密码（至少 6 位）</label><input id="pw-new" type="password" placeholder="新登录密码"></div>' +
    '<div class="field"><label>确认新密码</label><input id="pw-new2" type="password" placeholder="再输入一次"></div>', [
      {text: '取消', onClick: closeModal},
      {text: '保存', cls: 'primary', onClick: async () => {
        const oldPass = body.querySelector('#pw-old').value;
        const newPass = body.querySelector('#pw-new').value;
        const newPass2 = body.querySelector('#pw-new2').value;
        if (newPass.length < 6) return toast('新密码至少 6 位');
        if (newPass !== newPass2) return toast('两次输入的新密码不一致');
        try {
          await api('/api/password', {method: 'POST', body: {uid: state.uid, oldPass, newPass}});
          closeModal(); toast('密码已修改，下次登录请使用新密码');
        } catch (e) { toast(e.message); }
      }}
    ]);
}
function logout() {
  confirmBox('退出登录', '账号、同事和群聊都会保留，下次输入密码即可继续。', () => {
    // 只清会话，不清 uid / 账号列表 / 好友群数据
    try { socket.disconnect(); } catch (e) {}
    socket = null; state.uid = null; state.sid = null; state.token = ''; state.me = null;
    state.data = {friends: [], groups: [], requests: {in: [], out: []}, chats: [], unread: {}};
    state.histories = {}; state.current = null; clearQuote(); stopFlash();
    $('app').classList.remove('show'); $('login').style.display = 'flex';
    const last = savedAccounts()[0];
    $('nick-input').value = last ? last.nick : (localStorage.getItem('feiyi_nick') || '');
    $('pass-input').value = '';
    $('login-err').textContent = '';
    $('join-btn').disabled = false;
    $('pass-input').focus();
  });
}
function startPrivate(uid) {
  const f = (state.data.members || []).find(x => x.uid === uid) ||
    (state.data.friends || []).find(x => x.uid === uid);
  const ch = 'p:' + [state.uid, uid].sort().join(':');
  if (!state.data.chats.some(c => c.ch === ch)) {
    state.data.chats.unshift(f
      ? {ch, title: f.nick, color: f.color, avatar: f.avatar, type: 'private', peer: uid, last: '', mts: Date.now(), unread: 0}
      : {ch, title: uid.slice(0, 8), color: '#12b7f5', avatar: '🙂', type: 'private', peer: uid, last: '', mts: Date.now(), unread: 0});
  }
  switchView('chats'); openChat(ch);
}
function openNewChat() {
  const members = (state.data.members || []).filter(m => m.uid !== state.uid);
  if (!members.length) return toast('暂无其他成员');
  const body = showModal('发起会话', '<div id="new-chat-list" class="mini-list">' +
    members.map(m => '<div class="mini-row" data-uid="' + m.uid + '">' + avatarHTML(m) + '<div class="grow">' + esc(m.nick) + '</div><span class="preview">' + (m.online ? '在线' : '离线') + '</span></div>').join('') + '</div>', []);
  body.querySelectorAll('.mini-row').forEach(r => r.onclick = () => { closeModal(); startPrivate(r.dataset.uid); });
}

/* ======================= 公共盘 / 个人盘 ======================= */
function driveIsPublic() { return state.drive.scope !== 'private'; }
/* 盘接口带登录 token 作为身份凭据（下载走 <a href> 只能放 URL 参数） */
function driveParams(extra) {
  return Object.assign({uid: state.uid || '', sid: state.sid || '',
                        token: state.token || ''}, extra || {});
}
function driveQuery(extra) {
  return new URLSearchParams(driveParams(extra)).toString();
}

function updateDriveHead() {
  const d = state.drive, pub = driveIsPublic();
  $('drive-icon').className = 'ico ' + (pub ? 'i-cloud' : 'i-user');
  $('drive-name').textContent = pub ? '公共盘'
    : (d.viewingOther ? (d.ownerNick || '成员') + ' 的个人盘' : '个人盘');
  $('drive-sub').textContent = pub ? '公司成员共享，所有人都能上传和下载'
    : (d.viewingOther ? '管理员查看（可删除）' : '仅自己可见，其他成员无法访问');
  const sel = $('drive-member');
  const canPick = !pub && !!(state.me && state.me.isAdmin);
  sel.classList.toggle('show', canPick);
  if (canPick) sel.value = d.target || '';
}

/* 管理员个人盘页的成员选择器：列出全公司成员（排除自己） */
async function loadDriveMembers() {
  const sel = $('drive-member');
  try {
    const d = await api('/api/members?uid=' + encodeURIComponent(state.uid || '') + '&includeDeleted=1');
    const cur = state.drive.target || '';
    const list = (d.members || []).filter(m => m.uid !== state.uid);
    sel.innerHTML = '<option value="">我的个人盘</option>' +
      list.map(m => '<option value="' + esc(m.uid) + '">' + esc(m.nick) +
        (m.deleted ? '（已删除）' : '') + ' 的个人盘</option>').join('');
    if (cur && !list.some(m => m.uid === cur)) {
      state.drive.target = '';
      if (state.view === 'private-drive') loadDrive();
    }
    sel.value = state.drive.target || '';
    updateDriveHead();
  } catch (e) { /* 成员列表加载失败不影响盘本身 */ }
}

function loadDrive(folder) {
  if (folder !== undefined) state.drive.folder = folder || '';
  const d = state.drive;
  const scope = d.scope;
  $('drive-list').innerHTML = '<div class="drive-empty">正在加载…</div>';
  api('/api/drive?' + driveQuery({scope: scope, folder: d.folder || '',
    target: scope === 'private' ? (d.target || '') : ''}))
    .then(r => {
      if (d.scope !== scope) return; // 切页签后丢弃旧响应
      d.folder = r.folder || '';
      d.path = r.path || [];
      d.folders = r.folders || [];
      d.files = r.files || [];
      d.total = r.total || 0;
      d.isAdmin = !!r.isAdmin;
      d.viewingOther = !!r.viewingOther;
      d.ownerNick = r.ownerNick || '';
      if (scope === 'private' && d.viewingOther && r.ownerUid) d.target = r.ownerUid;
      d.limitBytes = (r.limitBytes === null || r.limitBytes === undefined ||
        isNaN(Number(r.limitBytes)))
        ? state.driveLimit[scope].maxBytes : Number(r.limitBytes);
      d.limitText = r.limitText || state.driveLimit[scope].text;
      updateDriveHead();
      renderDrive();
    })
    .catch(e => {
      if (d.scope !== scope) return;
      if (scope === 'private' && d.target) {
        d.target = ''; d.viewingOther = false; d.ownerNick = '';
        updateDriveHead(); loadDrive(); return;
      }
      $('drive-list').innerHTML = '<div class="drive-empty">' + esc(e.message) + '</div>';
    });
}

function renderDrive() {
  const d = state.drive, pub = d.scope === 'public';
  // 公共盘只有管理员能删；个人盘本人可删；管理员查看成员盘时也可删。
  const canDelete = item => pub ? d.isAdmin : true;
  $('drive-newfolder').style.display = d.viewingOther ? 'none' : '';
  $('drive-upload').style.display = d.viewingOther ? 'none' : '';

  // 面包屑
  let pathHTML = '<span class="crumb' + (d.path.length ? '' : ' cur') + '" data-folder="">全部文件</span>';
  d.path.forEach((p, i) => {
    pathHTML += '<span class="sep">/</span><span class="crumb' +
      (i === d.path.length - 1 ? ' cur' : '') + '" data-folder="' + esc(p.id) + '">' +
      esc(p.name) + '</span>';
  });
  $('drive-path').innerHTML = pathHTML;
  $('drive-path').querySelectorAll('.crumb').forEach(el => {
    if (el.classList.contains('cur')) return;
    el.onclick = () => loadDrive(el.dataset.folder || '');
  });

  const noUpload = d.limitBytes === 0;
  const limitText = d.limitText || state.driveLimit[d.scope].text || '禁止上传';
  const label = pub ? '公共盘'
    : (d.viewingOther ? (d.ownerNick || '成员') + ' 的个人盘' : '个人盘');
  $('drive-limit').textContent = label + ' · ' +
    d.folders.length + ' 个文件夹 / ' + d.files.length + ' 个文件' +
    (d.viewingOther ? ' · 管理员可删除'
      : (noUpload ? ' · 当前环境禁止上传' : ' · 单文件 ≤ ' + limitText));
  $('drive-upload').disabled = noUpload || d.viewingOther;
  $('drive-upload').title = d.viewingOther ? '管理员查看时不能上传'
    : (noUpload ? '当前环境禁止上传文件' : '上传文件');
  if (noUpload || d.viewingOther) $('drive-file').value = '';

  const q = (d.q || '').trim().toLowerCase();
  const folders = d.folders.filter(f => !q || (f.name || '').toLowerCase().includes(q));
  const files = d.files.filter(f => !q || (f.name || '').toLowerCase().includes(q));

  let html = '';
  folders.forEach(f => {
    html += '<div class="drive-row">' +
      '<div class="drive-name folder" data-open="' + esc(f.id) + '" title="' + esc(f.name) + '">' +
        '<i class="ico i-folder"></i><span>' + esc(f.name) + '</span></div>' +
      '<div class="muted">—</div>' +
      '<div class="muted drive-owner">' + esc(f.ownerNick || '') + '</div>' +
      '<div class="muted drive-time">' + fmtFull(f.mts) + '</div>' +
      '<div class="drive-actions">' +
        (canDelete(f) ? '<button class="danger" data-del-folder="' + esc(f.id) + '" title="删除文件夹"><i class="ico i-trash"></i></button>' : '') +
      '</div></div>';
  });
  files.forEach(f => {
    html += '<div class="drive-row">' +
      '<div class="drive-name" data-dl="' + esc(f.id) + '" title="点击下载：' + esc(f.name) + '">' +
        '<i class="ico i-file"></i><span>' + esc(f.name) + '</span></div>' +
      '<div class="muted">' + sizeText(f.size) + '</div>' +
      '<div class="muted drive-owner">' + esc(f.ownerNick || '') + '</div>' +
      '<div class="muted drive-time">' + fmtFull(f.mts) + '</div>' +
      '<div class="drive-actions">' +
        '<button data-dl="' + esc(f.id) + '" title="下载"><i class="ico i-download"></i></button>' +
        (canDelete(f) ? '<button class="danger" data-del-file="' + esc(f.id) + '" title="删除"><i class="ico i-trash"></i></button>' : '') +
      '</div></div>';
  });
  if (!html) {
    html = '<div class="drive-empty">' + (q ? '没有匹配的文件'
      : '这个文件夹还是空的<br>点右上角「上传文件」，或把文件拖到这里') + '</div>';
  }
  $('drive-list').innerHTML = html;

  $('drive-list').querySelectorAll('[data-open]').forEach(el => {
    el.onclick = () => loadDrive(el.dataset.open);
  });
  $('drive-list').querySelectorAll('[data-dl]').forEach(el => {
    el.onclick = e => { e.stopPropagation(); downloadDriveFile(el.dataset.dl); };
  });
  $('drive-list').querySelectorAll('[data-del-file]').forEach(el => {
    el.onclick = e => { e.stopPropagation(); deleteDriveItem('file', el.dataset.delFile); };
  });
  $('drive-list').querySelectorAll('[data-del-folder]').forEach(el => {
    el.onclick = e => { e.stopPropagation(); deleteDriveItem('folder', el.dataset.delFolder); };
  });
}

function downloadDriveFile(id) {
  if (!id) return;
  const d = state.drive;
  const url = '/api/drive/download?' + driveQuery({scope: d.scope, id: id,
    target: d.scope === 'private' ? (d.target || '') : ''});
  const a = document.createElement('a');
  a.href = url; a.download = '';
  document.body.appendChild(a); a.click(); a.remove();
}

function deleteDriveItem(kind, id) {
  const d = state.drive;
  const item = (kind === 'folder' ? d.folders : d.files).find(x => x.id === id);
  if (!item) return;
  const tip = (kind === 'folder' ? '文件夹里的文件也会一并删除。' : '') +
    (d.viewingOther ? ' 管理员操作。' : '');
  confirmBox(kind === 'folder' ? '删除文件夹' : '删除文件',
    '确定删除「' + item.name + '」吗？' + tip, async () => {
      try {
        await api('/api/drive/delete', {method: 'POST',
          body: driveParams({scope: d.scope, id, kind,
            target: d.scope === 'private' ? (d.target || '') : ''})});
        toast('已删除');
        loadDrive();
      } catch (e) { toast(e.message); }
    });
}

function openNewDriveFolder() {
  if (state.drive.viewingOther) return toast('查看成员盘时不能新建文件夹');
  const body = showModal('新建文件夹',
    '<div class="field"><label>文件夹名称</label>' +
    '<input id="df-name" maxlength="40" placeholder="例如：项目资料"></div>', [
      {text: '取消', onClick: closeModal},
      {text: '创建', cls: 'primary', onClick: async () => {
        const name = body.querySelector('#df-name').value.trim();
        if (!name) return toast('请输入文件夹名称');
        try {
          await api('/api/drive/folder', {method: 'POST', body: driveParams({
            scope: state.drive.scope, name, folder: state.drive.folder || ''
          })});
          closeModal(); toast('文件夹已创建'); loadDrive();
        } catch (e) { toast(e.message); }
      }}
    ]);
  setTimeout(() => { const el = body.querySelector('#df-name'); if (el) el.focus(); }, 30);
}

function uploadDriveFiles(files) {
  const list = Array.from(files || []);
  if (!list.length || !state.uid) return;
  const d = state.drive;
  if (d.viewingOther) { toast('查看成员盘时不能上传文件'); return; }
  if (d.limitBytes === 0) {
    toast(d.limitText || '当前环境禁止上传文件');
    return;
  }
  const scope = d.scope, folder = d.folder || '';
  const limit = {
    maxBytes: (d.limitBytes === undefined || d.limitBytes === null ||
      isNaN(Number(d.limitBytes)))
      ? state.driveLimit[scope].maxBytes : Number(d.limitBytes),
    text: d.limitText || state.driveLimit[scope].text,
  };
  let done = 0;

  const next = i => {
    if (i >= list.length) {
      $('drive-progress').textContent = '';
      if (done) toast('已上传 ' + done + ' 个文件');
      if (state.drive.scope === scope) loadDrive(folder);
      return;
    }
    const file = list[i];
    if (!file.size) { toast('跳过空文件：' + file.name); return next(i + 1); }
    if (file.size > limit.maxBytes) { toast('超过 ' + limit.text + '：' + file.name); return next(i + 1); }
    $('drive-progress').textContent = '上传中 ' + (i + 1) + '/' + list.length + '：' + file.name;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/drive/upload');
    if (state.token) xhr.setRequestHeader('X-Token', state.token);
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) {
        $('drive-progress').textContent = '上传中 ' + (i + 1) + '/' + list.length +
          ' · ' + Math.round(e.loaded / e.total * 100) + '%：' + file.name;
      }
    };
    xhr.onload = () => {
      let r = {};
      try { r = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status >= 200 && xhr.status < 300 && r.ok) done++;
      else toast(file.name + '：' + (r.msg || '上传失败'));
      next(i + 1);
    };
    xhr.onerror = () => { toast(file.name + '：网络错误'); next(i + 1); };
    const fd = new FormData();
    fd.append('file', file);
    fd.append('uid', state.uid || '');
    fd.append('sid', state.sid || '');
    fd.append('token', state.token || '');
    fd.append('scope', scope);
    fd.append('folder', folder);
    xhr.send(fd);
  };
  next(0);
}

$('drive-newfolder').onclick = openNewDriveFolder;
$('drive-upload').onclick = () => $('drive-file').click();
$('drive-file').addEventListener('change', e => { uploadDriveFiles(e.target.files); e.target.value = ''; });
$('drive-member').addEventListener('change', e => {
  const d = state.drive;
  d.target = e.target.value || '';
  d.folder = '';
  d.q = '';
  $('drive-search').value = '';
  loadDrive();
});
$('drive-search').addEventListener('input', e => { state.drive.q = e.target.value; renderDrive(); });
['dragover', 'drop'].forEach(evt => {
  $('drive-panel').addEventListener(evt, e => {
    e.preventDefault();
    if (evt === 'drop' && e.dataTransfer && e.dataTransfer.files.length) {
      uploadDriveFiles(e.dataTransfer.files);
    }
  });
});

/* ======================= 聊天 ======================= */
function openChat(ch) {
  if (!ch) return;
  stopFlash();
  if (state.current !== ch) { clearQuote(); state.mentions = []; hideMentionPanel(); }
  state.current = ch;
  state.view = 'chats';
  document.querySelectorAll('.rail-btn').forEach(b => b.classList.toggle('active', b.dataset.view === 'chats'));
  renderList(); updateChatHeader();
  if (!state.histories[ch]) {
    api('/api/history?uid=' + encodeURIComponent(state.uid) + '&ch=' + encodeURIComponent(ch))
      .then(r => {
        state.histories[ch] = r.messages || [];
        if (state.current === ch) renderMessages();
      }).catch(e => toast(e.message));
  } else {
    renderMessages();
    // 已缓存的历史可能未标记已读，补一次
    api('/api/read', {method: 'POST', body: {uid: state.uid, ch}}).catch(() => {});
  }
  $('input').focus();
}
function updateChatHeader() {
  const head = $('chat-header');
  if (!state.current) {
    head.innerHTML = '<div class="titles"><b>选择一个会话开始聊天</b><small>支持私聊、群聊、表情与文件发送</small></div>';
    renderGroupPanel();
    return;
  }
  const info = chatInfo(state.current);
  let sub = '';
  if (info.type === 'group') {
    const g = (state.data.groups || []).find(x => x.id === info.peer);
    sub = g ? (g.members || []).length + ' 位成员 · 群聊' : '群聊';
  } else {
    const f = (state.data.friends || []).find(x => x.uid === info.peer);
    sub = f ? (f.online ? '在线' : '离线') : '私聊';
  }
  const actions = info.type === 'group'
    ? '<button class="icon-btn" id="member-btn" title="群成员"><i class="ico i-group"></i></button>' +
      '<button class="icon-btn" id="info-btn" title="会话资料"><i class="ico i-dots"></i></button>'
    : '<button class="icon-btn" id="info-btn" title="会话资料"><i class="ico i-dots"></i></button>';
  head.innerHTML = '<div class="avatar" style="background:' + esc(info.color || '#12b7f5') + '">' + avatarInner(info.avatar) + '</div>' +
    '<div class="titles"><b>' + esc(info.title) + '</b><small>' + esc(sub) + '</small></div>' + actions;
  $('info-btn').onclick = () => {
    if (info.type === 'group') {
      const g = (state.data.groups || []).find(x => x.id === info.peer);
      if (g) openGroupInfo(g);
    } else {
      const f = (state.data.friends || []).find(x => x.uid === info.peer);
      if (f) showFriendCard(f);
    }
  };
  if ($('member-btn')) $('member-btn').onclick = () => {
    state.groupPanelOpen = !state.groupPanelOpen;
    renderGroupPanel();
  };
  renderGroupPanel();
}
function renderGroupPanel() {
  const panel = $('group-panel');
  if (!panel) return;
  const info = state.current ? chatInfo(state.current) : null;
  const g = info && info.type === 'group'
    ? (state.data.groups || []).find(x => x.id === info.peer)
    : null;
  if (!g || !state.groupPanelOpen) { panel.classList.add('hidden'); return; }
  panel.classList.remove('hidden');
  const members = (g.memberInfo || []).slice();
  $('group-count').textContent = members.length;
  const q = (state.groupSearch || '').trim().toLowerCase();
  const shown = members.filter(m => !q || (m.nick || '').toLowerCase().includes(q));
  shown.sort((a, b) => {
    const ao = a.uid === g.owner ? 0 : 1;
    const bo = b.uid === g.owner ? 0 : 1;
    if (ao !== bo) return ao - bo;
    if (!!b.online !== !!a.online) return (b.online ? 1 : 0) - (a.online ? 1 : 0);
    return (a.nick || '').localeCompare(b.nick || '');
  });
  if (!shown.length) {
    $('group-members').innerHTML = '<div class="gp-empty">没有匹配的成员</div>';
    return;
  }
  $('group-members').innerHTML = '<div class="gp-title">群主 · 在线 · 离线</div>' + shown.map(m =>
    '<div class="gp-member" data-uid="' + esc(m.uid) + '">' +
      avatarHTML(m) +
      '<div class="gp-info"><div class="gp-name">' + esc(m.nick || '用户') + '</div>' +
      '<div class="gp-sub">' + (m.online ? '在线' : '离线') + (m.isAdmin ? ' · 管理员' : '') + '</div></div>' +
      (m.uid === g.owner ? '<span class="gp-owner">群主</span>' : '') +
      (m.uid !== state.uid ? '<button class="gp-at" title="@ ' + esc(m.nick || '用户') + '">@</button>' : '') +
      '<i class="gp-status' + (m.online ? ' on' : '') + '"></i>' +
    '</div>').join('');
  $('group-members').querySelectorAll('.gp-member').forEach(el => {
    el.onclick = () => {
      const m = shown.find(x => x.uid === el.dataset.uid);
      if (m) showFriendCard(m);
    };
  });
  $('group-members').querySelectorAll('.gp-at').forEach(btn => {
    btn.onclick = e => {
      e.stopPropagation();
      const row = btn.closest('.gp-member');
      const m = shown.find(x => x.uid === row.dataset.uid);
      if (m) mentionAt(m);
    };
  });
}
function renderChat() {
  updateChatHeader();
  renderMessages();
}
function renderMessages() {
  const box = $('messages'); box.innerHTML = '';
  const msgs = state.current ? (state.histories[state.current] || []) : [];
  if (!msgs.length) {
    box.innerHTML = '<div class="empty-hint" style="padding-top:80px"><div style="font-size:46px">💬</div><br>' +
      (state.current ? '还没有消息，打个招呼吧～' : '选择左侧会话开始聊天') + '</div>';
    return;
  }
  let lastDay = '';
  msgs.forEach(m => {
    const d = dayKey(m.mts);
    if (d !== lastDay) { lastDay = d; box.appendChild(dateSeparator(m.mts)); }
    box.appendChild(buildMessage(m));
  });
  box.scrollTop = box.scrollHeight;
}
function dateSeparator(ms) {
  const el = document.createElement('div'); el.className = 'date-sep';
  el.innerHTML = '<span>' + fmtFull(ms) + '</span>'; return el;
}
function appendSys(text) {
  const box = $('messages');
  const el = document.createElement('div'); el.className = 'sys-msg';
  el.innerHTML = '<span>' + esc(text) + '</span>';
  box.appendChild(el); box.scrollTop = box.scrollHeight;
}
function buildFileCard(f) {
  const card = document.createElement('div'); card.className = 'file-card';
  const mime = f.mime || '', url = f.url || '';
  if (mime.startsWith('image/')) {
    const img = document.createElement('img'); img.src = url; img.alt = f.name || '';
    img.onclick = () => window.open(url, '_blank'); card.appendChild(img);
  } else if (mime.startsWith('video/')) {
    const v = document.createElement('video'); v.src = url; v.controls = true; v.preload = 'metadata'; card.appendChild(v);
  } else if (mime.startsWith('audio/')) {
    const a = document.createElement('audio'); a.src = url; a.controls = true; a.preload = 'metadata'; card.appendChild(a);
  }
  const line = document.createElement('div'); line.className = 'file-line';
  line.innerHTML = '<span>' + fileIcon(mime) + '</span><span class="fname" title="' + esc(f.name) + '">' + esc(f.name) + '</span>' +
    '<span class="fsize">' + sizeText(f.size) + '</span><a href="' + esc(url) + '" download="' + esc(f.name) + '">下载</a>';
  card.appendChild(line); return card;
}
/* ---------- @ 群成员 ---------- */
function isGroupChat(ch) { return !!ch && ch.indexOf('g:') === 0; }
function currentGroup() {
  if (!isGroupChat(state.current)) return null;
  const info = chatInfo(state.current);
  return (state.data.groups || []).find(g => g.id === info.peer) || null;
}
function memberNick(uid) {
  const g = currentGroup();
  const m = g && (g.memberInfo || []).find(x => x.uid === uid);
  if (m) return m.nick || '';
  const f = (state.data.friends || []).find(x => x.uid === uid);
  return (f && f.nick) || '';
}
function hideMentionPanel() {
  state.mention.open = false;
  const p = $('mention-panel');
  if (p) p.classList.add('hidden');
}
function canAtAll() {
  const g = currentGroup();
  if (!g) return false;
  return g.owner === state.uid;
}
function showMentionPanel() {
  const g = currentGroup();
  if (!g) return hideMentionPanel();
  const q = (state.mention.query || '').trim().toLowerCase();
  let items = (g.memberInfo || []).filter(m => m.uid !== state.uid &&
    (!q || (m.nick || '').toLowerCase().indexOf(q) >= 0));
  items.sort((a, b) => {
    const ao = a.uid === g.owner ? 0 : 1, bo = b.uid === g.owner ? 0 : 1;
    if (ao !== bo) return ao - bo;
    if (!!b.online !== !!a.online) return (b.online ? 1 : 0) - (a.online ? 1 : 0);
    return (a.nick || '').localeCompare(b.nick || '');
  });
  // @all 全部：仅群主/系统管理员可见；输入 all / 全部 也能匹配
  if (canAtAll() && (!q || 'all'.indexOf(q) >= 0 || '全部'.indexOf(q) >= 0 || '全体'.indexOf(q) >= 0)) {
    items.unshift({uid: '__all__', nick: '所有成员', isAll: true, online: true});
  }
  items = items.slice(0, 8);
  state.mention.items = items;
  state.mention.index = 0;
  const box = $('mention-list');
  if (!items.length) {
    box.innerHTML = '<div class="mp-empty">没有匹配的成员</div>';
  } else {
    box.innerHTML = items.map((m, i) =>
      '<div class="mp-item' + (i === 0 ? ' active' : '') + '" data-i="' + i + '">' +
        (m.isAll
          ? '<span class="mp-all-ava">@</span>'
          : avatarHTML(m)) +
        '<span class="mp-name">' + esc(m.nick || '用户') + '</span>' +
        (m.isAll
          ? '<span class="mp-all-tag">@all</span>'
          : (m.uid === g.owner ? '<span class="mp-owner">群主</span>' : '')) +
        '<span class="mp-tag">' + (m.online ? '在线' : '离线') + '</span>' +
      '</div>').join('');
    box.querySelectorAll('.mp-item').forEach(el => {
      el.onclick = () => { state.mention.index = Number(el.dataset.i); chooseMention(); };
    });
  }
  $('mention-panel').classList.remove('hidden');
  $('emoji-panel').classList.remove('open');
  state.mention.open = true;
}
function highlightMention() {
  const list = $('mention-list');
  list.querySelectorAll('.mp-item').forEach((el, i) => el.classList.toggle('active', i === state.mention.index));
  const active = list.querySelector('.mp-item.active');
  if (active && active.scrollIntoView) active.scrollIntoView({block: 'nearest'});
}
function moveMention(step) {
  const n = state.mention.items.length;
  if (!n) return;
  state.mention.index = (state.mention.index + step + n) % n;
  highlightMention();
}
function updateMentionTrigger() {
  const el = $('input');
  if (!isGroupChat(state.current)) return hideMentionPanel();
  const pos = el.selectionStart == null ? el.value.length : el.selectionStart;
  const m = /@([^\s@]{0,20})$/.exec(el.value.slice(0, pos));
  if (!m) return hideMentionPanel();
  state.mention.start = pos - m[0].length;
  state.mention.query = m[1];
  showMentionPanel();
}
function chooseMention() {
  const item = state.mention.items[state.mention.index];
  if (!item) return hideMentionPanel();
  const el = $('input');
  const pos = el.selectionStart == null ? el.value.length : el.selectionStart;
  const head = el.value.slice(0, state.mention.start);
  const text = item.isAll ? '@all ' : ('@' + (item.nick || '用户') + ' ');
  el.value = head + text + el.value.slice(pos);
  const caret = head.length + text.length;
  hideMentionPanel();
  if (item.isAll) {
    if (canAtAll()) state.mentionAll = true;
  } else {
    rememberMention(item.uid);
  }
  el.focus();
  el.setSelectionRange(caret, caret);
  notifyTyping();
}
function rememberMention(uid) {
  if (uid && uid !== state.uid && state.mentions.indexOf(uid) < 0) state.mentions.push(uid);
}
function mentionAt(m) {
  if (!isGroupChat(state.current)) return;
  const el = $('input');
  const text = '@' + (m.nick || '用户') + ' ';
  const s = el.selectionStart == null ? el.value.length : el.selectionStart;
  const e = el.selectionEnd == null ? el.value.length : el.selectionEnd;
  el.value = el.value.slice(0, s) + text + el.value.slice(e);
  el.setSelectionRange(s + text.length, s + text.length);
  rememberMention(m.uid);
  hideMentionPanel();
  el.focus(); notifyTyping();
}

/* ---------- 引用回复 ---------- */
function setQuote(m) {
  state.quote = {
    id: m.id, ch: m.ch, from: m.from, fromNick: m.fromNick || '用户',
    text: (m.text || (m.files && m.files[0] && m.files[0].name) || '').slice(0, 200),
  };
  $('quote-nick').textContent = state.quote.fromNick;
  $('quote-text').textContent = state.quote.text || '[文件]';
  $('quote-bar').classList.add('show');
  const el = $('input');
  // 群聊里回复某人时，输入框默认自动 @ 该消息发送者（自己发的消息不需要）
  if (state.autoAt && el.value.indexOf(state.autoAt) === 0) el.value = el.value.slice(state.autoAt.length);
  state.autoAt = null;
  if (isGroupChat(state.current) && m.from && m.from !== state.uid) {
    const at = '@' + (m.fromNick || '用户') + ' ';
    if (el.value.indexOf(at) !== 0) el.value = at + el.value;
    state.autoAt = at;
    rememberMention(m.from);
  }
  hideMentionPanel();
  el.focus();
  el.setSelectionRange(el.value.length, el.value.length);
}
function clearQuote() {
  state.quote = null;
  if ($('quote-bar')) $('quote-bar').classList.remove('show');
  const el = $('input');
  // 取消引用时，若自动插入的 @发送者 还没被改动，就一并移除
  if (state.autoAt && el && el.value.indexOf(state.autoAt) === 0) {
    el.value = el.value.slice(state.autoAt.length);
  }
  state.autoAt = null;
}

function buildMessage(m) {
  const mine = m.from === state.uid;
  const mentions = Array.isArray(m.mentions) ? m.mentions : [];
  const atMe = !mine && mentions.some(x => x.uid === state.uid);
  const wrap = document.createElement('div');
  wrap.className = 'msg' + (mine ? ' mine' : '') + (atMe ? ' mention-me' : '');
  const info = {nick: m.fromNick || '用户', color: m.color || '#12b7f5'};
  const content = document.createElement('div'); content.className = 'content';

  // 不显示头像方块，发送者姓名用加粗色条突出显示
  if (!mine) {
    const s = document.createElement('div'); s.className = 'sender';
    s.style.borderLeftColor = info.color;
    s.textContent = info.nick;
    content.appendChild(s);
  }

  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (m.quote) {
    const q = document.createElement('div'); q.className = 'quote';
    q.innerHTML = '回复 <b>' + esc(m.quote.fromNick || '用户') + '</b>：' + renderText(m.quote.text || '');
    bubble.appendChild(q);
  }
  const files = Array.isArray(m.files) ? m.files : [];
  files.forEach(f => bubble.appendChild(buildFileCard(f)));
  if (m.text) {
    const nicks = mentions.map(x => x.nick);
    if (m.atAll) nicks.push('all'); // @all 文本高亮
    const t = document.createElement('div'); t.innerHTML = renderText(m.text, nicks);
    if (files.length || m.quote) t.style.marginTop = '4px';
    bubble.appendChild(t);
  }
  content.appendChild(bubble);
  const stamp = document.createElement('div'); stamp.className = 'stamp';
  stamp.textContent = m.ts || fmtTime(m.mts);
  content.appendChild(stamp);
  wrap.appendChild(content);

  if (m.id) {
    const reply = document.createElement('button');
    reply.className = 'reply-btn'; reply.textContent = '↩ 回复';
    reply.title = '引用这条消息';
    reply.onclick = () => setQuote(m);
    wrap.appendChild(reply);
  }
  return wrap;
}
function onMessage(m) {
  if (!state.uid) return;
  const ch = m.ch;
  if (!state.histories[ch]) state.histories[ch] = [];
  state.histories[ch].push(m);
  desktopNotify(m);
  // 任务栏闪动与桌面通知独立：即使关闭通知，收到消息也会闪
  if (m.from !== state.uid &&
      (document.hidden || !document.hasFocus() || state.view !== 'chats' || state.current !== ch)) {
    startFlash(isMentioned(m) ? '@新消息' : '新消息');
  }
  if (state.current === ch) {
    const box = $('messages');
    const hint = box.querySelector('.empty-hint');
    if (hint) hint.remove();
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
    box.appendChild(buildMessage(m));
    if (stick) box.scrollTop = box.scrollHeight;
    markRead(ch);
  }
}
function notifyTyping() {
  if (!socket || !socket.connected || !state.current) return;
  const t = Date.now();
  if (t - lastTyping < 1800) return;
  lastTyping = t;
  socket.emit('typing', {ch: state.current});
}

/* ======================= 附件 ======================= */
function addFiles(files) {
  Array.from(files || []).forEach(file => {
    if (!file.size) return toast('跳过空文件：' + file.name);
    if (file.size > state.uploadLimit.maxBytes) return toast('超过 ' + state.uploadLimit.text + '：' + file.name);
    if (state.pending.length >= 5) return toast('一条消息最多 5 个文件');
    const id = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const el = document.createElement('div'); el.className = 'pending';
    const isImg = (file.type || '').startsWith('image/');
    el.innerHTML = (isImg ? '<img src="' + URL.createObjectURL(file) + '">' : '<span style="font-size:20px">' + fileIcon(file.type) + '</span>') +
      '<div><div class="pname">' + esc(file.name) + '</div><div class="psize">' + sizeText(file.size) + '</div></div>' +
      '<button class="rm">×</button><div class="prog"></div>';
    el.querySelector('.rm').onclick = () => removePending(id);
    state.pending.push({id, file, el});
    $('pending-bar').appendChild(el);
    $('pending-bar').classList.add('show');
  });
}
function removePending(id) {
  const i = state.pending.findIndex(p => p.id === id);
  if (i < 0) return;
  const p = state.pending[i];
  const img = p.el.querySelector('img');
  if (img) URL.revokeObjectURL(img.src);
  p.el.remove(); state.pending.splice(i, 1);
  if (!state.pending.length) $('pending-bar').classList.remove('show');
}
function clearPending() { state.pending.slice().forEach(p => removePending(p.id)); }
function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');
    if (state.token) xhr.setRequestHeader('X-Token', state.token);
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let d = {}; try { d = JSON.parse(xhr.responseText); } catch (err) {}
      if (xhr.status >= 200 && xhr.status < 300 && d.ok) resolve(d.file);
      else reject(new Error(d.msg || '上传失败'));
    };
    xhr.onerror = () => reject(new Error('网络错误'));
    const fd = new FormData(); fd.append('file', file); fd.append('uid', state.uid || '');
    fd.append('token', state.token || ''); xhr.send(fd);
  });
}

/* ======================= 发送 ======================= */
async function send() {
  if (!socket || !socket.connected || !state.current || state.sending) return;
  const text = $('input').value.trim();
  if (!text && !state.pending.length) return;
  const ch = state.current;
  const files = [];
  if (state.pending.length) {
    state.sending = true; $('send').disabled = true;
    const snapshot = state.pending.slice();
    for (const p of snapshot) {
      const prog = p.el.querySelector('.prog');
      try {
        const info = await uploadFile(p.file, v => { prog.style.width = Math.round(v * 100) + '%'; });
        files.push(info); removePending(p.id);
      } catch (e) { toast(p.file.name + '：' + e.message); }
    }
    state.sending = false; $('send').disabled = false;
    if (state.current !== ch) return;
  }
  if (!text && !files.length) return;
  const quote = (state.quote && state.quote.ch === ch)
    ? {id: state.quote.id, from: state.quote.from, fromNick: state.quote.fromNick, text: state.quote.text}
    : null;
  // 只提交文本里确实还存在的 @，避免用户删掉 @昵称 后仍误通知对方
  const mentions = state.mentions.filter(uid => {
    const nick = memberNick(uid);
    return nick && text.indexOf('@' + nick) >= 0;
  });
  // @all：文本里确实保留了 @all 且当前用户有权限；服务端还会再校验一次权限
  const atAll = /\@all\b/i.test(text) && canAtAll();
  socket.emit('chat', {ch, text, files, quote, mentions, atAll});
  $('input').value = ''; state.mentions = []; state.mentionAll = false;
  hideMentionPanel(); clearQuote();
  $('input').focus();
  $('typing-hint').style.display = 'none';
}
$('send').onclick = send;
$('input').addEventListener('keydown', e => {
  if (state.mention.open) {
    if (e.key === 'ArrowDown') { e.preventDefault(); moveMention(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); moveMention(-1); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); chooseMention(); return; }
    if (e.key === 'Escape') { e.preventDefault(); hideMentionPanel(); return; }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
$('input').addEventListener('input', () => { updateMentionTrigger(); notifyTyping(); });
$('input').addEventListener('click', updateMentionTrigger);
$('input').addEventListener('blur', () => setTimeout(hideMentionPanel, 120));

/* ---------- 表情面板 ---------- */
function buildEmojiPanel() {
  const classic = $('grid-classic'), unicode = $('grid-unicode');
  FACE_DEFS.forEach(d => {
    const el = document.createElement('div'); el.className = 'e';
    el.innerHTML = '<img src="' + FACE_URLS[d[0]] + '" alt="' + d[0] + '" title="' + d[0] + '">';
    el.onclick = () => insert('[' + d[0] + ']');
    classic.appendChild(el);
  });
  UNICODE_EMOJIS.forEach(p => {
    const el = document.createElement('div'); el.className = 'e';
    el.innerHTML = '<img src="/emoji/' + p[1] + '.svg" alt="' + esc(p[0]) + '" title="' + esc(p[0]) + '">';
    el.onclick = () => insert(p[0]); unicode.appendChild(el);
  });
  document.querySelectorAll('#emoji-tabs button').forEach(b => {
    b.onclick = () => {
      document.querySelectorAll('#emoji-tabs button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      $('grid-classic').classList.toggle('hidden', b.dataset.tab !== 'classic');
      $('grid-unicode').classList.toggle('hidden', b.dataset.tab !== 'unicode');
    };
  });
}
function insert(text) {
  const el = $('input');
  const s = el.selectionStart == null ? el.value.length : el.selectionStart;
  const e = el.selectionEnd == null ? el.value.length : el.selectionEnd;
  el.value = el.value.slice(0, s) + text + el.value.slice(e);
  el.setSelectionRange(s + text.length, s + text.length);
  el.focus(); notifyTyping();
}
$('emoji-btn').onclick = e => { e.stopPropagation(); hideMentionPanel(); $('emoji-panel').classList.toggle('open'); };
$('at-btn').onclick = () => {
  if (!isGroupChat(state.current)) return toast('仅群聊可以 @ 成员');
  $('emoji-panel').classList.remove('open');
  const el = $('input');
  const s = el.selectionStart == null ? el.value.length : el.selectionStart;
  el.value = el.value.slice(0, s) + '@' + el.value.slice(s);
  el.focus(); el.setSelectionRange(s + 1, s + 1);
  updateMentionTrigger();
};
document.addEventListener('click', e => {
  const p = $('emoji-panel');
  if (p.classList.contains('open') && !p.contains(e.target) && !$('emoji-btn').contains(e.target)) p.classList.remove('open');
  const mp = $('mention-panel');
  if (mp && !mp.classList.contains('hidden') && !mp.contains(e.target) &&
      e.target !== $('input') && !$('at-btn').contains(e.target)) hideMentionPanel();
});
$('quote-close').onclick = clearQuote;
$('file-btn').onclick = () => $('file-input').click();
$('file-input').addEventListener('change', e => { addFiles(e.target.files); e.target.value = ''; });
['#chat-body', '#composer'].forEach(sel => {
  const el = document.querySelector(sel);
  el.addEventListener('dragover', e => { e.preventDefault(); });
  el.addEventListener('drop', e => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });
});
$('input').addEventListener('paste', e => {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  const files = [];
  for (const it of items) if (it.kind === 'file') { const f = it.getAsFile(); if (f) files.push(f); }
  if (files.length) { e.preventDefault(); addFiles(files); }
});

/* ======================= 启动 ======================= */
const groupKey = gid => 'g:' + gid;
if (localStorage.getItem('feiyi_theme')) document.documentElement.setAttribute('data-theme', localStorage.getItem('feiyi_theme'));
buildEmojiPanel();
$('group-search').addEventListener('input', e => { state.groupSearch = e.target.value; renderGroupPanel(); });
$('group-panel-close').onclick = () => { state.groupPanelOpen = false; renderGroupPanel(); };
(function initLogin() {
  // 兼容旧版本：本地有 uid/nick 但没有账号列表时，补一条
  if (!savedAccounts().length) {
    const oldUid = localStorage.getItem('feiyi_uid');
    const oldNick = localStorage.getItem('feiyi_nick');
    if (oldUid && oldNick) {
      localStorage.setItem('feiyi_accounts', JSON.stringify([{uid: oldUid, nick: oldNick}]));
    }
  }
  renderSavedAccounts();
  const fromUrl = new URLSearchParams(location.search).get('nick');
  const last = savedAccounts()[0];
  const nick = (fromUrl || (last && last.nick) || '').trim();
  if (nick) $('nick-input').value = nick;
  $('pass-input').focus();
})();

