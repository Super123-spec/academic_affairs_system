async function loadList() {
        const sem = document.getElementById('semesterSel').value;
        const res = await api('/api/admin/offerings' + (sem ? '?semester=' + encodeURIComponent(sem) : ''));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(o => `
            <tr>
                <td>${esc(o.code)}</td><td>${esc(o.course_name)}</td><td>${o.credit}</td>
                <td>${esc(o.teacher_name || '待定')}</td>
                <td>${o.class_names ? esc(o.class_names) : '<span style="color:#bbb">不限</span>'}</td>
                <td>${esc(o.semester)}</td>
                <td>${o.selected_count}/${o.max_count}</td>
                <td>${esc(o.usual_ratio ?? 40)}% : ${esc(o.exam_ratio ?? 60)}%</td>
                <td><span class="tag ${o.status === '开放' ? 'tag-success' : 'tag-danger'}">${esc(o.status)}</span></td>
                <td><div class="table-actions">
                    <button class="btn btn-sm btn-default" data-action="openEdit\" data-arg='${jsAttr(o)}'>编辑</button>
                    <button class="btn btn-sm btn-danger" data-action="delOffering" data-arg='[${o.id}]'>删除</button>
                </div></td>
            </tr>`).join('') : '<tr><td colspan="10" class="text-center" style="color:#999">暂无开课</td></tr>';
    }

    // 班级选择：Set 为数据源，复选框只是视图（筛选切换不丢已选）
    let ALL_CLASSES = [];
    let classSelected = new Set();

    function renderClassBoxes() {
        const filter = document.getElementById('f_filterMajor').value;
        let classes = ALL_CLASSES;
        if (filter) classes = classes.filter(c => c.major_id == filter);
        const box = document.getElementById('f_classBoxes');
        box.innerHTML = classes.length ? classes.map(c => `
            <label style="display:inline-flex;align-items:center;gap:5px;font-size:13.5px;cursor:pointer;margin:2px 6px;">
                <input type="checkbox" value="${c.id}" ${classSelected.has(c.id) ? 'checked' : ''} data-change="toggleClass" data-arg='[${c.id}]' style="width:auto;">${esc(c.name)}
            </label>`).join('') : '<span style="color:#999;font-size:13px;">该专业暂无班级</span>';
        updateClassTags();
    }

    function toggleClass(id, checked) {
        if (checked === undefined) checked = this.checked;
        if (checked) classSelected.add(id); else classSelected.delete(id);
        updateClassTags();
    }

    function updateClassTags() {
        const map = {};
        ALL_CLASSES.forEach(c => map[c.id] = c.name);
        const ids = Array.from(classSelected);
        document.getElementById('f_classSelected').innerHTML = ids.length
            ? ids.map(id => `<span class="tag tag-primary" style="cursor:default;">${esc(map[id] || id)}<span style="cursor:pointer;margin-left:4px;" data-action="uncheckClass\" data-arg='[${id}]'>×</span></span>`).join('')
            : '<span style="color:#bbb;font-size:12.5px;">未选择班级（不限班级）</span>';
    }

    function uncheckClass(id) {
        classSelected.delete(id);
        const cb = document.querySelector(`#f_classBoxes input[value="${id}"]`);
        if (cb) cb.checked = false;
        updateClassTags();
    }

    function checkAllVisible() {
        document.querySelectorAll('#f_classBoxes input[type=checkbox]').forEach(cb => {
            cb.checked = true;
            classSelected.add(parseInt(cb.value));
        });
        updateClassTags();
    }

    function uncheckAll() {
        document.querySelectorAll('#f_classBoxes input[type=checkbox]').forEach(cb => cb.checked = false);
        classSelected.clear();
        updateClassTags();
    }

    function openEdit(o) {
        const isEdit = !!o;
        document.getElementById('modalTitle').textContent = isEdit ? '编辑开课' : '新增开课';
        document.getElementById('editId').value = isEdit ? o.id : '';
        document.getElementById('f_courseId').value = isEdit ? o.course_id : '';
        document.getElementById('f_teacherId').value = isEdit ? (o.teacher_id || '') : '';
        document.getElementById('f_semester').value = isEdit ? o.semester : '';
        document.getElementById('f_maxCount').value = isEdit ? o.max_count : 60;
        document.getElementById('f_usualRatio').value = isEdit ? (o.usual_ratio ?? 40) : 40;
        document.getElementById('f_examRatio').value = isEdit ? (o.exam_ratio ?? 60) : 60;
        document.getElementById('f_status').value = isEdit ? o.status : '开放';
        // 回显班级（先重置筛选为全部专业，避免遗漏跨专业的已选班级）
        document.getElementById('f_filterMajor').value = '';
        classSelected = new Set(isEdit ? (o.class_ids || []) : []);
        renderClassBoxes();
        openModal('editModal');
    }

    function getClassIds() {
        return Array.from(classSelected);
    }

    function syncRatio() {
        const u = document.getElementById('f_usualRatio');
        const e = document.getElementById('f_examRatio');
        if (document.activeElement === u) {
            e.value = Math.max(0, 100 - (parseInt(u.value) || 0));
        } else if (document.activeElement === e) {
            u.value = Math.max(0, 100 - (parseInt(e.value) || 0));
        }
    }

    async function saveOffering() {
        const id = document.getElementById('editId').value;
        const usualRatio = parseInt(document.getElementById('f_usualRatio').value);
        const examRatio = parseInt(document.getElementById('f_examRatio').value);
        if (usualRatio + examRatio !== 100) { toast('平时占比与考试占比之和须为 100%', 'error'); return; }
        const body = {
            course_id: parseInt(document.getElementById('f_courseId').value),
            teacher_id: parseInt(document.getElementById('f_teacherId').value) || null,
            semester: document.getElementById('f_semester').value.trim(),
            max_count: parseInt(document.getElementById('f_maxCount').value) || 60,
            status: document.getElementById('f_status').value,
            usual_ratio: usualRatio,
            exam_ratio: examRatio,
            class_ids: getClassIds()
        };
        if (!body.course_id || !body.semester) { toast('请选择课程并填写学期', 'error'); return; }
        const res = await api(id ? '/api/admin/offerings/' + id : '/api/admin/offerings',
            { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('editModal'); loadList(); } }
    }

    async function delOffering(id) {
        if (!(await confirmDialog('删除开课将级联删除排课与选课记录，确定？'))) return;
        const r = await api('/api/admin/offerings/' + id, { method: 'DELETE' });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        const meta = await loadMeta();
        document.getElementById('semesterSel').innerHTML =
            '<option value="">全部学期</option>' + meta.semesters.map(s => `<option>${esc(s)}</option>`).join('');
        document.getElementById('f_semester').value = meta.current_semester;
        // 学期候选（datalist）：点选即可，避免手填格式错误
        document.getElementById('semesterList').innerHTML =
            meta.semesters.map(s => `<option value="${esc(s)}">`).join('');
        const courses = await api('/api/admin/courses?page_size=100');
        if (courses && courses.success) {
            document.getElementById('f_courseId').innerHTML =
                courses.data.map(c => `<option value="${c.id}">${esc(c.code)} ${esc(c.name)}</option>`).join('');
        }
        const teachers = await api('/api/admin/teachers?page_size=100');
        if (teachers && teachers.success) {
            document.getElementById('f_teacherId').innerHTML = '<option value="">待定</option>' +
                teachers.data.map(t => `<option value="${t.id}">${esc(t.real_name)}（${esc(t.username)}）</option>`).join('');
        }
        // 班级数据：专业筛选下拉 + 复选框渲染
        if (meta && meta.classes) {
            ALL_CLASSES = meta.classes;
            const majors = {};
            meta.classes.forEach(c => { majors[c.major_id] = c.major_name; });
            document.getElementById('f_filterMajor').innerHTML = '<option value="">全部专业</option>' +
                Object.entries(majors).map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
            renderClassBoxes();
        }
        loadList();
    })();