let curPage = 1;

    async function loadList(page = 1) {
        curPage = page;
        const kw = document.getElementById('keyword').value.trim();
        const cid = document.getElementById('classSel').value;
        let url = '/api/admin/students?keyword=' + encodeURIComponent(kw) + '&page=' + page + '&page_size=20';
        if (cid) url += '&class_id=' + cid;
        const res = await api(url);
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(s => `
            <tr>
                <td>${s.avatar
                    ? `<img src="${esc(s.avatar)}" alt="头像" title="双击放大" style="width:36px;height:36px;object-fit:cover;border-radius:50%;display:block;cursor:zoom-in;" data-dbl="viewAvatar">`
                    : `<div style="width:36px;height:36px;border-radius:50%;background:#e5e7eb;display:flex;align-items:center;justify-content:center;font-size:13px;color:#888;">${esc((s.real_name || '').slice(-2))}</div>`}</td>
                <td>${esc(s.username)}</td><td>${esc(s.real_name)}</td><td>${esc(s.gender)}</td>
                <td>${esc(s.class_name || '-')}</td><td>${esc(s.major_name || '-')}</td>
                <td><span class="tag ${s.status === '在读' ? 'tag-success' : 'tag-warning'}">${esc(s.status)}</span></td>
                <td>${s.is_frozen ? '<span class="tag tag-danger">冻结</span>' : '<span class="tag tag-primary">正常</span>'}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(s)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delStudent" data-arg='[${s.id}, ${jsAttr(s.real_name)}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="9" class="text-center" style="color:#999">暂无学生</td></tr>';
        renderPager('pager', res.total || 0, res.page || 1, res.page_size || 20, 'loadList');
    }

    function openEdit(s) {
        const isEdit = !!s;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑学生' : '新增学生';
        document.getElementById('editId').value = isEdit ? s.id : '';
        document.getElementById('f_username').value = isEdit ? s.username : '';
        document.getElementById('f_username').disabled = isEdit;
        document.getElementById('f_realName').value = isEdit ? s.real_name : '';
        document.getElementById('f_gender').value = isEdit ? s.gender : '男';
        document.getElementById('f_classId').value = isEdit ? (s.class_id || '') : '';
        document.getElementById('f_phone').value = isEdit ? (s.phone || '') : '';
        document.getElementById('f_email').value = isEdit ? (s.email || '') : '';
        document.getElementById('f_status').value = isEdit ? s.status : '在读';
        document.getElementById('f_frozen').value = isEdit ? String(s.is_frozen) : '0';
        // 初始密码仅新增时展示；每次打开都把"重置密码"复选框取消勾选
        document.getElementById('pwRow').style.display = isEdit ? 'none' : 'flex';
        document.getElementById('f_password').value = '123456';
        document.getElementById('resetPwRow').style.display = isEdit ? 'block' : 'none';
        document.getElementById('f_resetPw').checked = false;
        openModal('editModal');
    }

    async function saveStudent() {
        const id = document.getElementById('editId').value;
        const body = {
            real_name: document.getElementById('f_realName').value.trim(),
            gender: document.getElementById('f_gender').value,
            class_id: parseInt(document.getElementById('f_classId').value) || null,
            phone: document.getElementById('f_phone').value.trim(),
            email: document.getElementById('f_email').value.trim(),
            status: document.getElementById('f_status').value,
        };
        if (!body.real_name) { toast('请填写姓名', 'error'); return; }
        let res;
        if (id) {
            res = await api('/api/admin/students/' + id, { method: 'PUT', body: JSON.stringify({
                ...body, is_frozen: parseInt(document.getElementById('f_frozen').value),
                reset_password: document.getElementById('f_resetPw').checked
            })});
        } else {
            body.username = document.getElementById('f_username').value.trim();
            if (!body.username) { toast('请填写学号', 'error'); return; }
            // 初始密码默认 123456，管理员可自定义；后端返回的 message 会带上初始密码与自动继承课程数
            body.password = document.getElementById('f_password').value.trim() || '123456';
            res = await api('/api/admin/students', { method: 'POST', body: JSON.stringify(body) });
        }
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }

    async function delStudent(id, name) {
        if (!(await confirmDialog(`确定删除学生「${name}」？其选课记录将一并删除。`))) return;
        const r = await api('/api/admin/students/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const meta = await loadMeta();
        const opts = meta.classes.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        document.getElementById('classSel').innerHTML = '<option value="">全部班级</option>' + opts;
        document.getElementById('f_classId').innerHTML = '<option value="">未分配</option>' + opts;
        loadList();
    })();