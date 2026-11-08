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
            document.getElementById('courseSel').innerHTML = '<option value="">请选择</option>' +
                courses.data.map(c => `<option value="${c.id}">${esc(c.code)} ${esc(c.name)}（${c.credit}学分）</option>`).join('');
        }
        if (applies && applies.success) {
            const list = applies.data.substitutes;
            document.getElementById('recordBody').innerHTML = list.length ? list.map(a => `
                <tr><td>${esc(a.external_course)}（${esc(a.external_school)}）</td>
                <td>${esc(a.substitute_course_name || '-')}</td><td>${a.external_credit ?? '-'}</td>
                <td>${statusTag(a.status)}</td><td>${esc(a.review_remark || '-')}</td><td>${esc(a.created_at)}</td></tr>`).join('')
                : '<tr><td colspan="6" class="text-center" style="color:#999">暂无申请记录</td></tr>';
        }
    }
    (async function () {
        await initLayout('报名申请');
        loadData();
        document.getElementById('applyForm').addEventListener('submit', async e => {
            e.preventDefault();
            const res = await api('/api/student/apply/credit-substitute', {
                method: 'POST',
                body: JSON.stringify({
                    external_school: document.getElementById('extSchool').value.trim(),
                    external_course: document.getElementById('extCourse').value.trim(),
                    external_credit: parseFloat(document.getElementById('extCredit').value) || null,
                    substitute_course_id: parseInt(document.getElementById('courseSel').value) || null,
                    reason: document.getElementById('reason').value.trim()
                })
            });
            if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { e.target.reset(); loadData(); } }
        });
    })();