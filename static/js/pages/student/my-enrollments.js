async function loadList() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/student/enrollments?semester=' + encodeURIComponent(semester));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        if (!res.data.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="color:#999">该学期暂无选课记录</td></tr>';
            return;
        }
        tbody.innerHTML = res.data.map(e => `
            <tr>
                <td>${esc(e.code)}</td><td>${esc(e.course_name)}</td><td>${e.credit}</td><td>${esc(e.type)}</td>
                <td>${esc(e.teacher_name || '-')}</td><td>${esc(e.select_time)}</td>
                <td>${e.status === '已选' ? '<span class="tag tag-success">已选</span>' : '<span class="tag tag-danger">退选</span>'}</td>
                <td>${e.is_retake ? '<span class="tag tag-warning">重修</span>' : ''}</td>
            </tr>`).join('');
    }
    (async function () {
        await initLayout('信息查询');
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadList();
    })();