function statusTag(s) {
        return s === '已通过' ? '<span class="tag tag-success">已通过</span>'
            : s === '已拒绝' ? '<span class="tag tag-danger">已拒绝</span>'
            : '<span class="tag tag-warning">待审核</span>';
    }
    async function loadData() {
        const [courses, applies] = await Promise.all([
            api('/api/student/courses'), api('/api/student/applies')
        ]);
        if (courses && courses.success) {
            document.getElementById('courseSel').innerHTML =
                courses.data.map(c => `<option value="${c.id}">${esc(c.code)} ${esc(c.name)}（${c.credit}学分）</option>`).join('');
        }
        if (applies && applies.success) {
            const list = applies.data.retakes;
            document.getElementById('recordBody').innerHTML = list.length ? list.map(a => `
                <tr><td>${esc(a.course_name)}</td><td>${esc(a.semester)}</td><td>${esc(a.reason || '-')}</td>
                <td>${statusTag(a.status)}</td><td>${esc(a.review_remark || '-')}</td><td>${esc(a.created_at)}</td></tr>`).join('')
                : '<tr><td colspan="6" class="text-center" style="color:#999">暂无报名记录</td></tr>';
        }
    }
    (async function () {
        await initLayout('报名申请');
        loadData();
        document.getElementById('applyForm').addEventListener('submit', async e => {
            e.preventDefault();
            const res = await api('/api/student/apply/retake', {
                method: 'POST',
                body: JSON.stringify({
                    course_id: parseInt(document.getElementById('courseSel').value),
                    reason: document.getElementById('reason').value.trim()
                })
            });
            if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { e.target.reset(); loadData(); } }
        });
    })();