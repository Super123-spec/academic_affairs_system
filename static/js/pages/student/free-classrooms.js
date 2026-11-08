async function loadRooms() {
        const wd = document.getElementById('weekdaySel').value;
        const sec = document.getElementById('sectionSel').value;
        const res = await api(`/api/student/free-classrooms?weekday=${wd}&section=${sec}`);
        const tbody = document.getElementById('roomBody');
        if (!res || !res.success) return;
        if (!res.data.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center" style="color:#999">该时段没有空闲教室</td></tr>';
            return;
        }
        tbody.innerHTML = res.data.map(r => `
            <tr><td>${esc(r.building)}</td><td>${esc(r.room)}</td><td>${r.capacity}人</td>
            <td><span class="tag tag-success">空闲</span></td></tr>`).join('');
    }
    (async function () {
        await initLayout('信息查询');
        loadRooms();
    })();