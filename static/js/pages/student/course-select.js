let allCourses = [];
    const WEEKDAYS = ['', '一', '二', '三', '四', '五', '六', '日'];

    function fmtSchedule(list) {
        if (!list || !list.length) return '时间待定';
        return list.map(s => `周${WEEKDAYS[s.weekday]} ${s.start_section}-${s.end_section}节（${s.week_type !== '全周' ? s.week_type + ' ' : ''}${s.weeks}周${s.building ? '，' + s.building + s.room : ''}）`).join('；');
    }

    function renderList() {
        const kw = document.getElementById('keyword').value.trim();
        const tp = document.getElementById('typeSel').value;
        const list = allCourses.filter(c =>
            (!kw || c.course_name.includes(kw) || c.code.includes(kw)) && (!tp || c.type === tp));
        const box = document.getElementById('courseList');
        if (!list.length) {
            box.innerHTML = '<div class="empty-state">没有符合条件的课程</div>';
            return;
        }
        box.innerHTML = `<table class="table">
            <thead><tr><th>课程号</th><th>课程名称</th><th>学分</th><th>性质</th><th>教师</th><th>上课时间</th><th>容量</th><th>操作</th></tr></thead>
            <tbody>${list.map(c => {
                const full = c.selected_count >= c.max_count;
                let action;
                if (c.enrolled) {
                    action = `<button class="btn btn-sm btn-danger" data-action="dropCourse" data-arg='[${c.id}]'>退选</button>`;
                } else if (full) {
                    action = '<span class="tag tag-danger">已满</span>';
                } else {
                    action = `<button class="btn btn-sm btn-primary" data-action="enrollCourse" data-arg='[${c.id}]'>选课</button>`;
                }
                return `<tr>
                    <td>${esc(c.code)}</td><td>${esc(c.course_name)}</td><td>${c.credit}</td>
                    <td><span class="tag ${c.type === '必修' ? 'tag-primary' : 'tag-success'}">${esc(c.type)}</span></td>
                    <td>${esc(c.teacher_name || '-')}</td>
                    <td style="font-size:12.5px;">${esc(fmtSchedule(c.schedules))}</td>
                    <td>${c.selected_count}/${c.max_count}</td><td>${action}</td>
                </tr>`;
            }).join('')}</tbody></table>`;
    }

    async function enrollCourse(id) {
        const res = await api('/api/student/course-select/enroll', { method: 'POST', body: JSON.stringify({ offering_id: id }) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadCourses(); }
    }
    async function dropCourse(id) {
        if (!(await confirmDialog('确定退选该课程吗？'))) return;
        const res = await api('/api/student/course-select/drop', { method: 'POST', body: JSON.stringify({ offering_id: id }) });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadCourses(); }
    }
    async function loadCourses() {
        const res = await api('/api/student/course-select/list');
        if (res && res.success) { allCourses = res.data; renderList(); }
    }
    (async function () {
        await initLayout('选课');
        loadCourses();
    })();