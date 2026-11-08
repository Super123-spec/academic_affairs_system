async function loadSchedule() {
        const semester = document.getElementById('semesterSel').value;
        const res = await api('/api/student/class-schedule?semester=' + encodeURIComponent(semester));
        if (!res || !res.success) {
            if (res) toast(res.message, 'error');
            return;
        }
        document.getElementById('className').textContent = res.class_name || '--';
        const box = document.getElementById('scheduleBox');
        if (!res.data.length) {
            box.innerHTML = '<div class="empty-state">该学期暂无班级课程安排</div>';
            return;
        }
        renderScheduleTable(box, res.data);
    }

    // 导出班级课表（Excel）
    function exportSchedule() {
        const semester = document.getElementById('semesterSel').value;
        window.location.href = '/api/student/class-schedule/export?semester=' + encodeURIComponent(semester);
    }
    (async function () {
        await initLayout('信息查询');
        await loadSectionTimes();
        await fillSemesterSelect(document.getElementById('semesterSel'));
        loadSchedule();
    })();