(async function () {
        await initLayout('信息查询');
        const res = await api('/api/student/profile');
        if (!res || !res.success) return;
        const s = res.data;
        const rows = [
            ['学号', s.username], ['姓名', s.real_name], ['性别', s.gender],
            ['学院', s.college_name], ['专业', s.major_name], ['班级', s.class_name],
            ['出生日期', s.birth_date], ['政治面貌', s.political_status], ['籍贯', s.native_place],
            ['身份证号', s.id_card], ['联系电话', s.phone], ['电子邮箱', s.email],
            ['家庭住址', s.address], ['入学日期', s.enrollment_date], ['学籍状态', s.status],
        ];
        document.getElementById('profileBox').innerHTML =
            '<div class="detail-grid">' + rows.map(([k, v]) => `
                <div class="detail-row"><div class="detail-label">${k}</div><div class="detail-value">${esc(v) || '<span style="color:#bbb">未填写</span>'}</div></div>
            `).join('') + '</div>';
    })();