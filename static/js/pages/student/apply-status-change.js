function statusTag(s) {
        return s === '已通过' ? '<span class="tag tag-success">已通过</span>'
            : s === '已拒绝' ? '<span class="tag tag-danger">已拒绝</span>'
            : '<span class="tag tag-warning">待审核</span>';
    }
    async function loadRecords() {
        const res = await api('/api/student/applies');
        const tbody = document.getElementById('recordBody');
        if (!res || !res.success) return;
        const list = res.data.status_changes;
        tbody.innerHTML = list.length ? list.map(a => `
            <tr><td>${esc(a.change_type)}</td><td>${esc(a.reason)}</td><td>${esc(a.apply_date)}</td>
            <td>${statusTag(a.status)}</td><td>${esc(a.review_remark || '-')}</td></tr>`).join('')
            : '<tr><td colspan="5" class="text-center" style="color:#999">暂无申请记录</td></tr>';
    }
    (async function () {
        await initLayout('报名申请');
        loadRecords();
        document.getElementById('applyForm').addEventListener('submit', async e => {
            e.preventDefault();
            const res = await api('/api/student/apply/status-change', {
                method: 'POST',
                body: JSON.stringify({
                    change_type: document.getElementById('changeType').value,
                    reason: document.getElementById('reason').value.trim()
                })
            });
            if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { e.target.reset(); loadRecords(); } }
        });
    })();