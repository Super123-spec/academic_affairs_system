async function loadList() {
        const oid = document.getElementById('offeringFilter').value;
        const res = await api('/api/admin/enrollments' + (oid ? '?offering_id=' + oid : ''));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(e => `
            <tr>
                <td>${esc(e.username)}</td><td>${esc(e.student_name)}</td><td>${esc(e.course_name)}</td>
                <td>${esc(e.semester)}</td><td>${esc(e.select_time)}</td>
                <td>${e.status === '已选' ? '<span class="tag tag-success">已选</span>' : '<span class="tag tag-danger">退选</span>'}</td>
                <td>${e.total_score ?? '-'}</td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center" style="color:#999">暂无选课记录</td></tr>';
    }

    // 重算各教学班已选人数（修复与选课记录不一致）
    async function repairCount() {
        if (!(await confirmDialog('将按实际选课记录重算所有教学班的「已选人数」，确定继续？'))) return;
        const r = await api('/api/admin/repair/selected-count', { method: 'POST' });
        if (r) {
            toast(r.message, r.success ? 'success' : 'error');
            if (r.success && r.details && r.details.length) {
                console.log('修正明细:', r.details);
            }
        }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const offerings = await api('/api/admin/offerings');
        if (offerings && offerings.success) {
            document.getElementById('offeringFilter').innerHTML = '<option value="">全部开课</option>' +
                offerings.data.map(o => `<option value="${o.id}">${esc(o.course_name)}（${esc(o.semester)}）</option>`).join('');
        }
        loadList();
    })();