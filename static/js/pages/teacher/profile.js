(async function () {
        // 强制改密跳转（?must_change=1）时在页面顶部显示提示条
        const isMustChange = new URLSearchParams(location.search).get('must_change') === '1';
        if (isMustChange) document.getElementById('mustChangeTip').style.display = 'block';

        if (!await initTeacherPage()) return;
        const res = await api('/api/teacher/profile');
        if (res && res.success) {
            const t = res.data;
            document.getElementById('profileBox').innerHTML = '<div class="detail-grid">' + [
                ['工号', t.username], ['姓名', t.real_name], ['性别', t.gender], ['学院', t.college_name],
                ['职称', t.title], ['联系电话', t.phone], ['电子邮箱', t.email]
            ].map(([k, v]) => `<div class="detail-row"><div class="detail-label">${k}</div><div class="detail-value">${esc(v) || '-'}</div></div>`).join('') + '</div>';
            if (t.avatar) {
                document.getElementById('avatarPreview').innerHTML = `<img src="${esc(t.avatar)}?t=${Date.now()}" alt="头像" title="双击放大" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" data-dbl="viewAvatar\" data-arg='[${jsAttr(t.avatar)}]'>`;
            } else {
                document.getElementById('avatarPreviewText').textContent = (t.real_name || '').slice(-2) || '头像';
            }
        }
        document.getElementById('pwForm').addEventListener('submit', async e => {
            e.preventDefault();
            const r = await api('/api/auth/change-password', {
                method: 'POST',
                body: JSON.stringify({ old_password: oldPw.value, new_password: newPw.value })
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