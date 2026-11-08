let students = [];
    let sortKey = null;      // 当前排序字段
    let sortAsc = true;      // true=升序，false=降序

    async function loadOfferings() {
        const res = await api('/api/teacher/offerings');
        if (!res || !res.success) return;
        document.getElementById('offeringSel').innerHTML = res.data.length
            ? res.data.map(o => `<option value="${o.id}">${esc(o.course_name)}（${esc(o.semester)}）</option>`).join('')
            : '<option value="">本学期暂无开课</option>';
    }

    // 从当前表格收集用户已输入但未保存的成绩，避免排序后丢失
    function collectEditing() {
        const map = {};
        students.forEach((s, i) => {
            const u = document.getElementById('usual_' + i);
            const e = document.getElementById('exam_' + i);
            if (u && e) {
                map[s.student_id] = {
                    usual: u.value,
                    exam: e.value,
                };
            }
        });
        return map;
    }

    // 点击表头排序：同一列再点切换升/降序
    function sortBy(key) {
        if (sortKey === key) {
            sortAsc = !sortAsc;
        } else {
            sortKey = key;
            sortAsc = true;
        }
        renderGrades();
    }

    // 排序箭头显示
    function updateSortArrows() {
        ['username', 'real_name', 'class_name', 'usual_score', 'exam_score', 'total_score'].forEach(k => {
            const el = document.getElementById('sort-' + k);
            if (el) el.textContent = (sortKey === k) ? (sortAsc ? '▲' : '▼') : '';
        });
    }

    // 把当前输入回写到数据副本（用于按「平时/考试」排序时用最新输入值）
    function withEditing() {
        const editing = collectEditing();
        return students.map(s => {
            const ed = editing[s.student_id] || {};
            const u = ed.usual !== undefined ? ed.usual : (s.usual_score ?? '');
            const e = ed.exam !== undefined ? ed.exam : (s.exam_score ?? '');
            return Object.assign({}, s, {
                usual_score: u === '' ? null : parseFloat(u),
                exam_score: e === '' ? null : parseFloat(e),
                _u: u,
                _e: e,
            });
        });
    }

    function renderGrades() {
        const tbody = document.getElementById('gradeBody');
        if (!students.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color:#999">该课程暂无选课学生</td></tr>';
            document.getElementById('saveBar').style.display = 'none';
            return;
        }

        let list = withEditing();

        if (sortKey) {
            list.sort((a, b) => {
                let va = a[sortKey], vb = b[sortKey];
                // 空值一律排到末尾（不论升降序）
                const aEmpty = (va === null || va === undefined || va === '');
                const bEmpty = (vb === null || vb === undefined || vb === '');
                if (aEmpty && bEmpty) return 0;
                if (aEmpty) return 1;
                if (bEmpty) return -1;
                if (typeof va === 'number' && typeof vb === 'number') {
                    return sortAsc ? va - vb : vb - va;
                }
                // 字符串：中文按拼音比较
                const r = String(va).localeCompare(String(vb), 'zh-CN');
                return sortAsc ? r : -r;
            });
        }

        tbody.innerHTML = list.map((s, i) => `
            <tr>
                <td>${esc(s.username)}</td><td>${esc(s.real_name)}</td><td>${esc(s.class_name || '-')}</td>
                <td><input type="number" min="0" max="100" step="0.5" id="usual_${i}" value="${s._u}" style="width:90px;padding:5px 8px;border:1px solid #d1d5db;border-radius:4px;"></td>
                <td><input type="number" min="0" max="100" step="0.5" id="exam_${i}" value="${s._e}" style="width:90px;padding:5px 8px;border:1px solid #d1d5db;border-radius:4px;"></td>
                <td>${s.total_score ?? '-'}</td>
            </tr>`).join('');

        // 排序后 students 顺序也要同步，否则保存时 id 与输入框错位
        students = list;
        document.getElementById('saveBar').style.display = 'block';
        updateSortArrows();
    }

    async function loadGrades() {
        const oid = document.getElementById('offeringSel').value;
        if (!oid) return;
        const res = await api(`/api/teacher/offering/${oid}/grades`);
        const tbody = document.getElementById('gradeBody');
        if (!res || !res.success) { if (res) toast(res.message, 'error'); return; }
        students = res.data;
        sortKey = null;
        sortAsc = true;
        const ratio = res.ratio || { usual_ratio: 40, exam_ratio: 60 };
        document.getElementById('ratioHint').innerHTML =
            `总评成绩 = 平时成绩 × <strong style="color:#1f6feb">${ratio.usual_ratio}%</strong> + 考试成绩 × <strong style="color:#1f6feb">${ratio.exam_ratio}%</strong>，保存时自动计算。`;
        renderGrades();
    }

    async function saveGrades() {
        const oid = document.getElementById('offeringSel').value;
        const grades = students.map((s, i) => ({
            student_id: s.student_id,
            usual_score: document.getElementById('usual_' + i).value === '' ? null : parseFloat(document.getElementById('usual_' + i).value),
            exam_score: document.getElementById('exam_' + i).value === '' ? null : parseFloat(document.getElementById('exam_' + i).value)
        }));
        const res = await api(`/api/teacher/offering/${oid}/grades`, { method: 'POST', body: JSON.stringify({ grades }) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadGrades(); }
    }

    function openImport() {
        const sel = document.getElementById('offeringSel');
        const oid = sel.value;
        if (!oid) { toast('请先选择课程', 'error'); return; }
        const courseName = sel.selectedOptions[0].text;
        openGradeImportDialog(oid, courseName, loadGrades);
    }

    (async function () {
        if (!await initTeacherPage()) return;
        await loadOfferings();
        loadGrades();
    })();