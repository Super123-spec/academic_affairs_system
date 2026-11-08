async function loadData() {
        const res = await api('/api/student/registration');
        if (!res || !res.success) return;
        document.getElementById('regBox').innerHTML = res.registered
            ? `<div style="padding:20px;background:#edf7e8;border:1px solid #b7e0a8;border-radius:4px;color:#389e0d;">
                 你已完成 <strong>${esc(res.current_semester)}</strong> 学期的报到注册。
               </div>`
            : `<div style="padding:20px;background:#fdf3e3;border:1px solid #f0d29a;border-radius:4px;">
                 你还未完成 <strong>${esc(res.current_semester)}</strong> 学期的报到注册。
               </div>
               <button class="btn btn-primary" style="margin-top:16px;" data-action="doRegister">立即报到注册</button>`;
        document.getElementById('recordBody').innerHTML = res.data.length ? res.data.map(r => `
            <tr><td>${esc(r.semester)}</td><td>${esc(r.register_time)}</td>
            <td><span class="tag tag-success">${esc(r.status)}</span></td></tr>`).join('')
            : '<tr><td colspan="3" class="text-center" style="color:#999">暂无注册记录</td></tr>';
    }
    async function doRegister() {
        const res = await api('/api/student/registration', { method: 'POST' });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadData(); }
    }
    (async function () {
        await initLayout('信息维护');
        loadData();
    })();