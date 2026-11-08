async function loadList() {
        const kw = document.getElementById('keyword').value.trim();
        const res = await api('/api/admin/grades?keyword=' + encodeURIComponent(kw));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(g => `
            <tr>
                <td>${esc(g.username)}</td><td>${esc(g.student_name)}</td><td>${esc(g.course_name)}</td><td>${esc(g.semester)}</td>
                <td>${g.usual_score ?? '-'}</td><td>${g.exam_score ?? '-'}</td>
                <td>${g.total_score === null ? '-' : `<strong style="color:${g.total_score < 60 ? '#cf1322' : 'inherit'}">${g.total_score}</strong>`}</td>
                <td>${g.grade_point ?? '-'}</td>
                <td><button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(g)}'>修改</button></td>
            </tr>`).join('') : '<tr><td colspan="9" class="text-center" style="color:#999">暂无成绩记录</td></tr>';
    }
    function openEdit(g) {
        document.getElementById('editId').value = g.id;
        document.getElementById('editInfo').textContent = `${g.student_name}（${g.username}） - ${g.course_name}（${g.semester}）`;
        document.getElementById('f_usual').value = g.usual_score ?? '';
        document.getElementById('f_exam').value = g.exam_score ?? '';
        const u = g.usual_ratio ?? 40, e = g.exam_ratio ?? 60;
        document.getElementById('ratioInfo').innerHTML =
            `总评 = 平时 × <strong style="color:#1f6feb">${u}%</strong> + 考试 × <strong style="color:#1f6feb">${e}%</strong>，自动计算。`;
        openModal('editModal');
    }
    async function saveGrade() {
        const id = document.getElementById('editId').value;
        const uv = document.getElementById('f_usual').value;
        const ev = document.getElementById('f_exam').value;
        const res = await api('/api/admin/grades', { method: 'PUT', body: JSON.stringify({
            id: parseInt(id),
            usual_score: uv === '' ? null : parseFloat(uv),
            exam_score: ev === '' ? null : parseFloat(ev)
        })});
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }
    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();