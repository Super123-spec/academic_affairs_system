// 大节分组：用于显示说明和休息时间
    const GROUPS = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]];

    function groupLabel(sec) {
        for (let i = 0; i < GROUPS.length; i++) {
            if (GROUPS[i].includes(sec)) return `第${i + 1}大节`;
        }
        return '';
    }

    function toMinutes(t) {
        if (!t || !/^\d{2}:\d{2}$/.test(t)) return null;
        const [h, m] = t.split(':').map(Number);
        return h * 60 + m;
    }

    // 计算相邻两节之间的休息分钟数（用于"说明"列提示）
    function restText(list, idx) {
        if (idx === 0) return '';
        const prevEnd = toMinutes(list[idx - 1].end_time);
        const curStart = toMinutes(list[idx].start_time);
        if (prevEnd === null || curStart === null) return '';
        const gap = curStart - prevEnd;
        if (gap < 0) return '<span style="color:#d93025;">与上一节时间重叠</span>';
        if (gap === 0) return '<span style="color:#d93025;">与上一节无间隔</span>';
        return `距上一节休息 ${gap} 分钟`;
    }

    let CURRENT = [];

    async function loadList() {
        const res = await api('/api/admin/section-times');
        const tbody = document.getElementById('listBody');
        if (!res || !res.success) return;
        CURRENT = res.data || [];
        tbody.innerHTML = CURRENT.length ? CURRENT.map((r, i) => `
            <tr>
                <td><strong>第 ${r.section} 节</strong><br><span style="color:#999;font-size:12px;">${groupLabel(r.section)}</span></td>
                <td><input type="time" data-sec="${r.section}" data-field="start_time" value="${esc(r.start_time)}"
                        style="padding:6px 8px;border:1px solid #d1d5db;border-radius:4px;font-size:14px;width:140px;"></td>
                <td><input type="time" data-sec="${r.section}" data-field="end_time" value="${esc(r.end_time)}"
                        style="padding:6px 8px;border:1px solid #d1d5db;border-radius:4px;font-size:14px;width:140px;"></td>
                <td style="color:#888;font-size:12.5px;" id="rest-${r.section}">${restText(CURRENT, i)}</td>
            </tr>`).join('') : '<tr><td colspan="4" class="text-center" style="color:#999">暂无作息数据</td></tr>';
        bindRestUpdate();
    }

    // 输入变化时实时重算休息提示
    function bindRestUpdate() {
        document.querySelectorAll('#listBody input[type=time]').forEach(inp => {
            inp.addEventListener('change', recomputeRests);
        });
    }

    function collect() {
        const map = {};
        document.querySelectorAll('#listBody input[type=time]').forEach(inp => {
            const sec = parseInt(inp.dataset.sec);
            map[sec] = map[sec] || {};
            map[sec][inp.dataset.field] = inp.value;
        });
        return Object.keys(map).sort((a, b) => a - b).map(sec => ({
            section: parseInt(sec),
            start_time: map[sec].start_time || '',
            end_time: map[sec].end_time || '',
        }));
    }

    function recomputeRests() {
        const list = collect();
        list.forEach((r, i) => {
            const el = document.getElementById('rest-' + r.section);
            if (el) el.innerHTML = restText(list, i);
        });
    }

    async function saveAll() {
        const items = collect();
        for (const it of items) {
            if (!it.start_time || !it.end_time) {
                toast(`第 ${it.section} 节时间未填写完整`, 'error');
                return;
            }
            if (it.start_time >= it.end_time) {
                toast(`第 ${it.section} 节结束时间须晚于开始时间`, 'error');
                return;
            }
        }
        const r = await api('/api/admin/section-times', { method: 'PUT', body: JSON.stringify({ items }) });
        if (r) { toast(r.message, r.success ? 'success' : 'error'); if (r.success) loadList(); }
    }

    (async function () {
        if (!await initAdminPage()) return;
        loadList();
    })();