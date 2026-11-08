(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/grade-report');
        if (!res || !res.success) return;
        const s = res.student, rows = res.data, sum = res.summary;
        document.getElementById('reportArea').innerHTML = `
            <div style="text-align:center;margin-bottom:18px;">
                <h2 style="letter-spacing:4px;">贵阳信息科技学院学生成绩总表</h2>
            </div>
            <div class="detail-grid" style="margin-bottom:14px;">
                <div class="detail-row"><div class="detail-label">学号</div><div class="detail-value">${esc(s.username)}</div></div>
                <div class="detail-row"><div class="detail-label">姓名</div><div class="detail-value">${esc(s.real_name)}</div></div>
                <div class="detail-row"><div class="detail-label">学院</div><div class="detail-value">${esc(s.college_name || '')}</div></div>
                <div class="detail-row"><div class="detail-label">班级</div><div class="detail-value">${esc(s.class_name || '')}</div></div>
            </div>
            <table class="table">
                <thead><tr><th>学期</th><th>课程号</th><th>课程名称</th><th>学分</th><th>性质</th><th>总评</th><th>绩点</th></tr></thead>
                <tbody>
                ${rows.length ? rows.map(g => `<tr>
                    <td>${esc(g.semester)}</td><td>${esc(g.code)}</td><td>${esc(g.course_name)}</td>
                    <td>${g.credit}</td><td>${esc(g.type)}</td><td>${g.total_score}</td><td>${g.grade_point ?? '-'}</td>
                </tr>`).join('') : '<tr><td colspan="7" class="text-center">暂无成绩</td></tr>'}
                </tbody>
            </table>
            <div style="margin-top:16px;display:flex;gap:40px;">
                <span>已获学分：<strong>${sum.total_credit}</strong></span>
                <span>平均分：<strong>${sum.avg_score}</strong></span>
                <span>平均绩点（GPA）：<strong>${sum.gpa}</strong></span>
            </div>
            <div style="margin-top:30px;color:#666;font-size:13px;display:flex;justify-content:space-between;">
                <span>打印日期：${new Date().toLocaleDateString('zh-CN')}</span>
                <span>贵阳信息科技学院教务处（盖章）</span>
            </div>`;
    })();