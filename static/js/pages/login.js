// ---------- 图形验证码 ----------
        let captchaToken = '';

        async function refreshCaptcha() {
            try {
                const resp = await fetch('/api/auth/captcha');
                const data = await resp.json();
                if (data.success) {
                    captchaToken = data.token;
                    document.getElementById('captchaImg').src = data.image;
                    document.getElementById('captchaCode').value = '';
                }
            } catch (err) {
                console.error('验证码加载失败:', err);
            }
        }
        document.getElementById('captchaImg').addEventListener('click', refreshCaptcha);
        refreshCaptcha();

        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();
            const userType = document.querySelector('input[name="userType"]:checked').value;
            const captchaCode = document.getElementById('captchaCode').value.trim();

            const errorDiv = document.getElementById('errorMsg');
            errorDiv.classList.remove('show');
            errorDiv.textContent = '';

            if (!username || !password) {
                errorDiv.textContent = '请输入用户名和密码';
                errorDiv.classList.add('show');
                return;
            }
            if (!captchaCode) {
                errorDiv.textContent = '请输入验证码';
                errorDiv.classList.add('show');
                return;
            }

            try {
                // 登录接口也校验 CSRF 令牌（与 Cookie 双提交），防止登录 CSRF
                const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
                const csrfToken = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
                    body: JSON.stringify({ username, password, user_type: userType,
                                           captcha_token: captchaToken, captcha_code: captchaCode })
                });
                const data = await response.json();

                if (data.success) {
                    // 首次登录 / 管理员重置后，必须先修改密码。
                    // 注意：学生改密表单在 profile-edit.html（不是 profile.html），
                    // 管理员端没有改密表单，不要跳不存在的 /admin/profile.html。
                    if (data.must_change_pwd) {
                        const mustChangeUrl = {
                            student: '/student/profile-edit.html?must_change=1',
                            teacher: '/teacher/profile.html?must_change=1',
                            admin: '/admin/index.html'
                        };
                        window.location.href = mustChangeUrl[data.user.user_type] || '/';
                        return;
                    }
                    if (data.user.user_type === 'student') {
                        window.location.href = '/student/index.html';
                    } else if (data.user.user_type === 'teacher') {
                        window.location.href = '/teacher/index.html';
                    } else {
                        window.location.href = '/admin/index.html';
                    }
                } else {
                    errorDiv.textContent = data.message || '登录失败，请重试';
                    errorDiv.classList.add('show');
                    // 验证码是一次性的：无论哪种失败都换一张新图
                    refreshCaptcha();
                }
            } catch (err) {
                errorDiv.textContent = '网络错误，请检查服务器是否运行';
                errorDiv.classList.add('show');
                console.error('登录请求异常:', err);
            }
        });