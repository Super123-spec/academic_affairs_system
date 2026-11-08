async function loadList() {
        const res = await api('/api/student/innovation-credits');
        const tbody = document.getElementById('creditBody');
        if (!res || !res.success) return;
        if (!res.data.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color:#999">暂无创新创业学分记录</td></tr>';
            return;
        }
        tbody.innerHTML = res.data.map(c => `
            <tr>
                <td>${esc(c.item_name)}</td><td>${esc(c.category)}</td><td>${c.credit}</td><td>${esc(c.obtained_date || '-')}</td>
                <td>${c.is_confirmed ? '<span class="tag tag-success">已确认</span>' : '<span class="tag tag-warning">待确认</span>'}</td>
                <td>${c.is_confirmed ? '-' : `<button class="btn btn-sm btn-primary" data-action="confirmCredit" data-arg='[${c.id}]'>确认</button>`}</td>
            </tr>`).join('');
    }
    async function confirmCredit(id) {
        const res = await api('/api/student/innovation-credits/confirm', { method: 'POST', body: JSON.stringify({ id }) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadList(); }
    }
    (async function () {
        await initLayout('信息维护');
        loadList();
    })();