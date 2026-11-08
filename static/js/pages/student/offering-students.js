let offeringsCache = [];
    async function loadOfferings() {
        const res = await api('/api/student/offering-students');
        if (!res || !res.success) return;
        offeringsCache = res.offerings;
        document.getElementById('offeringSel').innerHTML = offeringsCache.length
            ? offeringsCache.map(o => `<option value="${o.id}">${esc(o.course_name)}（${esc(o.semester)}）</option>`).join('')
            : '<option value="">暂无可查课程</option>';
    }
    async function loadStudents() {
        const oid = document.getElementById('offeringSel').value;
        if (!oid) return;
        const res = await api('/api/student/offering-students?offering_id=' + oid);
        const tbody = document.getElementById('stuBody');
        if (!res || !res.success) return;
        if (!res.students.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center" style="color:#999">该课程暂无选课学生</td></tr>';
            return;
        }
        tbody.innerHTML = res.students.map(s => `
            <tr><td>${esc(s.username)}</td><td>${esc(s.real_name)}</td><td>${esc(s.gender)}</td><td>${esc(s.class_name || '-')}</td></tr>`).join('');
    }
    (async function () {
        await initLayout('信息查询');
        await loadOfferings();
        loadStudents();
    })();