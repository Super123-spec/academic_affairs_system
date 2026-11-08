async function loadAll() {
        const [colleges, majors, classes] = await Promise.all([
            api('/api/admin/colleges'), api('/api/admin/majors'), api('/api/admin/classes')
        ]);
        if (colleges && colleges.success) {
            document.getElementById('collegeBody').innerHTML = colleges.data.map(c => `
                <tr><td><strong>${esc(c.name)}</strong><br><span style="color:#999;font-size:12px;">代码 ${esc(c.code || '-')}</span></td>
                <td style="width:60px;"><button class="btn btn-sm btn-danger" data-action="delCollege" data-arg='[${c.id}]'>删除</button></td></tr>`).join('')
                || '<tr><td class="text-center" style="color:#999">暂无</td></tr>';
        }
        if (majors && majors.success) {
            document.getElementById('majorBody').innerHTML = majors.data.map(m => `
                <tr><td><strong>${esc(m.name)}</strong><br><span style="color:#999;font-size:12px;">${esc(m.college_name)} · ${esc(m.code || '-')}</span></td>
                <td style="width:60px;"><button class="btn btn-sm btn-danger" data-action="delMajor" data-arg='[${m.id}]'>删除</button></td></tr>`).join('')
                || '<tr><td class="text-center" style="color:#999">暂无</td></tr>';
        }
        if (classes && classes.success) {
            document.getElementById('classBody').innerHTML = classes.data.map(c => `
                <tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.major_name)}</td><td>${c.grade_year}</td>
                <td>${c.student_count}</td>
                <td><button class="btn btn-sm btn-danger" data-action="delClass" data-arg='[${c.id}]'>删除</button></td></tr>`).join('')
                || '<tr><td colspan="5" class="text-center" style="color:#999">暂无</td></tr>';
        }
    }

    async function addCollege() {
        const d = await formDialog('新增学院', [
            { key: 'name', label: '学院名称', required: true, placeholder: '如：信息工程学院' },
            { key: 'code', label: '学院代码', placeholder: '如：01' },
        ]);
        if (!d.ok) return;
        const r = await api('/api/admin/colleges', { method: 'POST', body: JSON.stringify(d.values) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadAll(); }
    }
    async function delCollege(id) {
        if (!(await confirmDialog('删除学院将级联删除其专业班级，确定？'))) return;
        const r = await api('/api/admin/colleges/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadAll(); }
    }
    async function addMajor() {
        const meta = await loadMeta();
        const d = await formDialog('新增专业', [
            { key: 'college_id', label: '所属学院', type: 'select', required: true,
              options: meta.colleges.map(c => ({ value: c.id, label: c.name })) },
            { key: 'name', label: '专业名称', required: true, placeholder: '如：网络工程' },
            { key: 'code', label: '专业代码', placeholder: '如：0101' },
        ]);
        if (!d.ok) return;
        const r = await api('/api/admin/majors', { method: 'POST',
            body: JSON.stringify({ ...d.values, college_id: parseInt(d.values.college_id) }) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadAll(); }
    }
    async function delMajor(id) {
        if (!(await confirmDialog('删除专业将级联删除其班级，确定？'))) return;
        const r = await api('/api/admin/majors/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadAll(); }
    }
    async function addClass() {
        const meta = await loadMeta();
        const d = await formDialog('新增班级', [
            { key: 'major_id', label: '所属专业', type: 'select', required: true,
              options: meta.majors.map(m => ({ value: m.id, label: m.college_name + ' - ' + m.name })) },
            { key: 'name', label: '班级名称', required: true, placeholder: '如：网络2401' },
            { key: 'grade_year', label: '入学年份', type: 'number', required: true, value: new Date().getFullYear() },
        ]);
        if (!d.ok) return;
        const r = await api('/api/admin/classes', { method: 'POST',
            body: JSON.stringify({ ...d.values, major_id: parseInt(d.values.major_id), grade_year: parseInt(d.values.grade_year) }) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadAll(); }
    }
    async function delClass(id) {
        if (!(await confirmDialog('确定删除该班级？'))) return;
        const r = await api('/api/admin/classes/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadAll(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        loadAll();
    })();