async function loadSchedule() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/teacher/schedule?semester=' + encodeURIComponent(semester));
        if (!res || !res.success) return;
        const box = document.getElementById('scheduleBox');
        if (!res.data.length) { box.innerHTML = '<div class="empty-state">该学期暂无授课安排</div>'; return; }
        renderScheduleTable(box, res.data);
    }

    // 导出我的课表（Excel）
    function exportSchedule() {
        const semester = document.getElementById('semesterSel').value;
        if (!semester) { toast('请先选择学期', 'error'); return; }
        window.location.href = '/api/teacher/schedule/export?semester=' + encodeURIComponent(semester);
    }
    (async function () {
        if (!await initTeacherPage()) return;
        await loadSectionTimes();
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadSchedule();
    })();