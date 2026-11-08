// 教务管理系统 - 学生端公共脚本
// 提供：布局注入（URP 顶部导航）、请求封装、消息提示、课表渲染

const MENU_CONFIG = [
    {
        name: '报名申请', items: [
            ['学籍异动申请', 'apply-status-change.html'],
            ['重修报名', 'apply-retake.html'],
            ['教学项目报名', 'apply-project.html'],
            ['校外课程学分节点替代申请', 'apply-credit-substitute.html'],
        ]
    },
    {
        name: '信息维护', items: [
            ['学生个人信息维护', 'profile-edit.html'],
            ['创新创业学分确认', 'innovation-credit.html'],
            ['学生自主报到注册', 'registration.html'],
            ['分流专业确认', 'major-diversion.html'],
        ]
    },
    {
        name: '选课', items: [
            ['个人课表查询', 'my-schedule.html'],
            ['自主选课', 'course-select.html'],
        ]
    },
    {
        name: '信息查询', items: [
            ['查询个人信息', 'profile.html'],
            ['班级课表查询', 'class-schedule.html'],
            ['个人课表查询', 'my-schedule.html'],
            ['查询空闲教室', 'free-classrooms.html'],
            ['学生选课情况确认', 'my-enrollments.html'],
            ['选课名单查询', 'offering-students.html'],
            ['重修课程查询', 'retake-courses.html'],
            ['学生成绩查询', 'grades.html'],
            ['考试信息查询', 'exams.html'],
            ['学生证书打印', 'certificates.html'],
            ['学生成绩总表打印', 'grade-report.html'],
            ['教学执行计划查看', 'teaching-plan.html'],
        ]
    },
    {
        name: '教学评价', items: [
            ['学生评价', 'evaluate.html'],
            ['过程评价', 'process-evaluate.html'],
        ]
    }
];

// ---------- 工具函数 ----------
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
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
            ...options
        });
        if (resp.status === 401) {
            window.location.href = '/';
            return null;
        }
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

// ---------- 布局注入 ----------
async function initLayout(pageTitle) {
    // 身份校验
    const me = await api('/api/auth/me');
    if (!me || !me.success) return;
    if (me.user.user_type !== 'student') {
        window.location.href = '/';
        return;
    }

    const body = document.body;
    const urpBody = body.querySelector('.urp-body');

    // 顶部蓝色校名栏
    const header = document.createElement('div');
    header.className = 'urp-header';
    header.innerHTML = `
        <div class="logo-clip"><img src="/static/images/logo.png" alt="校徽"></div>
        <div class="school-name">贵阳信息科技学院<span class="old-name">（原贵州大学明德学院）</span></div>
        <div class="header-user">
            <span>${esc(me.user.real_name)}（${esc(me.user.username)}）</span>
            ${me.user.avatar
                ? `<img class="avatar-img" src="${esc(me.user.avatar)}" alt="头像" style="width:34px;height:34px;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar" title="点击修改头像" data-action="openAvatarUpload">`
                : `<div class="avatar-circle" title="点击修改头像" data-action="openAvatarUpload">${esc(me.user.real_name.slice(-2))}</div>`}
            <span class="logout-link" data-action="logout">退出</span>
        </div>`;

    // 菜单栏
    const menubar = document.createElement('div');
    menubar.className = 'urp-menubar';
    menubar.innerHTML = MENU_CONFIG.map(group => `
        <div class="urp-menu">
            <a>${group.name}</a>
            <div class="urp-dropdown">
                ${group.items.map(([label, href]) => `<a href="${href}">${label}</a>`).join('')}
            </div>
        </div>`).join('');

    body.insertBefore(menubar, body.firstChild);
    body.insertBefore(header, body.firstChild);

    // 左侧"我的应用"
    if (urpBody && !urpBody.querySelector('.urp-side')) {
        const side = document.createElement('div');
        side.className = 'urp-side';
        side.innerHTML = `
            <div class="side-box">
                <div class="side-title">我的应用</div>
                <a class="side-link" href="index.html">首页</a>
                <a class="side-link" href="my-schedule.html">我的课表</a>
                <a class="side-link" href="grades.html">成绩查询</a>
                <a class="side-link" href="course-select.html">自主选课</a>
                <a class="side-link" href="evaluate.html">教学评价</a>
            </div>`;
        urpBody.insertBefore(side, urpBody.firstChild);
    }
}

// ---------- 课表渲染 ----------
// 大节定义：1-2节 第1大节，3-4 第2大节，5-6 第3大节，7-8 第4大节，9-10 第5大节
const SECTION_GROUPS = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]];
const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

// ---------- 作息时间 ----------
// 缓存：section -> {start, end}，由后端 /api/common/section-times 提供
let SECTION_TIMES = {};

async function loadSectionTimes() {
    if (Object.keys(SECTION_TIMES).length) return SECTION_TIMES;
    const res = await api('/api/common/section-times');
    if (res && res.success) {
        res.data.forEach(r => { SECTION_TIMES[r.section] = { start: r.start_time, end: r.end_time }; });
    }
    return SECTION_TIMES;
}

// 单节时间文本，如 08:00-08:50
function sectionTimeText(sec) {
    const t = SECTION_TIMES[sec];
    return t ? `${t.start}-${t.end}` : '';
}

// 区间时间文本：从 startSec 开始 → endSec 结束，如 08:00-09:50
function sectionRangeText(startSec, endSec) {
    const a = SECTION_TIMES[startSec];
    const b = SECTION_TIMES[endSec] || a;
    return a && b ? `${a.start}-${b.end}` : '';
}

function renderScheduleTable(container, data) {
    // data: [{weekday, start_section, end_section, course_name, teacher_name, building, room, weeks}]
    const grid = {};
    (data || []).forEach(item => {
        const key = `${item.weekday}-${item.start_section}`;
        if (!grid[key]) grid[key] = [];
        grid[key].push(item);
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
            if (items.length === 0) {
                html += '<td></td>';
            } else {
                html += '<td>' + items.map(it => {
                    const wt = it.week_type && it.week_type !== '全周'
                        ? ` <span class="tag ${it.week_type === '单周' ? 'tag-warning' : 'tag-primary'}">${esc(it.week_type)}</span>`
                        : '';
                    const t = sectionRangeText(it.start_section, it.end_section);
                    return `
                    <div class="schedule-cell">
                        <div class="sc-name">${esc(it.course_name)}${wt}</div>
                        ${t ? `<div class="sc-info" style="color:#1f6feb;font-weight:600;">${t}</div>` : ''}
                        <div class="sc-info">${esc(it.teacher_name || '-')} · ${esc(it.weeks || '')}周</div>
                        <div class="sc-info">${it.building ? esc(it.building + ' ' + (it.room || '')) : ''}</div>
                    </div>`;
                }).join('') + '</td>';
            }
        }
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

// ---------- 学期下拉 ----------
async function fillSemesterSelect(selectEl, includeCurrent = true) {
    const meta = await api('/api/common/meta');
    if (!meta || !meta.success) return;
    selectEl.innerHTML = meta.data.semesters.map(s =>
        `<option value="${esc(s)}" ${s === meta.data.current_semester ? 'selected' : ''}>${esc(s)}</option>`).join('');
}

// ---------- 头像上传（各角色只能改自己的头像） ----------
// 头像单击延迟绑定：单击 250ms 后打开上传；双击则取消单击，交给 ondblclick 放大
// （否则 click 会抢先弹出上传框，导致双击无法放大）
function bindAvatarClick(el) {
    if (!el) return;
    el.style.cursor = 'pointer';
    let timer = null;
    el.onclick = () => {
        if (timer) {
            clearTimeout(timer);
            timer = null;
            return;
        }
        timer = setTimeout(() => {
            timer = null;
            openAvatarUpload();
        }, 250);
    };
}

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
    const previewText = document.getElementById('avPreviewText');
    fileInput.addEventListener('change', () => {
        const f = fileInput.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = e => {
            preview.innerHTML = `<img src="${e.target.result}" alt="预览" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
        };
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
