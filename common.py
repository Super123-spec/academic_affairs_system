# -*- coding: utf-8 -*-
"""公共数据蓝图：元数据、公告"""
from flask import Blueprint, jsonify

from core import (CURRENT_SEMESTER, query_all, fmt_rows, login_required)

common_bp = Blueprint('common', __name__)


@common_bp.route('/api/common/meta')
@login_required
def get_meta():
    """下拉框元数据：学院/专业/班级/学期"""
    colleges = query_all("SELECT id, name FROM college ORDER BY id")
    majors = query_all("SELECT m.id, m.name, m.college_id, c.name AS college_name FROM major m JOIN college c ON m.college_id=c.id ORDER BY m.id")
    classes = query_all("""SELECT cl.id, cl.name, cl.grade_year, cl.major_id, m.name AS major_name
                           FROM class cl JOIN major m ON cl.major_id=m.id ORDER BY cl.id""")
    semesters = [r['semester'] for r in query_all("SELECT DISTINCT semester FROM course_offering ORDER BY semester DESC")]
    return jsonify({'success': True, 'data': {
        'colleges': colleges, 'majors': majors, 'classes': classes,
        'semesters': semesters, 'current_semester': CURRENT_SEMESTER
    }})


@common_bp.route('/api/common/announcements')
@login_required
def get_announcements():
    rows = query_all("SELECT id, title, content, is_top, created_at FROM announcement WHERE is_active=1 ORDER BY is_top DESC, created_at DESC")
    return jsonify({'success': True, 'data': fmt_rows(rows)})


@common_bp.route('/api/common/section-times')
@login_required
def get_section_times():
    """作息时间：每节课的开始/结束时间（供各端课表显示）"""
    rows = query_all("SELECT section, start_time, end_time FROM section_time ORDER BY section")
    return jsonify({'success': True, 'data': fmt_rows(rows)})
