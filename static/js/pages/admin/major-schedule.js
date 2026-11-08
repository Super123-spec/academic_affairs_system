// 复用与 teacher.js 一致的课表渲染
    const SECTION_GROUPS = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]];
    const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

    // 作息时间缓存：section -> {start, end}
    let SECTION_TIMES = {};

    async function loadSectionTimes() {
        if (Object.keys(SECTION_TIMES).length) return SECTION_TIMES;
        const res = await api('/api/common/section-times');
        if (res && res.success) {
            res.data.forEach(r => { SECTION_TIMES[r.section] = { start: r.start_time, end: r.end_time }; });
        }
        return SECTION_TIMES;
    }

    function sectionRangeText(startSec, endSec) {
        const a = SECTION_TIMES[startSec];
        const b = SECTION_TIMES[endSec] || a;
        return a && b ? `${a.start}-${b.end}` : '';
    }

    function renderScheduleTable(container, data) {
        const grid = {};
        (data || []).forEach(item => {
            const key = `${item.weekday}-${item.start_section}`;
            (grid[key] = grid[key] || []).push(item);
        });
        let html = '<table class="schedule-table"><thead><tr><th class="section-col">节次</th>';
        WEEKDAY_NAMES.forEach(d => html += `<th>${d}</th>`);
        html += '</tr></thead><tbody>';
        SECTION_GROUPS.forEach(([start, end], gi) => {
            const rangeText = sectionRangeText(start, end);
            html += `<tr><td class="section-col">第${gi + 1}大节<br><span style="font-weight:400;color:#999">${start}-${end}节</span>`
                  + (rangeText ? `<br><span style="font-weight:400;color:#1f6feb;font-size:11.5px">${rangeText}</span>` : '')
                  + `</td>`;
            for (let wd = 1; wd <= 7; wd++) {
                const items = grid[`${wd}-${start}`] || [];
                html += '<td>' + items.map(it => {
                    const wt = it.week_type && it.week_type !== '全周'
                        ? `<span class="tag ${it.week_type === '单周' ? 'tag-warning' : 'tag-primary'}" style="margin-left:4px;">${esc(it.week_type)}</span>`
                        : '';
                    const t = sectionRangeText(it.start_section, it.end_section);
                    return `
                    <div class="schedule-cell">
                        <div class="sc-name">${esc(it.course_name)}${wt}</div>
                        ${t ? `<div class="sc-info" style="color:#1f6feb;font-weight:600;">${t}</div>` : ''}
                        <div class="sc-info">${esc(it.teacher_name || '待定')} · ${esc(it.weeks || '')}周</div>
                        <div class="sc-info">${it.building ? esc(it.building + ' ' + (it.room || '')) : ''}</div>
                    </div>`;
                }).join('') + '</td>';
            }
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    }

    async function loadSchedule() {
        const mid = document.getElementById('majorSel').value;
        const sem = document.getElementById('semesterSel').value;
        if (!mid) return;
        const res = await api(`/api/admin/major-schedule?major_id=${mid}&semester=${encodeURIComponent(sem)}`);
        const box = document.getElementById('scheduleBox');
        if (!res || !res.success) { if (res) toast(res.message, 'error'); return; }

        // 专业信息
        const majorName = document.getElementById('majorSel').selectedOptions[0].text;
        let info = `<strong>${esc(majorName)}</strong>　学期：${esc(sem)}`;
        if (res.classes && res.classes.length) {
            info += '　班级：' + res.classes.map(c => `${esc(c.name)}（${c.student_count}人）`).join('、');
        }
        document.getElementById('majorInfo').innerHTML = info;

        if (!res.data || !res.data.length) {
            box.innerHTML = '<div class="empty-state">该专业在当前学期暂无课程排课</div>';
            return;
        }
        renderScheduleTable(box, res.data);
    }

    // 导出专业课表（Excel）
    function exportSchedule() {
        const mid = document.getElementById('majorSel').value;
        const sem = document.getElementById('semesterSel').value;
        if (!mid) { toast('请先选择专业', 'error'); return; }
        window.location.href = `/api/admin/major-schedule/export?major_id=${mid}&semester=${encodeURIComponent(sem)}`;
    }

    (async function () {
        if (!await initAdminPage()) return;
        await loadSectionTimes();
        const meta = await loadMeta();
        document.getElementById('majorSel').innerHTML = '<option value="">请选择专业</option>' +
            meta.majors.map(m => `<option value="${m.id}">${esc(m.college_name)} - ${esc(m.name)}</option>`).join('');
        document.getElementById('semesterSel').innerHTML =
            meta.semesters.map(s => `<option value="${esc(s)}" ${s === meta.current_semester ? 'selected' : ''}>${esc(s)}</option>`).join('');
    })();