let projects = [];

    async function loadList() {
        const kw = document.getElementById('keyword').value.trim();
        const res = await api('/api/admin/projects?keyword=' + encodeURIComponent(kw));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        projects = res.data || [];
        tbody.innerHTML = projects.length ? projects.map(p => `
            <tr>
                <td>${esc(p.name)}</td>
                <td><span class="tag tag-primary">${esc(p.type)}</span></td>
                <td>${esc(p.semester || '-')}</td>
                <td>${p.total_apply || 0} / ${p.max_count}</td>
                <td style="font-size:12.5px;color:#666;">${esc(p.start_date || '-')} ~ ${esc(p.end_date || '-')}</td>
                <td>${p.is_open ? '<span class="tag tag-success">报名中</span>' : '<span class="tag tag-danger">已关闭</span>'}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(p)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delItem" data-arg='[${p.id}, ${jsAttr(p.name)}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center" style="color:#999">暂无教学项目</td></tr>';
    }

    async function openEdit(p) {
        const isEdit = !!p;
        const meta = await loadMeta();
        const d = await formDialog(isEdit ? '编辑教学项目' : '新增教学项目', [
            { key: 'name', label: '项目名称', required: true, value: isEdit ? p.name : '' },
            { key: 'type', label: '项目类型', type: 'select', value: isEdit ? p.type : '学科竞赛',
              options: ['学科竞赛', '科研项目', '创新训练', '社会实践', '企业实习'].map(t => ({ value: t, label: t })) },
            { key: 'semester', label: '学期', type: 'select', value: isEdit ? p.semester : meta.current_semester,
              options: meta.semesters.map(s => ({ value: s, label: s })) },
            { key: 'max_count', label: '名额', type: 'number', value: isEdit ? p.max_count : 30 },
            { key: 'start_date', label: '开始日期', type: 'date', value: isEdit ? (p.start_date || '') : '' },
            { key: 'end_date', label: '结束日期', type: 'date', value: isEdit ? (p.end_date || '') : '' },
            { key: 'is_open', label: '开放报名', type: 'select', value: isEdit ? String(p.is_open) : '1',
              options: [{ value: '1', label: '开放' }, { value: '0', label: '关闭' }] },
            { key: 'description', label: '项目说明', value: isEdit ? (p.description || '') : '' },
        ]);
        if (!d.ok) return;
        const body = {
            name: d.values.name, type: d.values.type, semester: d.values.semester,
            max_count: parseInt(d.values.max_count) || 30,
            start_date: d.values.start_date || null, end_date: d.values.end_date || null,
            is_open: parseInt(d.values.is_open), description: d.values.description,
        };
        const r = await api(isEdit ? '/api/admin/projects/' + p.id : '/api/admin/projects',
            { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
    }

    async function delItem(id, name) {
        if (!(await confirmDialog(`确定删除项目「${name}」？相关报名记录将一并删除。`))) return;
        const r = await api('/api/admin/projects/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();