// 教务管理系统 - 教师端公共脚本

function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// 内联事件属性中的 JS 字符串字面量专用（onclick="fn(1, '...')"）。
// 不能用 esc()：esc 会把 ' 转成 &#39;，浏览器解析属性时会还原成 '，从而截断 JS 字符串
// 甚至执行注入代码（存储型 XSS）。这里先做 JS 转义，再做 HTML 属性必需的实体转义。
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

// 弹窗开关（设置成绩比例等 modal 使用）
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// 页面初始化：身份校验 + 用户名 + 导航高亮
async function initTeacherPage() {
    const me = await api('/api/auth/me');
    if (!me || !me.success) return false;
    if (me.user.user_type !== 'teacher') { window.location.href = '/'; return false; }
    const nameEl = document.getElementById('userName');
    if (nameEl) nameEl.textContent = me.user.real_name;
    // 顶部头像（可点击修改）
    const avatarEl = document.getElementById('userAvatar');
    if (avatarEl) {
        if (me.user.avatar) {
            avatarEl.innerHTML = `<img class="avatar-img" src="${esc(me.user.avatar)}" alt="头像" style="width:34px;height:34px;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar" title="点击修改头像">`;
        } else {
            avatarEl.innerHTML = `<div class="avatar-circle" style="background:#1f6feb;color:#fff;cursor:pointer;" title="点击修改头像">${esc(me.user.real_name.slice(-2))}</div>`;
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


async function fillSemesterSelect(selectEl) {
    const meta = await api('/api/common/meta');
    if (!meta || !meta.success) return;
    selectEl.innerHTML = meta.data.semesters.map(s =>
        `<option value="${esc(s)}" ${s === meta.data.current_semester ? 'selected' : ''}>${esc(s)}</option>`).join('');
}

// 课表渲染（与 student.js 一致）
const SECTION_GROUPS = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]];
const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

// ---------- 作息时间 ----------
let SECTION_TIMES = {};

async function loadSectionTimes() {
    if (Object.keys(SECTION_TIMES).length) return SECTION_TIMES;
    const res = await api('/api/common/section-times');
    if (res && res.success) {
        res.data.forEach(r => { SECTION_TIMES[r.section] = { start: r.start_time, end: r.end_time }; });
    }
    return SECTION_TIMES;
}

function sectionRangeText(startSec, endSec) {
    const a = SECTION_TIMES[startSec];
    const b = SECTION_TIMES[endSec] || a;
    return a && b ? `${a.start}-${b.end}` : '';
}

function renderScheduleTable(container, data) {
    const grid = {};
    (data || []).forEach(item => {
        const key = `${item.weekday}-${item.start_section}`;
        (grid[key] = grid[key] || []).push(item);
    });
    let html = '<table class="schedule-table"><thead><tr><th class="section-col">节次</th>';
    WEEKDAY_NAMES.forEach(d => html += `<th>${d}</th>`);
    html += '</tr></thead><tbody>';
    SECTION_GROUPS.forEach(([start, end], gi) => {
        const rangeText = sectionRangeText(start, end);
        html += `<tr><td class="section-col">第${gi + 1}大节<br><span style="font-weight:400;color:#999">${start}-${end}节</span>`
              + (rangeText ? `<br><span style="font-weight:400;color:#1f6feb;font-size:11.5px">${rangeText}</span>` : '')
              + `</td>`;
        for (let wd = 1; wd <= 7; wd++) {
            const items = grid[`${wd}-${start}`] || [];
            html += '<td>' + items.map(it => {
                const wt = it.week_type && it.week_type !== '全周'
                    ? ` <span class="tag ${it.week_type === '单周' ? 'tag-warning' : 'tag-primary'}">${esc(it.week_type)}</span>`
                    : '';
                const t = sectionRangeText(it.start_section, it.end_section);
                return `
                <div class="schedule-cell">
                    <div class="sc-name">${esc(it.course_name)}${wt}</div>
                    ${t ? `<div class="sc-info" style="color:#1f6feb;font-weight:600;">${t}</div>` : ''}
                    <div class="sc-info">${esc(it.weeks || '')}周 ${it.building ? esc(it.building + ' ' + (it.room || '')) : ''}</div>
                </div>`;
            }).join('') + '</td>';
        }
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

// 成绩批量导入弹窗：offeringId 教学班ID，onDone 成功后回调
function openGradeImportDialog(offeringId, courseName, onDone) {
    const old = document.getElementById('gradeImportDialog');
    if (old) old.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal active';
    overlay.id = 'gradeImportDialog';
    overlay.innerHTML = `
        <div class="modal-content" style="width:560px;">
            <div class="modal-header">批量导入成绩：${esc(courseName)}<span class="modal-close" id="giClose">✕</span></div>
            <div class="modal-body">
                <div style="background:#f0f6ff;border:1px solid #d6e6fb;border-radius:4px;padding:12px 14px;font-size:13px;color:#1b4fa0;margin-bottom:16px;">
                    <strong>操作步骤：</strong><br>
                    1. 下载成绩模板（含本课程选课学生名单）；<br>
                    2. 在模板中填写「平时成绩」「考试成绩」两列（0-100）；<br>
                    3. 上传文件，系统按「学号」自动匹配导入。<br>
                    <span style="color:#888;">支持 Excel（.xlsx/.xls）和 CSV。</span>
                </div>
                <div style="margin-bottom:16px;">
                    <button class="btn btn-default btn-sm" id="giDownload">下载成绩模板</button>
                </div>
                <div class="form-group" style="margin-bottom:14px;">
                    <label>选择文件 *</label>
                    <input type="file" id="giFile" accept=".xlsx,.xls,.csv">
                </div>
                <div id="giResult" style="display:none;font-size:13px;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-default" id="giCancel">关闭</button>
                <button class="btn btn-primary" id="giOk" disabled>开始导入</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    document.getElementById('giClose').onclick = close;
    document.getElementById('giCancel').onclick = close;
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

    document.getElementById('giDownload').onclick = () => {
        window.open(`/api/teacher/offering/${offeringId}/grades/template`, '_blank');
    };

    const fileInput = document.getElementById('giFile');
    const okBtn = document.getElementById('giOk');
    fileInput.onchange = () => { okBtn.disabled = !fileInput.files.length; };

    okBtn.onclick = async () => {
        const f = fileInput.files[0];
        if (!f) { toast('请选择文件', 'error'); return; }
        okBtn.disabled = true;
        okBtn.textContent = '导入中...';
        const fd = new FormData();
        fd.append('file', f);
        try {
            const resp = await fetch(`/api/teacher/offering/${offeringId}/grades/import`, { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrfToken() } });
            const data = await resp.json();
            const box = document.getElementById('giResult');
            box.style.display = 'block';
            if (data.success) {
                box.innerHTML = `<div style="padding:12px;background:#edf7e8;border:1px solid #b7e0a8;border-radius:4px;color:#389e0d;">${esc(data.message)}</div>`;
                if (data.errors && data.errors.length) {
                    box.innerHTML += `<div style="margin-top:8px;padding:12px;background:#fdf3e3;border:1px solid #f0d29a;border-radius:4px;color:#d48806;max-height:160px;overflow-y:auto;"><strong>失败明细：</strong><br>${data.errors.map(esc).join('<br>')}</div>`;
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
