(async function () {
        await initLayout('首页');
        bindAvatarClick(document.getElementById('avatarBox'));

        const profile = await api('/api/student/profile');
        if (profile && profile.success) {
            const s = profile.data;
            document.getElementById('stuName').textContent = s.real_name;
            const avatarBox = document.getElementById('avatarBox');
            if (s.avatar) {
                avatarBox.innerHTML = `<img src="${esc(s.avatar)}" alt="头像" title="双击放大" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar\" data-arg='[${jsAttr(s.avatar)}]'>`;
            } else {
                avatarBox.textContent = s.real_name.slice(-2);
            }
            document.getElementById('stuClass').textContent =
                [s.college_name, s.class_name].filter(Boolean).join(' ') || '未分配班级';
        }

        const ann = await api('/api/common/announcements');
        const box = document.getElementById('announcements');
        if (ann && ann.success && ann.data.length) {
            box.innerHTML = ann.data.slice(0, 5).map(a => `
                <div class="announcement-item">
                    <div class="announcement-title">${a.is_top ? '<span class="tag tag-danger">置顶</span> ' : ''}${esc(a.title)}</div>
                    <div class="announcement-meta">${esc(a.created_at)}</div>
                    <div style="margin-top:6px;color:#555;font-size:13px;">${esc(a.content)}</div>
                </div>`).join('');
        } else {
            box.innerHTML = '<div class="empty-state">暂无公告</div>';
        }
    })();