function statusTag(s) {
        return s === '已通过' ? '<span class="tag tag-success">已通过</span>'
            : s === '已拒绝' ? '<span class="tag tag-danger">已拒绝</span>'
            : '<span class="tag tag-warning">待审核</span>';
    }
    function applyProject(id, name) {
        document.getElementById('applyProjectId').value = id;
        document.getElementById('applyProjectName').textContent = name;
        document.getElementById('applyReason').value = '';
        document.getElementById('applyModal').classList.add('active');
    }
    function closeApplyModal() {
        document.getElementById('applyModal').classList.remove('active');
    }
    async function submitApply() {
        const res = await api('/api/student/apply/project', {
            method: 'POST',
            body: JSON.stringify({
                project_id: parseInt(document.getElementById('applyProjectId').value),
                reason: document.getElementById('applyReason').value.trim()
            })
        });
        if (res) {
            toast(res.message, res.success ? 'success' : 'error');
            if (res.success) { closeApplyModal(); loadData(); }
        }
    }
    async function loadData() {
        const [projects, applies] = await Promise.all([
            api('/api/student/projects'), api('/api/student/applies')
        ]);
        if (projects && projects.success) {
            document.getElementById('projectList').innerHTML = projects.data.length ? projects.data.map(p => `
                <div style="border:1px solid #e5e7eb;border-radius:4px;padding:16px 18px;margin-bottom:14px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <strong style="font-size:15px;">${esc(p.name)}</strong>
                            <span class="tag tag-primary" style="margin-left:8px;">${esc(p.type)}</span>
                        </div>
                        ${p.applied ? '<span class="tag tag-success">已报名</span>'
                            : `<button class="btn btn-sm btn-primary" data-action="applyProject" data-arg='[${p.id}, ${jsAttr(p.name)}]'>报名</button>`}
                    </div>
                    <div style="color:#777;font-size:13px;margin-top:8px;">${esc(p.description || '')}</div>
                    <div style="color:#999;font-size:12.5px;margin-top:8px;">
                        报名期限：${esc(p.start_date)} 至 ${esc(p.end_date)}　名额：${p.apply_count}/${p.max_count}
                    </div>
                </div>`).join('') : '<div class="empty-state">暂无开放报名的项目</div>';
        }
        if (applies && applies.success) {
            const list = applies.data.projects;
            document.getElementById('recordBody').innerHTML = list.length ? list.map(a => `
                <tr><td>${esc(a.project_name)}</td><td>${esc(a.project_type)}</td>
                <td>${statusTag(a.status)}</td><td>${esc(a.created_at)}</td></tr>`).join('')
                : '<tr><td colspan="4" class="text-center" style="color:#999">暂无报名记录</td></tr>';
        }
    }
    (async function () {
        await initLayout('报名申请');
        loadData();
    })();