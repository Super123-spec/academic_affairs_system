(async function () {
        if (!await initAdminPage()) return;
        const d = await api('/api/admin/dashboard');
        if (d && d.success) {
            document.getElementById('studentCount').textContent = d.data.student_count;
            document.getElementById('teacherCount').textContent = d.data.teacher_count;
            document.getElementById('courseCount').textContent = d.data.course_count;
            document.getElementById('offeringCount').textContent = d.data.offering_count;
            document.getElementById('pendingCount').textContent = d.data.pending_applies;
        }
        const ann = await api('/api/common/announcements');
        const box = document.getElementById('announcements');
        if (ann && ann.success && ann.data.length) {
            box.innerHTML = ann.data.slice(0, 5).map(a => `
                <div class="announcement-item">
                    <div class="announcement-title">${a.is_top ? '<span class="tag tag-danger">置顶</span> ' : ''}${esc(a.title)}</div>
                    <div class="announcement-meta">${esc(a.created_at)}</div>
                </div>`).join('');
        } else {
            box.innerHTML = '<div class="empty-state">暂无公告</div>';
        }
    })();