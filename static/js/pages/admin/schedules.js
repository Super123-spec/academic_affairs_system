const WD = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日'];

    async function loadList() {
        const oid = document.getElementById('offeringFilter').value;
        const res = await api('/api/admin/schedules' + (oid ? '?offering_id=' + oid : ''));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(s => `
            <tr>
                <td>${esc(s.course_name)}</td><td>${esc(s.teacher_name || '待定')}</td>
                <td>${s.class_names ? esc(s.class_names) : '<span style="color:#bbb">-</span>'}</td>
                <td>${esc(s.semester)}</td>
                <td>${WD[s.weekday]}</td><td>${s.start_section}-${s.end_section}节</td><td>${esc(s.weeks)}周</td>
                <td>${s.week_type === '全周' ? '全周' : `<span class="tag ${s.week_type === '单周' ? 'tag-warning' : 'tag-primary'}">${esc(s.week_type)}</span>`}</td>
                <td>${s.building ? esc(s.building + ' ' + s.room) : '待定'}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(s)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delSchedule" data-arg='[${s.id}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="10" class="text-center" style="color:#999">暂无排课</td></tr>';
    }

    function openEdit(s) {
        const isEdit = !!s;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑排课' : '新增排课';
        document.getElementById('editId').value = isEdit ? s.id : '';
        document.getElementById('f_offeringId').value = isEdit ? s.offering_id : '';
        document.getElementById('f_offeringId').disabled = isEdit;
        document.getElementById('f_weekday').value = isEdit ? s.weekday : 1;
        document.getElementById('f_classroomId').value = isEdit ? (s.classroom_id || '') : '';
        document.getElementById('f_start').value = isEdit ? s.start_section : 1;
        document.getElementById('f_end').value = isEdit ? s.end_section : 2;
        document.getElementById('f_weeks').value = isEdit ? s.weeks : '1-16';
        document.getElementById('f_weekType').value = isEdit ? (s.week_type || '全周') : '全周';
        openModal('editModal');
    }

    async function saveSchedule() {
        const id = document.getElementById('editId').value;
        const body = {
            weekday: parseInt(document.getElementById('f_weekday').value),
            start_section: parseInt(document.getElementById('f_start').value),
            end_section: parseInt(document.getElementById('f_end').value),
            weeks: document.getElementById('f_weeks').value.trim() || '1-16',
            week_type: document.getElementById('f_weekType').value,
            classroom_id: parseInt(document.getElementById('f_classroomId').value) || null
        };
        if (body.end_section < body.start_section) { toast('结束节次不能小于开始节次', 'error'); return; }
        let res;
        if (id) {
            res = await api('/api/admin/schedules/' + id, { method: 'PUT', body: JSON.stringify(body) });
        } else {
            body.offering_id = parseInt(document.getElementById('f_offeringId').value);
            if (!body.offering_id) { toast('请选择开课', 'error'); return; }
            res = await api('/api/admin/schedules', { method: 'POST', body: JSON.stringify(body) });
        }
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }

    async function delSchedule(id) {
        if (!(await confirmDialog('确定删除该排课？'))) return;
        const r = await api('/api/admin/schedules/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const [offerings, rooms] = await Promise.all([api('/api/admin/offerings'), api('/api/admin/classrooms')]);
        if (offerings && offerings.success) {
            const opts = offerings.data.map(o => `<option value="${o.id}">${esc(o.course_name)} - ${esc(o.teacher_name || '待定')}${o.class_names ? ' [' + esc(o.class_names) + ']' : ''}（${esc(o.semester)}）</option>`).join('');
            document.getElementById('offeringFilter').innerHTML = '<option value="">全部开课</option>' + opts;
            document.getElementById('f_offeringId').innerHTML = opts;
        }
        if (rooms && rooms.success) {
            document.getElementById('f_classroomId').innerHTML = '<option value="">待定</option>' +
                rooms.data.map(r => `<option value="${r.id}">${esc(r.building)} ${esc(r.room)}（${r.capacity}人）</option>`).join('');
        }
        loadList();
    })();