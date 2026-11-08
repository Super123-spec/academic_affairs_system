(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/retake-courses');
        if (!res || !res.success) return;
        document.getElementById('failedBody').innerHTML = res.failed.length
            ? res.failed.map(c => `<tr><td>${esc(c.code)}</td><td>${esc(c.name)}</td><td>${c.credit}</td>
                <td>${esc(c.semester)}</td><td><strong style="color:#cf1322">${c.total_score}</strong></td></tr>`).join('')
            : '<tr><td colspan="5" class="text-center" style="color:#389e0d">没有不及格课程，无需重修</td></tr>';
        document.getElementById('availBody').innerHTML = res.available.length
            ? res.available.map(c => `<tr><td>${esc(c.course_name)}</td><td>${c.credit}</td>
                <td>${esc(c.teacher_name || '-')}</td><td>${c.selected_count}/${c.max_count}</td></tr>`).join('')
            : '<tr><td colspan="4" class="text-center" style="color:#999">本学期暂无开放的教学班</td></tr>';
    })();