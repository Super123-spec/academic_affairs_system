async function loadOfferings() {
        const res = await api('/api/teacher/offerings');
        if (!res || !res.success) return;
        document.getElementById('offeringSel').innerHTML = res.data.length
            ? res.data.map(o => `<option value="${o.id}">${esc(o.course_name)}（${esc(o.semester)}）</option>`).join('')
            : '<option value="">本学期暂无开课</option>';
    }
    async function loadStudents() {
        const oid = document.getElementById('offeringSel').value;
        if (!oid) return;
        const res = await api(`/api/teacher/offering/${oid}/students`);
        const tbody = document.getElementById('stuBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(s => `
            <tr><td>${esc(s.username)}</td><td>${esc(s.real_name)}</td><td>${esc(s.gender)}</td>
            <td>${esc(s.class_name || '-')}</td><td>${esc(s.select_time)}</td></tr>`).join('')
            : '<tr><td colspan="5" class="text-center" style="color:#999">该课程暂无选课学生</td></tr>';
    }

    // 导出选课名单（Excel）
    function exportStudents() {
        const oid = document.getElementById('offeringSel').value;
        if (!oid) { toast('请先选择课程', 'error'); return; }
        window.location.href = `/api/teacher/offering/${oid}/students/export`;
    }
    (async function () {
        if (!await initTeacherPage()) return;
        await loadOfferings();
        loadStudents();
    })();