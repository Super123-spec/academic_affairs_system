async function loadGrades() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/student/grades?semester=' + encodeURIComponent(semester));
        const tbody = document.getElementById('gradeBody');
        if (!res || !res.success) return;
        if (!res.data.length) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center" style="color:#999">该学期暂无成绩记录</td></tr>';
            return;
        }
        tbody.innerHTML = res.data.map(g => `
            <tr>
                <td>${esc(g.code)}</td><td>${esc(g.course_name)}</td><td>${g.credit}</td><td>${esc(g.type)}</td>
                <td>${esc(g.semester)}</td>
                <td>${g.usual_score ?? '-'}</td><td>${g.exam_score ?? '-'}</td>
                <td>${g.total_score === null ? '<span style="color:#999">未出分</span>'
                    : `<strong style="color:${g.total_score < 60 ? '#cf1322' : '#1f2937'}">${g.total_score}</strong>`}</td>
                <td>${g.grade_point ?? '-'}</td>
                <td>${g.is_retake ? '<span class="tag tag-warning">重修</span>' : ''}</td>
            </tr>`).join('');
    }
    (async function () {
        await initLayout('信息查询');
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadGrades();
    })();