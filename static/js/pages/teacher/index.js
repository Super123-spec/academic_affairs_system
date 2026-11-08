(async function () {
        if (!await initTeacherPage()) return;
        const d = await api('/api/teacher/dashboard');
        if (d && d.success) {
            document.getElementById('offeringCount').textContent = d.data.offering_count;
            document.getElementById('studentCount').textContent = d.data.student_count;
            document.getElementById('ungradedCount').textContent = d.data.ungraded_count;
            document.getElementById('avgEval').textContent = d.data.avg_evaluation ?? '暂无';
        }
        const ann = await api('/api/common/announcements');
        const box = document.getElementById('announcements');
        if (ann && ann.success && ann.data.length) {
            box.innerHTML = ann.data.slice(0, 5).map(a => `
                <div class="announcement-item">
                    <div class="announcement-title">${a.is_top ? '<span class="tag tag-danger">置顶</span> ' : ''}${esc(a.title)}</div>
                    <div class="announcement-meta">${esc(a.created_at)}</div>
                    <div style="margin-top:6px;color:#555;font-size:13px;">${esc(a.content)}</div>
                </div>`).join('');
        } else {
            box.innerHTML = '<div class="empty-state">暂无公告</div>';
        }
    })();