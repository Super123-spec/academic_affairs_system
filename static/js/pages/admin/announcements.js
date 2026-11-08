async function loadList() {
        const res = await api('/api/admin/announcements');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(a => `
            <tr>
                <td><strong>${esc(a.title)}</strong></td>
                <td>${a.is_top ? '<span class="tag tag-danger">置顶</span>' : '-'}</td>
                <td>${a.is_active ? '<span class="tag tag-success">已发布</span>' : '<span class="tag tag-warning">已下线</span>'}</td>
                <td>${esc(a.created_at)}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(a)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delAnn" data-arg='[${a.id}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="5" class="text-center" style="color:#999">暂无公告</td></tr>';
    }
    function openEdit(a) {
        const isEdit = !!a;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑公告' : '发布公告';
        document.getElementById('editId').value = isEdit ? a.id : '';
        document.getElementById('f_title').value = isEdit ? a.title : '';
        document.getElementById('f_content').value = isEdit ? a.content : '';
        document.getElementById('f_top').value = isEdit ? String(a.is_top) : '0';
        document.getElementById('activeRow').style.display = isEdit ? 'block' : 'none';
        if (isEdit) document.getElementById('f_active').value = String(a.is_active);
        openModal('editModal');
    }
    async function saveAnn() {
        const id = document.getElementById('editId').value;
        const body = {
            title: document.getElementById('f_title').value.trim(),
            content: document.getElementById('f_content').value.trim(),
            is_top: parseInt(document.getElementById('f_top').value)
        };
        if (!body.title || !body.content) { toast('请填写标题和内容', 'error'); return; }
        let res;
        if (id) {
            res = await api('/api/admin/announcements/' + id, { method: 'PUT',
                body: JSON.stringify({ ...body, is_active: parseInt(document.getElementById('f_active').value) }) });
        } else {
            res = await api('/api/admin/announcements', { method: 'POST', body: JSON.stringify(body) });
        }
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }
    async function delAnn(id) {
        if (!(await confirmDialog('确定删除该公告？'))) return;
        const r = await api('/api/admin/announcements/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }
    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();