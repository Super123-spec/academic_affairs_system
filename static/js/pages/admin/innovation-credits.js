let records = [];
    let studentOptions = [];

    async function loadStudents() {
        const res = await api('/api/admin/students?page_size=100');
        if (res && res.success) {
            studentOptions = res.data.map(s => ({
                value: s.id, label: `${s.username} ${s.real_name}${s.class_name ? '（' + s.class_name + '）' : ''}`
            }));
        }
    }

    async function loadList() {
        const kw = document.getElementById('keyword').value.trim();
        const res = await api('/api/admin/innovation-credits?keyword=' + encodeURIComponent(kw));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        records = res.data || [];
        tbody.innerHTML = records.length ? records.map(r => `
            <tr>
                <td>${esc(r.username)}</td><td>${esc(r.real_name)}</td><td>${esc(r.class_name || '-')}</td>
                <td>${esc(r.item_name)}</td>
                <td><span class="tag tag-primary">${esc(r.category)}</span></td>
                <td><strong>${r.credit}</strong></td>
                <td>${esc(r.obtained_date || '-')}</td>
                <td>${r.is_confirmed ? '<span class="tag tag-success">已确认</span>' : '<span class="tag tag-warning">待确认</span>'}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(r)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delItem" data-arg='[${r.id}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="9" class="text-center" style="color:#999">暂无创新学分记录</td></tr>';
    }

    async function openEdit(r) {
        const isEdit = !!r;
        if (!studentOptions.length) await loadStudents();
        const d = await formDialog(isEdit ? '编辑创新学分' : '录入创新学分', [
            { key: 'student_id', label: '学生', type: 'select', required: true,
              value: isEdit ? r.student_id : '',
              options: studentOptions },
            { key: 'item_name', label: '项目名称', required: true, value: isEdit ? r.item_name : '' },
            { key: 'category', label: '类别', type: 'select', value: isEdit ? r.category : '竞赛获奖',
              options: ['竞赛获奖', '科研论文', '专利', '创新创业训练', '社会实践', '技能证书'].map(c => ({ value: c, label: c })) },
            { key: 'credit', label: '学分', type: 'number', value: isEdit ? r.credit : 1 },
            { key: 'obtained_date', label: '获得日期', type: 'date', value: isEdit ? (r.obtained_date || '') : '' },
            { key: 'is_confirmed', label: '确认状态', type: 'select', value: isEdit ? String(r.is_confirmed) : '0',
              options: [{ value: '0', label: '待确认' }, { value: '1', label: '已确认' }] },
        ]);
        if (!d.ok) return;
        const body = {
            student_id: parseInt(d.values.student_id), item_name: d.values.item_name,
            category: d.values.category, credit: parseFloat(d.values.credit) || 0,
            obtained_date: d.values.obtained_date || null,
            is_confirmed: parseInt(d.values.is_confirmed),
        };
        const r2 = await api(isEdit ? '/api/admin/innovation-credits/' + r.id : '/api/admin/innovation-credits',
            { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (r2) { toast(r2.message, r2.success ? 'success' : 'error'); if (r2.success) loadList(); }
    }

    async function delItem(id) {
        if (!(await confirmDialog('确定删除该创新学分记录？'))) return;
        const r = await api('/api/admin/innovation-credits/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        await loadStudents();
        loadList();
    })();