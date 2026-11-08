async function loadList() {
        const res = await api('/api/admin/exams');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(e => `
            <tr>
                <td>${esc(e.course_name)}</td><td>${esc(e.semester)}</td>
                <td><span class="tag tag-primary">${esc(e.exam_type)}</span></td>
                <td>${esc(e.exam_date)}</td><td>${esc(e.start_time || '')} - ${esc(e.end_time || '')}</td>
                <td>${e.building ? esc(e.building + ' ' + e.room) : '待定'}</td>
                <td><button class="btn btn-sm btn-danger" data-action="delExam" data-arg='[${e.id}]'>删除</button></td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center" style="color:#999">暂无考试安排</td></tr>';
    }
    async function saveExam() {
        const body = {
            offering_id: parseInt(document.getElementById('f_offeringId').value),
            exam_date: document.getElementById('f_date').value,
            start_time: document.getElementById('f_start').value,
            end_time: document.getElementById('f_end').value,
            classroom_id: parseInt(document.getElementById('f_classroomId').value) || null,
            exam_type: document.getElementById('f_type').value
        };
        if (!body.offering_id || !body.exam_date) { toast('请选择开课并填写考试日期', 'error'); return; }
        const res = await api('/api/admin/exams', { method: 'POST', body: JSON.stringify(body) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }
    async function delExam(id) {
        if (!(await confirmDialog('确定删除该考试安排？'))) return;
        const r = await api('/api/admin/exams/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }
    (async function () {
        if (!await initAdminPage()) return;
        const [offerings, rooms] = await Promise.all([api('/api/admin/offerings'), api('/api/admin/classrooms')]);
        if (offerings && offerings.success) {
            document.getElementById('f_offeringId').innerHTML =
                offerings.data.map(o => `<option value="${o.id}">${esc(o.course_name)}（${esc(o.semester)}）</option>`).join('');
        }
        if (rooms && rooms.success) {
            document.getElementById('f_classroomId').innerHTML = '<option value="">待定</option>' +
                rooms.data.map(r => `<option value="${r.id}">${esc(r.building)} ${esc(r.room)}</option>`).join('');
        }
        loadList();
    })();