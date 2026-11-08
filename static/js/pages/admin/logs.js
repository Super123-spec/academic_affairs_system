async function loadList() {
        const res = await api('/api/admin/logs');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(l => `
            <tr>
                <td>${esc(l.created_at)}</td><td>${esc(l.admin_name || '系统')}</td>
                <td><span class="tag tag-primary">${esc(l.action)}</span></td>
                <td>${l.target_table ? esc(l.target_table + '#' + (l.target_id || '')) : '-'}</td>
                <td style="font-size:12.5px;color:#555;">${esc(l.detail || '-')}</td>
                <td>${esc(l.ip_address || '-')}</td>
                <td><button class="btn btn-sm btn-danger" data-action="delLog" data-arg='[${l.id}]'>删除</button></td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center" style="color:#999">暂无日志</td></tr>';
    }

    async function delLog(id) {
        if (!(await confirmDialog('确定删除这条日志？'))) return;
        const r = await api('/api/admin/logs/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    async function clearLogs() {
        if (!(await confirmDialog('确定清空全部操作日志？此操作不可恢复。'))) return;
        const r = await api('/api/admin/logs', { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();