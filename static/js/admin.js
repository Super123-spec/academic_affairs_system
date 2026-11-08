// 教务管理系统 - 管理端公共脚本

function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// 内联事件属性中的 JS 字符串字面量专用（onclick="fn(1, '...')"）。
// 不能用 esc()：esc 会把 ' 转成 &#39;，而浏览器解析属性时会把实体还原成 '，从而截断 JS 字符串
// 甚至执行注入代码（存储型 XSS）。这里先做 JS 转义，再只做 HTML 属性必需的实体转义。
function escJs(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\r?\n/g, '\\n')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 把对象安全序列化后放进单引号 HTML 属性（onclick='fn(${jsAttr(x)})'）。
// JSON.stringify 不转义单引号：数据含 ' 时会截断属性边界，形成存储型 XSS。
// 这里按 HTML 属性解码规则先转义 & < ' ：浏览器解码后 JS 拿到的仍是合法 JSON。
function jsAttr(obj) {
    return JSON.stringify(obj)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/'/g, '&#39;');
}

// 读取服务端下发的 CSRF 令牌（双提交 Cookie），写操作需通过请求头回传
function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
}

function toast(message, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

async function api(url, options = {}) {
    try {
        const resp = await fetch(url, { headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() }, ...options });
        if (resp.status === 401) { window.location.href = '/'; return null; }
        if (resp.status === 403) {
            // 403 = 已登录但权限不足（如细分权限/超级管理员），只提示，不登出
            const _d = await resp.json().catch(() => null);
            toast((_d && _d.message) || '无权限访问', 'error');
            return null;
        }
        return await resp.json();
    } catch (e) {
        toast('网络错误，请稍后重试', 'error');
        console.error(e);
        return null;
    }
}

async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    window.location.href = '/';
}

// 页面初始化：注入布局 + 身份校验 + 用户名 + 导航高亮
async function initAdminPage() {
    const me = await api('/api/auth/me');
    if (!me || !me.success) return false;
    if (me.user.user_type !== 'admin') { window.location.href = '/'; return false; }

    injectLayout(me.user);

    // 顶部头像（可点击修改）
    const avatarEl = document.getElementById('userAvatar');
    if (avatarEl) {
        if (me.user.avatar) {
            avatarEl.innerHTML = `<img class="avatar-img" src="${esc(me.user.avatar)}" alt="头像" style="width:34px;height:34px;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar" title="点击修改头像">`;
        } else {
            avatarEl.innerHTML = `<div class="avatar-circle" style="background:#1f6feb;color:#fff;" title="点击修改头像">${esc(me.user.real_name.slice(-2))}</div>`;
        }
        avatarEl.style.cursor = 'pointer';
        // 单击延迟 250ms 打开上传；双击则取消单击、直接放大
        // （否则 click 会抢先弹出上传框，导致双击无法放大）
        let avatarClickTimer = null;
        avatarEl.onclick = () => {
            if (avatarClickTimer) {
                clearTimeout(avatarClickTimer);
                avatarClickTimer = null;
                return;
            }
            avatarClickTimer = setTimeout(() => {
                avatarClickTimer = null;
                openAvatarUpload();
            }, 250);
        };
    }

    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href && currentPath.endsWith(href)) item.classList.add('active');
    });
    return true;
}

const ADMIN_NAV = [
    { group: null, items: [['工作台', 'index.html']] },
    { group: '基础数据', items: [['院系专业班级', 'org.html'], ['教室管理', 'classrooms.html'], ['作息时间', 'section-times.html']] },
    { group: '人员管理', items: [['学生管理', 'students.html'], ['教师管理', 'teachers.html']] },
    { group: '教务管理', items: [['课程管理', 'courses.html'], ['开课管理', 'offerings.html'], ['排课管理', 'schedules.html'], ['专业课程排课', 'major-schedule.html'], ['考试安排', 'exams.html'], ['选课管理', 'enrollments.html'], ['成绩管理', 'grades.html'], ['教学执行计划', 'teaching-plans.html']] },
    { group: '事务处理', items: [['教学项目', 'projects.html'], ['申请审核', 'reviews.html'], ['创新学分', 'innovation-credits.html'], ['证书管理', 'certificates.html'], ['公告管理', 'announcements.html']] },
    { group: '系统', items: [['操作日志', 'logs.html']] },
];

function injectLayout(user) {
    const content = document.getElementById('pageContent');
    const wrapper = document.createElement('div');
    wrapper.className = 'page-wrapper';
    wrapper.innerHTML = `
        <div class="sidebar">
            <div class="logo">
                <div class="logo-clip"><img src="/static/images/logo.png" alt="校徽"></div>
                <div class="logo-text">
                    <div class="logo-title">教务管理后台</div>
                    <div class="logo-sub">贵阳信息科技学院</div>
                </div>
            </div>
            <div class="nav-menu">
                ${ADMIN_NAV.map(g => `
                    ${g.group ? `<div class="nav-group-title">${g.group}</div>` : ''}
                    ${g.items.map(([label, href]) => `<a href="${href}" class="nav-item"><span>${label}</span></a>`).join('')}
                `).join('')}
            </div>
        </div>
        <div class="main-content">
            <div class="header">
                <div class="header-title">贵阳信息科技学院 · 教务管理后台</div>
                <div class="user-info">
                    <span id="userAvatar" style="display:inline-flex;align-items:center;margin-right:8px;"></span>
                    <span>欢迎，<strong id="userName">${esc(user.real_name)}</strong></span>
                    <div class="logout-btn" data-action="logout">退出登录</div>
                </div>
            </div>
        </div>`;
    document.body.insertBefore(wrapper, content);
    wrapper.querySelector('.main-content').appendChild(content);
}

// 元数据缓存
let META = null;
async function loadMeta() {
    if (META) return META;
    const res = await api('/api/common/meta');
    if (res && res.success) META = res.data;
    return META;
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function statusTag(s) {
    return s === '已通过' ? '<span class="tag tag-success">已通过</span>'
        : s === '已拒绝' ? '<span class="tag tag-danger">已拒绝</span>'
        : '<span class="tag tag-warning">待审核</span>';
}

// 通用确认弹窗（替代原生 confirm）：返回 Promise<boolean>
function confirmDialog(message, options = {}) {
    return new Promise(resolve => {
        const old = document.getElementById('confirmDialog');
        if (old) old.remove();
        const overlay = document.createElement('div');
        overlay.className = 'modal active';
        overlay.id = 'confirmDialog';
        overlay.innerHTML = `
            <div class="modal-content" style="width:400px;">
                <div class="modal-header">${esc(options.title || '操作确认')}<span class="modal-close" id="cdClose">✕</span></div>
                <div class="modal-body" style="font-size:14px;color:#444;">${esc(message)}</div>
                <div class="modal-footer">
                    <button class="btn btn-default" id="cdCancel">取消</button>
                    <button class="btn ${options.danger === false ? 'btn-primary' : 'btn-danger'}" id="cdOk">${esc(options.okText || '确定')}</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        const finish = ok => { overlay.remove(); resolve(ok); };
        document.getElementById('cdOk').onclick = () => finish(true);
        document.getElementById('cdCancel').onclick = () => finish(false);
        document.getElementById('cdClose').onclick = () => finish(false);
        overlay.addEventListener('click', e => { if (e.target === overlay) finish(false); });
    });
}

// 通用批量导入弹窗：entityType = 'student'|'teacher'|'course'|'class'；onDone 导入成功后回调（用于刷新列表）
function openImportDialog(entityType, label, onDone) {
    if (typeof onDone === 'string') onDone = window[onDone];
    const old = document.getElementById('importDialog');
    if (old) old.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal active';
    overlay.id = 'importDialog';
    overlay.innerHTML = `
        <div class="modal-content" style="width:560px;">
            <div class="modal-header">批量导入${esc(label)}<span class="modal-close" id="imClose">✕</span></div>
            <div class="modal-body">
                <div style="background:#f0f6ff;border:1px solid #d6e6fb;border-radius:4px;padding:12px 14px;font-size:13px;color:#1b4fa0;margin-bottom:16px;">
                    <strong>支持格式：</strong>Excel（.xlsx/.xls）、CSV<br>
                    <strong>要求：</strong>第一行为表头，列名需与模板一致；必填列不能为空。
                </div>
                <div style="margin-bottom:16px;">
                    <button class="btn btn-default btn-sm" id="imDownload">下载导入模板</button>
                </div>
                <div class="form-group" style="margin-bottom:14px;">
                    <label>选择文件 *</label>
                    <input type="file" id="imFile" accept=".xlsx,.xls,.csv">
                </div>
                <div id="imResult" style="display:none;font-size:13px;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-default" id="imCancel">关闭</button>
                <button class="btn btn-primary" id="imOk" disabled>开始导入</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    document.getElementById('imClose').onclick = close;
    document.getElementById('imCancel').onclick = close;
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

    document.getElementById('imDownload').onclick = () => {
        window.open(`/api/admin/import/${entityType}/template`, '_blank');
    };

    const fileInput = document.getElementById('imFile');
    const okBtn = document.getElementById('imOk');
    fileInput.onchange = () => { okBtn.disabled = !fileInput.files.length; };

    okBtn.onclick = async () => {
        const f = fileInput.files[0];
        if (!f) { toast('请选择文件', 'error'); return; }
        okBtn.disabled = true;
        okBtn.textContent = '导入中...';
        const fd = new FormData();
        fd.append('file', f);
        try {
            const resp = await fetch(`/api/admin/import/${entityType}`, { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrfToken() } });
            const data = await resp.json();
            const box = document.getElementById('imResult');
            box.style.display = 'block';
            if (data.success) {
                box.innerHTML = `
                    <div style="padding:12px;background:#edf7e8;border:1px solid #b7e0a8;border-radius:4px;color:#389e0d;">
                        ${esc(data.message)}
                    </div>`;
                if (data.errors && data.errors.length) {
                    box.innerHTML += `<div style="margin-top:8px;padding:12px;background:#fdf3e3;border:1px solid #f0d29a;border-radius:4px;color:#d48806;max-height:160px;overflow-y:auto;">
                        <strong>失败明细：</strong><br>${data.errors.map(esc).join('<br>')}
                    </div>`;
                }
                if (onDone) onDone();
            } else {
                box.innerHTML = `<div style="padding:12px;background:#fbe9ea;border:1px solid #f5b9bd;border-radius:4px;color:#cf1322;">${esc(data.message)}</div>`;
            }
        } catch (e) {
            toast('导入失败，请重试', 'error');
        } finally {
            okBtn.disabled = false;
            okBtn.textContent = '开始导入';
        }
    };
}

// 通用表单弹窗：fields = [{key, label, type:'text'|'number'|'select', options:[{value,label}], placeholder, required, value}]
// 返回 Promise<{ok:boolean, values:{}}>
function formDialog(title, fields) {
    return new Promise(resolve => {
        const old = document.getElementById('formDialog');
        if (old) old.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal active';
        overlay.id = 'formDialog';
        overlay.innerHTML = `
            <div class="modal-content" style="width:460px;">
                <div class="modal-header">${esc(title)}<span class="modal-close" id="fdClose">✕</span></div>
                <div class="modal-body">
                    ${fields.map(f => {
                        let input;
                        if (f.type === 'select') {
                            input = `<select id="fd_${f.key}">${(f.options || []).map(o =>
                                `<option value="${esc(o.value)}" ${String(o.value) === String(f.value ?? '') ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
                        } else {
                            input = `<input type="${f.type || 'text'}" id="fd_${f.key}" value="${esc(f.value ?? '')}"
                                     placeholder="${esc(f.placeholder || '')}" ${f.required ? 'required' : ''}>`;
                        }
                        return `<div class="form-group"><label>${esc(f.label)}${f.required ? ' *' : ''}</label>${input}</div>`;
                    }).join('')}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-default" id="fdCancel">取消</button>
                    <button class="btn btn-primary" id="fdOk">确定</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        const finish = ok => {
            const values = {};
            if (ok) {
                for (const f of fields) {
                    const el = document.getElementById('fd_' + f.key);
                    if (el) values[f.key] = el.value;
                    if (f.required && (!el || !el.value.trim())) {
                        toast(`请填写「${f.label}」`, 'error');
                        el && el.focus();
                        return;
                    }
                }
            }
            overlay.remove();
            resolve({ ok, values });
        };

        document.getElementById('fdOk').onclick = () => finish(true);
        document.getElementById('fdCancel').onclick = () => finish(false);
        document.getElementById('fdClose').onclick = () => finish(false);
        overlay.addEventListener('click', e => { if (e.target === overlay) finish(false); });
        overlay.addEventListener('keydown', e => { if (e.key === 'Enter') finish(true); });

        const first = overlay.querySelector('input, select');
        if (first) setTimeout(() => first.focus(), 50);
    });
}

// 头像上传（各角色只能改自己的头像）
function openAvatarUpload() {
    const old = document.getElementById('avatarModal');
    if (old) old.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal active';
    overlay.id = 'avatarModal';
    overlay.innerHTML = `
        <div class="modal-content" style="width:420px;">
            <div class="modal-header">修改头像<span class="modal-close" id="avClose">✕</span></div>
            <div class="modal-body">
                <div class="avatar-upload">
                    <div class="avatar-preview" id="avPreview"><span id="avPreviewText">预览</span></div>
                    <div class="avatar-actions">
                        <input type="file" id="avFile" accept="image/*" style="max-width:100%;">
                        <span class="avatar-hint">仅支持 png/jpg/jpeg/gif/webp，大小不超过 5MB</span>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-default" id="avCancel">取消</button>
                <button class="btn btn-primary" id="avOk">上传</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
    const fileInput = document.getElementById('avFile');
    const preview = document.getElementById('avPreview');
    fileInput.addEventListener('change', () => {
        const f = fileInput.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = e => { preview.innerHTML = `<img src="${e.target.result}" alt="预览" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`; };
        reader.readAsDataURL(f);
    });
    const finish = () => overlay.remove();
    document.getElementById('avClose').onclick = finish;
    document.getElementById('avCancel').onclick = finish;
    overlay.addEventListener('click', e => { if (e.target === overlay) finish(); });
    document.getElementById('avOk').onclick = async () => {
        const f = fileInput.files[0];
        if (!f) { toast('请先选择图片', 'error'); return; }
        const fd = new FormData();
        fd.append('file', f);
        const resp = await fetch('/api/avatar', { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrfToken() } });
        let res = null;
        try { res = await resp.json(); } catch (e) {}
        if (res && res.success) {
            toast('头像已更新', 'success');
            finish();
            setTimeout(() => location.reload(), 500);
        } else {
            toast((res && res.message) || '上传失败', 'error');
        }
    };
}

// 双击头像放大查看
function viewAvatar(src) {
    if (!src && this && this.src) src = this.src;
    if (!src) return;
    const old = document.getElementById('avatarViewer');
    if (old) old.remove();
    const viewer = document.createElement('div');
    viewer.className = 'avatar-viewer';
    viewer.id = 'avatarViewer';
    viewer.innerHTML = `<img src="${esc(src)}" alt="头像大图">`;
    document.body.appendChild(viewer);
    viewer.addEventListener('click', () => viewer.remove());
}

// 分页栏渲染：total 总数、page 当前页、pageSize 每页条数、goFn 跳页函数名（全局）
function renderPager(containerId, total, page, pageSize, goFn) {
    const box = document.getElementById(containerId);
    if (!box) return;
    if (!total) { box.innerHTML = ''; return; }
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const btn = (label, p, disabled) =>
        `<button class="btn btn-sm ${disabled ? '' : 'btn-default'}" ${disabled ? 'disabled style="opacity:.4;cursor:not-allowed;"' : ''} data-action="${goFn}" data-arg='[${p}]'>${label}</button>`;
    // 生成页码（最多显示 7 个，带省略）
    let pages = [];
    if (totalPages <= 7) {
        pages = Array.from({ length: totalPages }, (_, i) => i + 1);
    } else {
        pages = [1];
        let lo = Math.max(2, page - 2), hi = Math.min(totalPages - 1, page + 2);
        if (page <= 4) { lo = 2; hi = 6; }
        if (page >= totalPages - 3) { lo = totalPages - 5; hi = totalPages - 1; }
        if (lo > 2) pages.push('...');
        for (let i = lo; i <= hi; i++) pages.push(i);
        if (hi < totalPages - 1) pages.push('...');
        pages.push(totalPages);
    }
    box.innerHTML = `<span style="color:#666;font-size:13px;margin-right:8px;">共 ${total} 条 · 第 ${page}/${totalPages} 页</span>` +
        btn('上一页', page - 1, page <= 1) +
        pages.map(p => p === '...'
            ? '<span style="margin:0 4px;color:#999;">…</span>'
            : `<button class="btn btn-sm ${p === page ? 'btn-primary' : 'btn-default'}" data-action="${goFn}" data-arg='[${p}]'>${p}</button>`).join('') +
        btn('下一页', page + 1, page >= totalPages);
}


// 事件委托：替代内联 on* 属性（配合 CSP script-src 'self'，无 unsafe-inline）
(function () {
    function _args(el) {
        var a = el.getAttribute('data-arg');
        if (a === null || a === '') return [];
        var v;
        try { v = JSON.parse(a); } catch (e) { return [a]; }
        return Array.isArray(v) ? v : [v];
    }
    function _run(el, attr) {
        var fn = el.getAttribute(attr);
        if (!fn) return;
        var f = window[fn];
        if (typeof f !== 'function') return;
        f.apply(el, _args(el));
    }
    function _closest(target) {
        return (target instanceof Element) ? target.closest.bind(target) : null;
    }
    document.addEventListener('click', function (e) {
        var t = e.target; if (!(t instanceof Element)) return;
        var el = t.closest('[data-action]'); if (el) _run(el, 'data-action');
    });
    document.addEventListener('dblclick', function (e) {
        var t = e.target; if (!(t instanceof Element)) return;
        var el = t.closest('[data-dbl]'); if (el) _run(el, 'data-dbl');
    });
    document.addEventListener('change', function (e) {
        var t = e.target; if (!(t instanceof Element)) return;
        var el = t.closest('[data-change]'); if (el) _run(el, 'data-change');
    });
    document.addEventListener('input', function (e) {
        var t = e.target; if (!(t instanceof Element)) return;
        var el = t.closest('[data-input]'); if (el) _run(el, 'data-input');
    });
})();
