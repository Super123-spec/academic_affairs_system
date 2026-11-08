async function loadList() {
        const res = await api('/api/admin/classrooms');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(r => `
            <tr><td>${esc(r.building)}</td><td>${esc(r.room)}</td><td>${r.capacity}人</td>
            <td><button class="btn btn-sm btn-danger" data-action="delRoom" data-arg='[${r.id}]'>删除</button></td></tr>`).join('')
            : '<tr><td colspan="4" class="text-center" style="color:#999">暂无教室</td></tr>';
    }
    async function addRoom() {
        const d = await formDialog('新增教室', [
            { key: 'building', label: '教学楼', required: true, placeholder: '如：博学楼' },
            { key: 'room', label: '教室号', required: true, placeholder: '如：A101' },
            { key: 'capacity', label: '容量（人数）', type: 'number', value: 60 },
        ]);
        if (!d.ok) return;
        const r = await api('/api/admin/classrooms', { method: 'POST',
            body: JSON.stringify({ ...d.values, capacity: parseInt(d.values.capacity) || 60 }) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
    }
    async function delRoom(id) {
        if (!(await confirmDialog('确定删除该教室？'))) return;
        const r = await api('/api/admin/classrooms/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }
    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();