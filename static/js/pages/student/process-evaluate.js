const EVAL_TYPE = 'process';
    const scores = { score_teaching: 0, score_content: 0, score_method: 0, score_effect: 0 };

    document.querySelectorAll('.star-group').forEach(g => {
        const field = g.dataset.field;
        for (let i = 1; i <= 5; i++) {
            const lb = document.createElement('label');
            lb.textContent = i;
            lb.onclick = () => {
                scores[field] = i;
                g.querySelectorAll('label').forEach((el, idx) => el.classList.toggle('active', idx < i));
            };
            g.appendChild(lb);
        }
    });

    function openModal(offeringId, courseName) {
        document.getElementById('evalOfferingId').value = offeringId;
        document.getElementById('evalCourseName').textContent = courseName;
        document.getElementById('evalComment').value = '';
        Object.keys(scores).forEach(k => scores[k] = 0);
        document.querySelectorAll('.star-group label').forEach(el => el.classList.remove('active'));
        document.getElementById('evalModal').classList.add('active');
    }
    function closeModal() { document.getElementById('evalModal').classList.remove('active'); }

    async function submitEval() {
        if (Object.values(scores).some(s => !s)) { toast('请完成全部四项评分', 'error'); return; }
        const res = await api('/api/student/evaluations', {
            method: 'POST',
            body: JSON.stringify({
                offering_id: parseInt(document.getElementById('evalOfferingId').value),
                type: EVAL_TYPE, ...scores,
                comment: document.getElementById('evalComment').value.trim()
            })
        });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) { closeModal(); loadList(); } }
    }

    async function loadList() {
        const res = await api('/api/student/evaluations?type=' + EVAL_TYPE);
        const box = document.getElementById('evalList');
        if (!res || !res.success) return;
        if (!res.data.length) { box.innerHTML = '<div class="empty-state">本学期暂无可评价的课程</div>'; return; }
        box.innerHTML = `<table class="table">
            <thead><tr><th>课程名称</th><th>任课教师</th><th>学期</th><th>评价状态</th><th>总分</th><th>操作</th></tr></thead>
            <tbody>${res.data.map(e => `
                <tr>
                    <td>${esc(e.course_name)}</td><td>${esc(e.teacher_name || '-')}</td><td>${esc(e.semester)}</td>
                    <td>${e.evaluation_id ? '<span class="tag tag-success">已评价</span>' : '<span class="tag tag-warning">待评价</span>'}</td>
                    <td>${e.total_score ?? '-'}</td>
                    <td><button class="btn btn-sm ${e.evaluation_id ? 'btn-default' : 'btn-primary'}"
                        data-action="openModal" data-arg='[${e.offering_id}, ${jsAttr(e.course_name)}]'>${e.evaluation_id ? '修改评价' : '评价'}</button></td>
                </tr>`).join('')}</tbody></table>`;
    }
    (async function () {
        await initLayout('教学评价');
        loadList();
    })();