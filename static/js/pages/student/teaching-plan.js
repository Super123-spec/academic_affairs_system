(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/teaching-plan');
        if (!res || !res.success) return;
        document.getElementById('majorName').textContent = res.major_name || '--';
        document.getElementById('className').textContent = res.class_name || '--';
        const box = document.getElementById('planBox');
        if (!res.data.length) {
            box.innerHTML = '<div class="empty-state">本专业暂无教学执行计划</div>';
            return;
        }
        // 按学期分组
        const groups = {};
        res.data.forEach(c => {
            (groups[c.semester_no] = groups[c.semester_no] || []).push(c);
        });
        box.innerHTML = Object.keys(groups).sort().map(no => `
            <div style="margin-bottom:18px;">
                <div style="font-weight:600;margin-bottom:8px;">第 ${no} 学期</div>
                <table class="table">
                    <thead><tr><th>课程号</th><th>课程名称</th><th>学分</th><th>学时</th><th>类别</th></tr></thead>
                    <tbody>${groups[no].map(c => `
                        <tr><td>${esc(c.code)}</td><td>${esc(c.course_name)}</td><td>${c.credit}</td>
                        <td>${c.hours}</td><td><span class="tag ${c.category === '必修' ? 'tag-primary' : c.category === '实践' ? 'tag-warning' : 'tag-success'}">${esc(c.category)}</span></td></tr>`).join('')}
                    </tbody>
                </table>
            </div>`).join('');
    })();