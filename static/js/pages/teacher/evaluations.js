(async function () {
        if (!await initTeacherPage()) return;
        const res = await api('/api/teacher/evaluations');
        if (!res || !res.success) return;
        document.getElementById('summaryBody').innerHTML = res.summary.length ? res.summary.map(s => `
            <tr><td>${esc(s.course_name)}</td><td>${esc(s.semester)}</td>
            <td>${s.type === 'final' ? '学生评价' : '过程评价'}</td>
            <td>${s.eval_count}</td><td><strong>${Math.round(s.avg_score * 10) / 10}</strong></td></tr>`).join('')
            : '<tr><td colspan="5" class="text-center" style="color:#999">暂无评教数据</td></tr>';
        document.getElementById('commentBox').innerHTML = res.comments.length ? res.comments.map(c => `
            <div class="announcement-item">
                <div class="announcement-title">${esc(c.course_name)} <span class="tag tag-primary">${c.total_score}分</span></div>
                <div style="color:#555;font-size:13px;margin-top:4px;">${esc(c.comment)}</div>
                <div class="announcement-meta" style="margin-top:4px;">${esc(c.created_at)}</div>
            </div>`).join('') : '<div class="empty-state">暂无学生评语</div>';
    })();