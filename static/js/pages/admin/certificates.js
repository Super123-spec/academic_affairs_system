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
        const res = await api('/api/admin/certificates?keyword=' + encodeURIComponent(kw));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        records = res.data || [];
        tbody.innerHTML = records.length ? records.map(c => `
            <tr>
                <td>${esc(c.username)}</td><td>${esc(c.real_name)}</td><td>${esc(c.class_name || '-')}</td>
                <td><strong>${esc(c.name)}</strong></td>
                <td style="font-family:monospace;">${esc(c.cert_no || '-')}</td>
                <td>${esc(c.issue_date || '-')}</td>
                <td>${esc(c.issuer || '-')}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(c)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delItem" data-arg='[${c.id}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="8" class="text-center" style="color:#999">暂无证书记录</td></tr>';
    }

    // 自动生成证书编号：年份 + 4位随机
    function genCertNo() {
        const y = new Date().getFullYear();
        const r = String(Math.floor(Math.random() * 9000) + 1000);
        return `CERT${y}${r}`;
    }

    async function openEdit(c) {
        const isEdit = !!c;
        if (!studentOptions.length) await loadStudents();
        const today = new Date().toISOString().slice(0, 10);
        const d = await formDialog(isEdit ? '编辑证书' : '发放证书', [
            { key: 'student_id', label: '学生', type: 'select', required: !isEdit,
              value: isEdit ? c.student_id : '', options: studentOptions },
            { key: 'name', label: '证书名称', required: true, value: isEdit ? c.name : '' },
            { key: 'cert_no', label: '证书编号', value: isEdit ? (c.cert_no || '') : genCertNo() },
            { key: 'issue_date', label: '发证日期', type: 'date', value: isEdit ? (c.issue_date || '') : today },
            { key: 'issuer', label: '发证单位', value: isEdit ? (c.issuer || '') : '贵阳信息科技学院' },
        ]);
        if (!d.ok) return;
        const body = {
            name: d.values.name, cert_no: d.values.cert_no,
            issue_date: d.values.issue_date || null, issuer: d.values.issuer,
        };
        if (!isEdit) body.student_id = parseInt(d.values.student_id);
        const r = await api(isEdit ? '/api/admin/certificates/' + c.id : '/api/admin/certificates',
            { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
    }

    async function delItem(id) {
        if (!(await confirmDialog('确定删除该证书？'))) return;
        const r = await api('/api/admin/certificates/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        await loadStudents();
        loadList();
    })();