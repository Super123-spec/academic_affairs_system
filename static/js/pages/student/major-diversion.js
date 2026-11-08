async function loadData() {
        const res = await api('/api/student/major-diversion');
        if (!res || !res.success) return;
        const d = res.data;
        const box = document.getElementById('diversionBox');
        if (d.status === '已确认') {
            box.innerHTML = `<div style="padding:20px;background:#edf7e8;border:1px solid #b7e0a8;border-radius:4px;color:#389e0d;">
                你已完成分流专业确认，分流后专业：<strong>${esc(d.diversion_major || '-')}</strong>
            </div>`;
            return;
        }
        box.innerHTML = `
            <div class="detail-row"><div class="detail-label">当前专业</div><div class="detail-value">${esc(d.current_major || '-')}</div></div>
            <div class="form-group" style="margin-top:18px;"><label>选择分流专业</label>
                <select id="majorSel">${d.majors.map(m => `<option value="${m.id}">${esc(m.college_name)} - ${esc(m.name)}</option>`).join('')}</select>
            </div>
            <button class="btn btn-primary" data-action="confirmDiversion">确认分流专业</button>
            <p style="color:#cf1322;font-size:13px;margin-top:10px;">注意：确认后不可自行修改，请谨慎选择。</p>`;
    }
    async function confirmDiversion() {
        if (!(await confirmDialog('确认选择该分流专业吗？确认后不可自行修改。', { title: '分流确认', danger: false, okText: '确认' }))) return;
        const res = await api('/api/student/major-diversion', {
            method: 'POST', body: JSON.stringify({ major_id: parseInt(document.getElementById('majorSel').value) })
        });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadData(); }
    }
    (async function () {
        await initLayout('信息维护');
        loadData();
    })();