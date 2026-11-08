async function loadList(page = 1) {
        const kw = document.getElementById('keyword').value.trim();
        const res = await api('/api/admin/teachers?keyword=' + encodeURIComponent(kw) + '&page=' + page + '&page_size=20');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(t => `
            <tr>
                <td>${t.avatar
                    ? `<img src="${esc(t.avatar)}" alt="头像" title="双击放大" style="width:36px;height:36px;object-fit:cover;border-radius:50%;display:block;cursor:zoom-in;" data-dbl="viewAvatar">`
                    : `<div style="width:36px;height:36px;border-radius:50%;background:#e5e7eb;display:flex;align-items:center;justify-content:center;font-size:13px;color:#888;">${esc((t.real_name || '').slice(-2))}</div>`}</td>
                <td>${esc(t.username)}</td><td>${esc(t.real_name)}</td><td>${esc(t.gender)}</td>
                <td>${esc(t.college_name || '-')}</td><td>${esc(t.title || '-')}</td><td>${esc(t.phone || '-')}</td>
                <td>${t.is_active ? '<span class="tag tag-success">在职</span>' : '<span class="tag tag-danger">停用</span>'}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(t)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delTeacher" data-arg='[${t.id}, ${jsAttr(t.real_name)}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="9" class="text-center" style="color:#999">暂无教师</td></tr>';
        renderPager('pager', res.total || 0, res.page || 1, res.page_size || 20, 'loadList');
    }

    function openEdit(t) {
        const isEdit = !!t;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑教师' : '新增教师';
        document.getElementById('editId').value = isEdit ? t.id : '';
        document.getElementById('f_username').value = isEdit ? t.username : '';
        document.getElementById('f_username').disabled = isEdit;
        document.getElementById('f_realName').value = isEdit ? t.real_name : '';
        document.getElementById('f_gender').value = isEdit ? t.gender : '男';
        document.getElementById('f_collegeId').value = isEdit ? (t.college_id || '') : '';
        document.getElementById('f_title').value = isEdit ? (t.title || '讲师') : '讲师';
        document.getElementById('f_phone').value = isEdit ? (t.phone || '') : '';
        document.getElementById('f_email').value = isEdit ? (t.email || '') : '';
        document.getElementById('f_active').value = isEdit ? String(t.is_active) : '1';
        // 初始密码仅新增时展示；每次打开都把"重置密码"复选框取消勾选
        document.getElementById('pwRow').style.display = isEdit ? 'none' : 'flex';
        document.getElementById('f_password').value = '123456';
        document.getElementById('resetPwRow').style.display = isEdit ? 'block' : 'none';
        document.getElementById('f_resetPw').checked = false;
        openModal('editModal');
    }

    async function saveTeacher() {
        const id = document.getElementById('editId').value;
        const body = {
            real_name: document.getElementById('f_realName').value.trim(),
            gender: document.getElementById('f_gender').value,
            college_id: parseInt(document.getElementById('f_collegeId').value) || null,
            title: document.getElementById('f_title').value,
            phone: document.getElementById('f_phone').value.trim(),
            email: document.getElementById('f_email').value.trim(),
        };
        if (!body.real_name) { toast('请填写姓名', 'error'); return; }
        let res;
        if (id) {
            res = await api('/api/admin/teachers/' + id, { method: 'PUT', body: JSON.stringify({
                ...body, is_active: parseInt(document.getElementById('f_active').value),
                reset_password: document.getElementById('f_resetPw').checked
            })});
        } else {
            body.username = document.getElementById('f_username').value.trim();
            if (!body.username) { toast('请填写工号', 'error'); return; }
            // 初始密码默认 123456，管理员可自定义
            body.password = document.getElementById('f_password').value.trim() || '123456';
            res = await api('/api/admin/teachers', { method: 'POST', body: JSON.stringify(body) });
        }
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }

    async function delTeacher(id, name) {
        if (!(await confirmDialog(`确定删除教师「${name}」？`))) return;
        const r = await api('/api/admin/teachers/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const meta = await loadMeta();
        document.getElementById('f_collegeId').innerHTML = '<option value="">请选择</option>' +
            meta.colleges.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        loadList();
    })();