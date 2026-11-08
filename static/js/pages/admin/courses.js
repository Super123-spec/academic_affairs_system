async function loadList(page = 1) {
        const kw = document.getElementById('keyword').value.trim();
        const res = await api('/api/admin/courses?keyword=' + encodeURIComponent(kw) + '&page=' + page + '&page_size=20');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(c => `
            <tr>
                <td>${esc(c.code)}</td><td>${esc(c.name)}</td><td>${c.credit}</td><td>${c.hours}</td>
                <td><span class="tag tag-primary">${esc(c.type)}</span></td><td>${esc(c.college_name || '-')}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(c)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delCourse" data-arg='[${c.id}, ${jsAttr(c.name)}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center" style="color:#999">暂无课程</td></tr>';
        renderPager('pager', res.total || 0, res.page || 1, res.page_size || 20, 'loadList');
    }

    function openEdit(c) {
        const isEdit = !!c;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑课程' : '新增课程';
        document.getElementById('editId').value = isEdit ? c.id : '';
        document.getElementById('f_code').value = isEdit ? c.code : '';
        document.getElementById('f_name').value = isEdit ? c.name : '';
        document.getElementById('f_credit').value = isEdit ? c.credit : '';
        document.getElementById('f_hours').value = isEdit ? c.hours : '';
        document.getElementById('f_type').value = isEdit ? c.type : '必修';
        document.getElementById('f_collegeId').value = isEdit ? (c.college_id || '') : '';
        document.getElementById('f_desc').value = isEdit ? (c.description || '') : '';
        openModal('editModal');
    }

    async function saveCourse() {
        const id = document.getElementById('editId').value;
        const body = {
            code: document.getElementById('f_code').value.trim(),
            name: document.getElementById('f_name').value.trim(),
            credit: parseFloat(document.getElementById('f_credit').value) || 0,
            hours: parseInt(document.getElementById('f_hours').value) || 0,
            type: document.getElementById('f_type').value,
            college_id: parseInt(document.getElementById('f_collegeId').value) || null,
            description: document.getElementById('f_desc').value.trim()
        };
        if (!body.code || !body.name) { toast('请填写课程号和名称', 'error'); return; }
        const res = await api(id ? '/api/admin/courses/' + id : '/api/admin/courses',
            { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }

    async function delCourse(id, name) {
        if (!(await confirmDialog(`确定删除课程「${name}」？相关开课将一并删除。`))) return;
        const r = await api('/api/admin/courses/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const meta = await loadMeta();
        document.getElementById('f_collegeId').innerHTML = '<option value="">请选择</option>' +
            meta.colleges.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        loadList();
    })();