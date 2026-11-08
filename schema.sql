-- 教务管理系统数据库建表SQL（edu_admin）

-- 管理员表
CREATE TABLE IF NOT EXISTS admin (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    avatar VARCHAR(255) COMMENT '头像文件路径',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active TINYINT(1) DEFAULT 1,
    must_change_pwd TINYINT(1) DEFAULT 0 COMMENT '首次登录需强制修改密码',
    is_super TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否超级管理员（可看审计日志等敏感操作）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学院表
CREATE TABLE IF NOT EXISTS college (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(20) UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 专业表
CREATE TABLE IF NOT EXISTS major (
    id INT PRIMARY KEY AUTO_INCREMENT,
    college_id INT NOT NULL,
    code VARCHAR(20) UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (college_id) REFERENCES college(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 班级表
CREATE TABLE IF NOT EXISTS class (
    id INT PRIMARY KEY AUTO_INCREMENT,
    major_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    grade_year INT NOT NULL COMMENT '入学年份',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (major_id) REFERENCES major(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生表
CREATE TABLE IF NOT EXISTS student (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '学号',
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(50) NOT NULL,
    gender VARCHAR(10) DEFAULT '男',
    class_id INT,
    id_card VARCHAR(255) COMMENT '身份证号（AES-GCM 加密存储）',
    phone VARCHAR(20),
    email VARCHAR(100),
    birth_date DATE,
    political_status VARCHAR(20) DEFAULT '群众',
    native_place VARCHAR(100),
    address VARCHAR(255),
    enrollment_date DATE COMMENT '入学日期',
    status VARCHAR(20) DEFAULT '在读' COMMENT '在读/休学/复学/退学/毕业',
    diversion_status VARCHAR(20) DEFAULT '未确认' COMMENT '分流专业确认状态',
    diversion_major_id INT COMMENT '分流后专业',
    is_frozen TINYINT(1) DEFAULT 0,
    must_change_pwd TINYINT(1) DEFAULT 0 COMMENT '首次登录需强制修改密码',
    avatar VARCHAR(255) COMMENT '头像文件路径',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES class(id) ON DELETE SET NULL,
    FOREIGN KEY (diversion_major_id) REFERENCES major(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教师表
CREATE TABLE IF NOT EXISTS teacher (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '工号',
    password_hash VARCHAR(255) NOT NULL,
    real_name VARCHAR(50) NOT NULL,
    gender VARCHAR(10) DEFAULT '男',
    college_id INT,
    title VARCHAR(50) COMMENT '职称',
    phone VARCHAR(20),
    email VARCHAR(100),
    avatar VARCHAR(255) COMMENT '头像文件路径',
    is_active TINYINT(1) DEFAULT 1,
    must_change_pwd TINYINT(1) DEFAULT 0 COMMENT '首次登录需强制修改密码',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (college_id) REFERENCES college(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 课程表
CREATE TABLE IF NOT EXISTS course (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE COMMENT '课程号',
    name VARCHAR(200) NOT NULL,
    credit DECIMAL(4,1) DEFAULT 0 COMMENT '学分',
    hours INT DEFAULT 0 COMMENT '学时',
    type VARCHAR(20) DEFAULT '必修' COMMENT '必修/选修/通识',
    college_id INT COMMENT '开课学院',
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (college_id) REFERENCES college(id) ON DELETE SET NULL,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 开课（教学班）表
CREATE TABLE IF NOT EXISTS course_offering (
    id INT PRIMARY KEY AUTO_INCREMENT,
    course_id INT NOT NULL,
    teacher_id INT,
    semester VARCHAR(20) NOT NULL COMMENT '学期 如 2025-2026-1',
    max_count INT DEFAULT 60,
    selected_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT '开放' COMMENT '开放/关闭',
    usual_ratio INT DEFAULT 40 COMMENT '平时成绩占比%',
    exam_ratio INT DEFAULT 60 COMMENT '考试成绩占比%',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES teacher(id) ON DELETE SET NULL,
    INDEX idx_semester (semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教室表
CREATE TABLE IF NOT EXISTS classroom (
    id INT PRIMARY KEY AUTO_INCREMENT,
    building VARCHAR(50) NOT NULL COMMENT '教学楼',
    room VARCHAR(50) NOT NULL COMMENT '教室号',
    capacity INT DEFAULT 60,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_room (building, room)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 作息时间表（每节课的开始/结束时间，供课表显示）
CREATE TABLE IF NOT EXISTS section_time (
    id INT PRIMARY KEY AUTO_INCREMENT,
    section INT NOT NULL UNIQUE COMMENT '节次 1-10',
    start_time VARCHAR(8) NOT NULL COMMENT '开始时间 HH:MM',
    end_time VARCHAR(8) NOT NULL COMMENT '结束时间 HH:MM'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作息时间表';

-- 排课表
CREATE TABLE IF NOT EXISTS course_schedule (
    id INT PRIMARY KEY AUTO_INCREMENT,
    offering_id INT NOT NULL,
    weekday INT NOT NULL COMMENT '星期几 1-7',
    start_section INT NOT NULL COMMENT '开始节次',
    end_section INT NOT NULL COMMENT '结束节次',
    weeks VARCHAR(50) DEFAULT '1-16' COMMENT '上课周次',
    week_type VARCHAR(10) DEFAULT '全周' COMMENT '全周/单周/双周',
    classroom_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE,
    FOREIGN KEY (classroom_id) REFERENCES classroom(id) ON DELETE SET NULL,
    INDEX idx_offering (offering_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 开课-班级关联表（教学班指定授课班级，支持合班）
CREATE TABLE IF NOT EXISTS offering_class (
    id INT PRIMARY KEY AUTO_INCREMENT,
    offering_id INT NOT NULL,
    class_id INT NOT NULL,
    UNIQUE KEY uk_offering_class (offering_id, class_id),
    FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES class(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 选课记录表
CREATE TABLE IF NOT EXISTS enrollment (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    offering_id INT NOT NULL,
    select_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT '已选' COMMENT '已选/退选',
    usual_score DECIMAL(5,1) COMMENT '平时成绩',
    exam_score DECIMAL(5,1) COMMENT '考试成绩',
    total_score DECIMAL(5,1) COMMENT '总评成绩',
    grade_point DECIMAL(3,1) COMMENT '绩点',
    is_retake TINYINT(1) DEFAULT 0 COMMENT '是否重修',
    UNIQUE KEY uk_student_offering (student_id, offering_id),
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
    FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE,
    INDEX idx_student (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 考试安排表
CREATE TABLE IF NOT EXISTS exam (
    id INT PRIMARY KEY AUTO_INCREMENT,
    offering_id INT NOT NULL,
    exam_date DATE NOT NULL,
    start_time VARCHAR(10),
    end_time VARCHAR(10),
    classroom_id INT,
    exam_type VARCHAR(20) DEFAULT '期末' COMMENT '期中/期末/补考',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE,
    FOREIGN KEY (classroom_id) REFERENCES classroom(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教学评价表（学生评价/过程评价）
CREATE TABLE IF NOT EXISTS evaluation (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    offering_id INT NOT NULL,
    type VARCHAR(20) DEFAULT 'final' COMMENT 'final学生评价/process过程评价',
    score_teaching INT COMMENT '教学态度',
    score_content INT COMMENT '教学内容',
    score_method INT COMMENT '教学方法',
    score_effect INT COMMENT '教学效果',
    total_score DECIMAL(4,1) COMMENT '总分',
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_eval (student_id, offering_id, type),
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
    FOREIGN KEY (offering_id) REFERENCES course_offering(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 重修报名表
CREATE TABLE IF NOT EXISTS retake_apply (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    semester VARCHAR(20) NOT NULL,
    reason VARCHAR(255),
    status VARCHAR(20) DEFAULT '待审核' COMMENT '待审核/已通过/已拒绝',
    review_remark VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学籍异动申请表
CREATE TABLE IF NOT EXISTS status_change_apply (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    change_type VARCHAR(20) NOT NULL COMMENT '休学/复学/转专业/退学',
    reason TEXT,
    apply_date DATE,
    status VARCHAR(20) DEFAULT '待审核' COMMENT '待审核/已通过/已拒绝',
    review_remark VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教学项目表
CREATE TABLE IF NOT EXISTS project (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(50) DEFAULT '学科竞赛' COMMENT '学科竞赛/创新创业/科研项目/交换项目',
    semester VARCHAR(20),
    max_count INT DEFAULT 30,
    apply_count INT DEFAULT 0,
    start_date DATE,
    end_date DATE,
    description TEXT,
    is_open TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教学项目报名表
CREATE TABLE IF NOT EXISTS project_apply (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    student_id INT NOT NULL,
    reason VARCHAR(255),
    status VARCHAR(20) DEFAULT '待审核' COMMENT '待审核/已通过/已拒绝',
    review_remark VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    UNIQUE KEY uk_project_student (project_id, student_id),
    FOREIGN KEY (project_id) REFERENCES project(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 校外课程学分替代申请表
CREATE TABLE IF NOT EXISTS credit_substitute_apply (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    external_school VARCHAR(200) NOT NULL COMMENT '校外学校/机构',
    external_course VARCHAR(200) NOT NULL COMMENT '校外课程',
    external_credit DECIMAL(4,1) COMMENT '校外学分',
    substitute_course_id INT COMMENT '替代的本校课程',
    proof_url VARCHAR(500) COMMENT '证明材料',
    reason VARCHAR(255),
    status VARCHAR(20) DEFAULT '待审核',
    review_remark VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
    FOREIGN KEY (substitute_course_id) REFERENCES course(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创新创业学分表
CREATE TABLE IF NOT EXISTS innovation_credit (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    item_name VARCHAR(200) NOT NULL COMMENT '项目名称',
    credit DECIMAL(4,1) NOT NULL,
    category VARCHAR(50) DEFAULT '竞赛获奖',
    obtained_date DATE,
    is_confirmed TINYINT(1) DEFAULT 0 COMMENT '学生确认',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 报到注册表
CREATE TABLE IF NOT EXISTS registration (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    semester VARCHAR(20) NOT NULL,
    register_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT '已注册',
    UNIQUE KEY uk_reg (student_id, semester),
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 学生证书表
CREATE TABLE IF NOT EXISTS certificate (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    cert_no VARCHAR(100),
    issue_date DATE,
    issuer VARCHAR(200) COMMENT '颁发机构',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 教学执行计划表
CREATE TABLE IF NOT EXISTS teaching_plan (
    id INT PRIMARY KEY AUTO_INCREMENT,
    major_id INT NOT NULL,
    course_id INT NOT NULL,
    semester_no INT NOT NULL COMMENT '建议修读学期 1-8',
    category VARCHAR(20) DEFAULT '必修' COMMENT '必修/选修/实践',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (major_id) REFERENCES major(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE,
    UNIQUE KEY uk_plan (major_id, course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 公告表
CREATE TABLE IF NOT EXISTS announcement (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    is_top TINYINT(1) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 操作日志表
CREATE TABLE IF NOT EXISTS operation_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT,
    action VARCHAR(50) NOT NULL,
    target_table VARCHAR(50),
    target_id INT,
    detail TEXT,
    ip_address VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admin(id) ON DELETE SET NULL,
    INDEX idx_admin_id (admin_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 登录验证码表（防爆破：一次性使用，5 分钟过期，答案存库以支持多 worker 部署）
CREATE TABLE IF NOT EXISTS login_captcha (
    token VARCHAR(32) PRIMARY KEY COMMENT '一次性令牌，登录时随验证码字符一起提交',
    code VARCHAR(8) NOT NULL COMMENT '验证码字符',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录图形验证码';

-- 登录限流表（防暴力破解，跨进程共享）
-- 存库而非进程内存：gunicorn 多 worker 各自的内存字典会把阈值放大 N 倍，且重启清零。
-- 主键行锁保证并发下的原子计数；封禁期到期后由 UPSERT 自动恢复计数。
CREATE TABLE IF NOT EXISTS login_throttle (
    throttle_key VARCHAR(128) PRIMARY KEY COMMENT 'ip:<ip> 或 acct:<user_type>:<username>',
    fail_count INT NOT NULL DEFAULT 0 COMMENT '连续失败次数',
    blocked_until DATETIME DEFAULT NULL COMMENT '封禁截止时间（NULL=未封禁）',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_blocked (blocked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录限流';
