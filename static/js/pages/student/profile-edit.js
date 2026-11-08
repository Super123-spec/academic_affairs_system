(async function () {
        // 强制改密跳转（?must_change=1）时在页面顶部显示提示条
        const isMustChange = new URLSearchParams(location.search).get('must_change') === '1';
        if (isMustChange) document.getElementById('mustChangeTip').style.display = 'block';

        await initLayout('信息维护');
        const res = await api('/api/student/profile');
        if (!res || !res.success) return;
        const s = res.data;
        document.getElementById('fixedInfo').innerHTML = '<div class="detail-grid">' + [
            ['学号', s.username], ['姓名', s.real_name], ['学院', s.college_name], ['班级', s.class_name]
        ].map(([k, v]) => `<div class="detail-row"><div class="detail-label">${k}</div><div class="detail-value">${esc(v) || '-'}</div></div>`).join('') + '</div>';

        // 头像预览
        if (s.avatar) {
            document.getElementById('avatarPreview').innerHTML = `<img src="${esc(s.avatar)}?t=${Date.now()}" alt="头像" title="双击放大" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar\" data-arg='[${jsAttr(s.avatar)}]'>`;
        } else {
            document.getElementById('avatarPreviewText').textContent = (s.real_name || '').slice(-2) || '头像';
        }

        document.getElementById('phone').value = s.phone || '';
        document.getElementById('email').value = s.email || '';
        document.getElementById('political_status').value = s.political_status || '群众';
        document.getElementById('native_place').value = s.native_place || '';
        document.getElementById('address').value = s.address || '';

        document.getElementById('profileForm').addEventListener('submit', async e => {
            e.preventDefault();
            const r = await api('/api/student/profile', {
                method: 'PUT',
                body: JSON.stringify({
                    phone: document.getElementById('phone').value.trim(),
                    email: document.getElementById('email').value.trim(),
                    political_status: document.getElementById('political_status').value,
                    native_place: document.getElementById('native_place').value.trim(),
                    address: document.getElementById('address').value.trim(),
                })
            });
            if (r) toast(r.message, r.success ? 'success' : 'error');
        });

        document.getElementById('pwForm').addEventListener('submit', async e => {
            e.preventDefault();
            const r = await api('/api/auth/change-password', {
                method: 'POST',
                body: JSON.stringify({
                    old_password: document.getElementById('oldPw').value,
                    new_password: document.getElementById('newPw').value
                })
            });
            if (r) {
                toast(r.message, r.success ? 'success' : 'error');
                if (r.success) {
                    e.target.reset();
                    // 改密成功：隐藏强制改密提示，并从 URL 去掉 must_change 参数（避免刷新后重复提示）
                    document.getElementById('mustChangeTip').style.display = 'none';
                    const u = new URL(location.href);
                    if (u.searchParams.has('must_change')) {
                        u.searchParams.delete('must_change');
                        history.replaceState(null, '', u.pathname + u.search);
                    }
                }
            }
        });
    })();