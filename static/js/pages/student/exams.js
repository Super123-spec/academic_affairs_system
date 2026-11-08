(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/exams');
        const tbody = document.getElementById('examBody');
        if (!res || !res.success) return;
        if (!res.data.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color:#999">暂无考试安排</td></tr>';
            return;
        }
        tbody.innerHTML = res.data.map(e => `
            <tr>
                <td>${esc(e.course_name)}</td>
                <td><span class="tag tag-primary">${esc(e.exam_type)}</span></td>
                <td>${esc(e.exam_date)}</td>
                <td>${esc(e.start_time || '')} - ${esc(e.end_time || '')}</td>
                <td>${e.building ? esc(e.building + ' ' + e.room) : '-'}</td>
                <td>${esc(e.semester)}</td>
            </tr>`).join('');
    })();