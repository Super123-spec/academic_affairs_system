let plans = [];
    let courseOptions = [];

    async function loadCourses() {
        const res = await api('/api/admin/courses?page_size=100');
        if (res && res.success) {
            courseOptions = res.data.map(c => ({ value: c.id, label: `${c.code} ${c.name}（${c.credit}学分）` }));
        }
    }

    async function loadList() {
        const mid = document.getElementById('majorSel').value;
        const res = await api('/api/admin/teaching-plans' + (mid ? '?major_id=' + mid : ''));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        plans = res.data || [];

        // 汇总
        const bySem = {};
        plans.forEach(p => {
            bySem[p.semester_no] = bySem[p.semester_no] || { count: 0, credit: 0 };
            bySem[p.semester_no].count++;
            bySem[p.semester_no].credit += parseFloat(p.credit || 0);
        });
        const semKeys = Object.keys(bySem).sort((a, b) => a - b);
        document.getElementById('summary').innerHTML = plans.length
            ? `共 <strong>${plans.length}</strong> 门课程　` +
              semKeys.map(k => `第${k}学期：${bySem[k].count}门/${bySem[k].credit.toFixed(1)}学分`).join('　')
            : '';

        tbody.innerHTML = plans.length ? plans.map(p => `
            <tr>
                <td>${esc(p.major_name)}</td>
                <td><strong>第 ${p.semester_no} 学期</strong></td>
                <td>${esc(p.code)}</td><td>${esc(p.course_name)}</td>
                <td>${p.credit}</td><td>${p.hours}</td>
                <td><span class="tag tag-primary">${esc(p.type)}</span></td>
                <td>${esc(p.category)}</td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(p)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delItem" data-arg='[${p.id}]'>移除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="9" class="text-center" style="color:#999">该专业暂无教学计划，点击「添加课程」开始</td></tr>';
    }

    async function openEdit(p) {
        const isEdit = !!p;
        const meta = await loadMeta();
        if (!courseOptions.length) await loadCourses();
        const curMajor = document.getElementById('majorSel').value;
        if (!isEdit && !curMajor) { toast('请先在顶部选择专业', 'error'); return; }

        const fields = [
            { key: 'semester_no', label: '开课学期（第几学期）', type: 'number',
              value: isEdit ? p.semester_no : 1 },
            { key: 'category', label: '计划类别', type: 'select',
              value: isEdit ? p.category : '必修',
              options: ['必修', '选修', '通识', '实践'].map(c => ({ value: c, label: c })) },
        ];
        if (isEdit) {
            fields.unshift({ key: 'course_id', label: '课程', type: 'select', value: p.course_id, options: courseOptions });
        } else {
            fields.unshift({ key: 'course_id', label: '课程', type: 'select', required: true, options: courseOptions });
        }

        const d = await formDialog(isEdit ? '编辑教学计划' : '添加到教学计划', fields);
        if (!d.ok) return;

        if (isEdit) {
            const r = await api('/api/admin/teaching-plans/' + p.id, { method: 'PUT',
                body: JSON.stringify({ semester_no: parseInt(d.values.semester_no), category: d.values.category }) });
            if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
        } else {
            const r = await api('/api/admin/teaching-plans', { method: 'POST',
                body: JSON.stringify({
                    major_id: parseInt(curMajor), course_id: parseInt(d.values.course_id),
                    semester_no: parseInt(d.values.semester_no), category: d.values.category,
                }) });
            if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
        }
    }

    async function delItem(id) {
        if (!(await confirmDialog('确定从教学计划中移除该课程？'))) return;
        const r = await api('/api/admin/teaching-plans/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const meta = await loadMeta();
        document.getElementById('majorSel').innerHTML = '<option value="">全部专业</option>' +
            meta.majors.map(m => `<option value="${m.id}">${esc(m.college_name)} - ${esc(m.name)}</option>`).join('');
        await loadCourses();
        loadList();
    })();