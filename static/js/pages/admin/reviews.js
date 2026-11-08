let currentType = 'retake';

    const COLUMNS = {
        retake: {
            head: ['学号', '姓名', '课程', '学期', '理由', '申请时间'],
            row: a => `<td>${esc(a.username)}</td><td>${esc(a.student_name)}</td><td>${esc(a.course_name)}</td>
                       <td>${esc(a.semester)}</td><td>${esc(a.reason || '-')}</td><td>${esc(a.created_at)}</td>`
        },
        status_change: {
            head: ['学号', '姓名', '异动类型', '理由', '申请日期'],
            row: a => `<td>${esc(a.username)}</td><td>${esc(a.student_name)}</td><td>${esc(a.change_type)}</td>
                       <td>${esc(a.reason || '-')}</td><td>${esc(a.apply_date)}</td>`
        },
        project: {
            head: ['学号', '姓名', '项目', '理由', '申请时间'],
            row: a => `<td>${esc(a.username)}</td><td>${esc(a.student_name)}</td><td>${esc(a.project_name)}</td>
                       <td>${esc(a.reason || '-')}</td><td>${esc(a.created_at)}</td>`
        },
        credit_substitute: {
            head: ['学号', '姓名', '校外课程', '替代课程', '学分', '申请时间'],
            row: a => `<td>${esc(a.username)}</td><td>${esc(a.student_name)}</td>
                       <td>${esc(a.external_course)}（${esc(a.external_school)}）</td>
                       <td>${esc(a.substitute_course_name || '-')}</td><td>${a.external_credit ?? '-'}</td><td>${esc(a.created_at)}</td>`
        }
    };

    function switchTab(el) {
        el = el || this;
        document.querySelectorAll('.review-tab').forEach(t => t.classList.remove('active'));
        el.classList.add('active');
        currentType = el.dataset.type;
        loadList();
    }

    async function loadList() {
        const cfg = COLUMNS[currentType];
        document.getElementById('headRow').innerHTML = cfg.head.map(h => `<th>${h}</th>`).join('') + '<th>状态</th><th>审核备注</th><th>操作</th>';
        const st = document.getElementById('statusFilter').value;
        const res = await api('/api/admin/reviews/' + currentType + (st ? '?status=' + encodeURIComponent(st) : ''));
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        const colspan = cfg.head.length + 3;
        tbody.innerHTML = res.data.length ? res.data.map(a => {
            let ops;
            if (a.status === '待审核') {
                ops = `<button class="btn btn-sm btn-success" data-action="review" data-arg='[${a.id}, "approve"]'>通过</button>
                       <button class="btn btn-sm btn-danger" data-action="review" data-arg='[${a.id}, "reject"]'>拒绝</button>`;
            } else {
                ops = `<button class="btn btn-sm btn-warning" data-action="revoke" data-arg='[${a.id}, ${jsAttr(a.status)}]'>撤销</button>`;
            }
            return `
            <tr>${cfg.row(a)}
                <td>${statusTag(a.status)}</td>
                <td style="font-size:12.5px;color:#666;">${esc(a.review_remark || '-')}</td>
                <td><div class="table-actions">${ops}</div></td>
            </tr>`;
        }).join('') : `<tr><td colspan="${colspan}" class="text-center" style="color:#999">暂无申请</td></tr>`;
    }

    // 撤销：已通过/已拒绝 → 待审核，并回滚已产生的业务副作用
    async function revoke(id, status) {
        let tip = `确定撤销该申请的「${status}」结果，退回待审核？`;
        if (status === '已通过') {
            tip += ' 撤销已通过的申请会同时回滚它产生的业务变更（学籍状态还原、撤销自动选课、清除学分认定）。';
        }
        if (!(await confirmDialog(tip, { title: '撤销审核', okText: '确认撤销' }))) return;

        const d = await formDialog('撤销原因', [
            { key: 'remark', label: '撤销原因', placeholder: '选填，将记录到操作日志' },
        ]);
        if (!d.ok) return;

        const res = await api(`/api/admin/reviews/${currentType}/${id}`, {
            method: 'POST',
            body: JSON.stringify({ action: 'revoke', remark: d.values.remark || '' })
        });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadList(); }
    }

    async function review(id, action) {
        if (action === 'approve') {
            if (!(await confirmDialog('确认通过该申请？', { title: '审核确认', danger: false, okText: '通过' }))) return;
        }
        let remark = '';
        if (action === 'reject') {
            const d = await formDialog('拒绝申请', [
                { key: 'remark', label: '拒绝理由', placeholder: '选填' },
            ]);
            if (!d.ok) return;
            remark = d.values.remark || '';
        }
        const res = await api(`/api/admin/reviews/${currentType}/${id}`, {
            method: 'POST', body: JSON.stringify({ action, remark })
        });
        if (res) { toast(res.message, res.success ? 'success' : 'error'); if (res.success) loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();