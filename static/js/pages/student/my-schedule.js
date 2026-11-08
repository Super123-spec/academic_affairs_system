async function loadSchedule() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/student/schedule?semester=' + encodeURIComponent(semester));
        if (!res || !res.success) return;
        const box = document.getElementById('scheduleBox');
        if (!res.data.length) {
            box.innerHTML = '<div class="empty-state">该学期暂无课程安排</div>';
            return;
        }
        renderScheduleTable(box, res.data);
    }

    // 导出个人课表（Excel）
    function exportSchedule() {
        const semester = document.getElementById('semesterSel').value;
        window.location.href = '/api/student/schedule/export?semester=' + encodeURIComponent(semester);
    }
    (async function () {
        await initLayout('选课');
        await loadSectionTimes();
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadSchedule();
    })();