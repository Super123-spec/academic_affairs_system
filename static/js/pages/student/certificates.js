(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/certificates');
        if (!res || !res.success) return;
        const s = res.student;
        document.getElementById('certArea').innerHTML = `
            <div style="text-align:center;margin-bottom:18px;">
                <h2 style="letter-spacing:4px;">贵阳信息科技学院学生证书登记表</h2>
            </div>
            <div class="detail-grid" style="margin-bottom:14px;">
                <div class="detail-row"><div class="detail-label">学号</div><div class="detail-value">${esc(s.username)}</div></div>
                <div class="detail-row"><div class="detail-label">姓名</div><div class="detail-value">${esc(s.real_name)}</div></div>
                <div class="detail-row"><div class="detail-label">学院</div><div class="detail-value">${esc(s.college_name || '')}</div></div>
                <div class="detail-row"><div class="detail-label">班级</div><div class="detail-value">${esc(s.class_name || '')}</div></div>
            </div>
            <table class="table">
                <thead><tr><th>证书名称</th><th>证书编号</th><th>颁发日期</th><th>颁发机构</th></tr></thead>
                <tbody>
                ${res.data.length ? res.data.map(c => `<tr>
                    <td>${esc(c.name)}</td><td>${esc(c.cert_no || '-')}</td>
                    <td>${esc(c.issue_date || '-')}</td><td>${esc(c.issuer || '-')}</td>
                </tr>`).join('') : '<tr><td colspan="4" class="text-center">暂无证书记录</td></tr>'}
                </tbody>
            </table>
            <div style="margin-top:30px;color:#666;font-size:13px;display:flex;justify-content:space-between;">
                <span>打印日期：${new Date().toLocaleDateString('zh-CN')}</span>
                <span>贵阳信息科技学院教务处</span>
            </div>`;
    })();