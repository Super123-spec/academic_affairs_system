async function loadList() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/teacher/offerings?semester=' + encodeURIComponent(semester));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        tbody.innerHTML = res.data.length ? res.data.map(o => `
            <tr><td>${esc(o.code)}</td><td>${esc(o.course_name)}</td><td>${o.credit}</td><td>${o.hours}</td>
            <td>${esc(o.type)}</td><td>${o.selected_count}/${o.max_count}</td>
            <td>${esc(o.usual_ratio ?? 40)}% : ${esc(o.exam_ratio ?? 60)}%</td>
            <td><span class="tag ${o.status === '开放' ? 'tag-success' : 'tag-danger'}">${esc(o.status)}</span></td>
            <td><button class="btn btn-sm btn-default" data-action="openRatio\" data-arg='${jsAttr(o)}'>设置比例</button></td></tr>`).join('')
            : '<tr><td colspan="9" class="text-center" style="color:#999">该学期暂无开课</td></tr>';
    }

    function openRatio(o) {
        document.getElementById('ratioId').value = o.id;
        document.getElementById('ratioTitle').textContent = '设置成绩比例';
        document.getElementById('ratioInfo').textContent = `${o.code} ${o.course_name}（${o.semester}）`;
        document.getElementById('f_usualRatio').value = o.usual_ratio ?? 40;
        document.getElementById('f_examRatio').value = o.exam_ratio ?? 60;
        openModal('ratioModal');
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

    async function saveRatio() {
        const id = document.getElementById('ratioId').value;
        const usualRatio = parseInt(document.getElementById('f_usualRatio').value);
        const examRatio = parseInt(document.getElementById('f_examRatio').value);
        if (usualRatio + examRatio !== 100) { toast('平时占比与考试占比之和须为 100%', 'error'); return; }
        const res = await api('/api/teacher/offering/' + id + '/ratio', {
            method: 'PUT',
            body: JSON.stringify({ usual_ratio: usualRatio, exam_ratio: examRatio })
        });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal('ratioModal'); loadList(); } }
    }

    (async function () {
        if (!await initTeacherPage()) return;
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadList();
    })();