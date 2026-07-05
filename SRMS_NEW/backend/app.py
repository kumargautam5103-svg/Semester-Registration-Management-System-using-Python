"""
SRMS - Semester Registration Management System
Flask + SQL Server (pyodbc) backend  [v8 - Fee Receipt stored in Database]

Key change from v7:
  - Fee receipts are uploaded as binary data directly into the Registrations table
    (FeeReceiptData VARBINARY(MAX), FeeReceiptMime NVARCHAR(100)).
  - FeeReceiptPath stores only the original display filename (no local file write).
  - No uploads/ folder is used or needed.
  - Coordinators fetch and view fee receipts via /coordinator/receipt/<reg_id>
    which streams binary data directly from the database.
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, send_file, abort, Response)
from flask_mail import Mail, Message
import pyodbc
import os, io, csv, secrets
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__,
            template_folder='../frontend/templates',
            static_folder='../frontend/static')
app.secret_key = 'srms_secret_key_change_in_production'

# ============================================================
# FILE UPLOAD CONFIGURATION
# No local filesystem storage — receipts go to the database.
# Only allowed extensions are validated before inserting.
# ============================================================
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB

MIME_MAP = {
    'pdf':  'application/pdf',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'png':  'image/png',
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_mime(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return MIME_MAP.get(ext, 'application/octet-stream')

# ============================================================
# EMAIL CONFIGURATION  (Flask-Mail / SMTP)
# ============================================================
app.config['MAIL_SERVER']        = 'smtp.gmail.com'
app.config['MAIL_PORT']          = 587
app.config['MAIL_USE_TLS']       = True
app.config['MAIL_USERNAME']      = 'gautam028377@gmail.com'
app.config['MAIL_PASSWORD']      = 'exfj vdop ycvt wufq'
app.config['MAIL_DEFAULT_SENDER']= ('SRMS Portal', 'gautam028377@gmail.com')

mail = Mail(app)

# ============================================================
# DATABASE CONFIGURATION
# ============================================================
DB_CONFIG = {
    'server':   r'localhost\SQLEXPRESS',
    'database': 'SRMS_DB3',
    'trusted':  True,
    'username': 'sa',
    'password': 'YourPassword123',
}

def get_db():
    if DB_CONFIG['trusted']:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"Trusted_Connection=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['username']};"
            f"PWD={DB_CONFIG['password']};"
        )
    return pyodbc.connect(conn_str)

# ============================================================
# AUTH HELPERS
# ============================================================
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ============================================================
# HELPERS
# ============================================================
def get_coord_id(cur, user_id):
    cur.execute("SELECT CoordID FROM Coordinators WHERE UserID=?", user_id)
    row = cur.fetchone()
    return row.CoordID if row else None

def get_coord_assignments(cur, coord_id):
    cur.execute("""
        SELECT ca.CourseID, c.ShortCode, c.CourseName, ca.Semester
        FROM CoordinatorAssignments ca
        JOIN Courses c ON ca.CourseID = c.CourseID
        WHERE ca.CoordID = ?
        ORDER BY c.ShortCode, ca.Semester
    """, coord_id)
    return cur.fetchall()

# ============================================================
# EMAIL HELPERS
# ============================================================
def send_registration_initiated_email(student_email, student_name, acad_year, course_name, semester):
    try:
        msg = Message(
            subject=f"[SRMS] Semester Registration Open - {acad_year}",
            recipients=[student_email]
        )
        msg.html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                    max-width:560px;margin:0 auto;background:#fff;border:1px solid #e0e0e0;
                    border-radius:10px;overflow:hidden;">
          <div style="background:#185FA5;padding:20px 24px;">
            <h2 style="color:#fff;margin:0;font-size:18px;font-weight:500;">
              SRMS - Semester Registration Portal
            </h2>
          </div>
          <div style="padding:24px;">
            <p style="font-size:15px;color:#111;margin-bottom:12px;">Dear <strong>{student_name}</strong>,</p>
            <p style="font-size:14px;color:#444;line-height:1.6;margin-bottom:16px;">
              Your coordinator has initiated the semester registration for the current academic period.
              You can now log in to the SRMS portal and submit your registration.
            </p>
            <table style="width:100%;background:#f5f8fc;border-radius:8px;padding:14px;border-collapse:collapse;margin-bottom:20px;">
              <tr>
                <td style="font-size:12px;color:#666;padding:6px 8px;">Academic Year</td>
                <td style="font-size:13px;color:#111;font-weight:500;padding:6px 8px;">{acad_year}</td>
              </tr>
              <tr>
                <td style="font-size:12px;color:#666;padding:6px 8px;">Course</td>
                <td style="font-size:13px;color:#111;font-weight:500;padding:6px 8px;">{course_name}</td>
              </tr>
              <tr>
                <td style="font-size:12px;color:#666;padding:6px 8px;">Semester</td>
                <td style="font-size:13px;color:#111;font-weight:500;padding:6px 8px;">{semester}</td>
              </tr>
            </table>
            <p style="font-size:13px;color:#444;margin-bottom:20px;">
              Please log in, select your subjects, upload your fee receipt, and submit your registration before the deadline.
            </p>
            <a href="http://localhost:5000/student/register"
               style="display:inline-block;background:#185FA5;color:#fff;padding:10px 22px;
                      border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;">
              Go to Registration Portal
            </a>
          </div>
          <div style="padding:14px 24px;background:#f5f5f5;border-top:1px solid #e0e0e0;">
            <p style="font-size:11px;color:#999;margin:0;">This is an automated message from SRMS Portal. Do not reply.</p>
          </div>
        </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"[MAIL ERROR] Failed to send to {student_email}: {e}")
        return False


def send_password_reset_email(email, full_name, reset_url):
    try:
        msg = Message(
            subject="[SRMS] Password Reset Request",
            recipients=[email]
        )
        msg.html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                    max-width:560px;margin:0 auto;background:#fff;border:1px solid #e0e0e0;
                    border-radius:10px;overflow:hidden;">
          <div style="background:#185FA5;padding:20px 24px;">
            <h2 style="color:#fff;margin:0;font-size:18px;font-weight:500;">
              SRMS - Password Reset
            </h2>
          </div>
          <div style="padding:24px;">
            <p style="font-size:15px;color:#111;margin-bottom:12px;">Dear <strong>{full_name}</strong>,</p>
            <p style="font-size:14px;color:#444;line-height:1.6;margin-bottom:20px;">
              We received a request to reset your SRMS portal password.
              Click the button below to set a new password. This link expires in <strong>30 minutes</strong>.
            </p>
            <a href="{reset_url}"
               style="display:inline-block;background:#185FA5;color:#fff;padding:10px 22px;
                      border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;">
              Reset My Password
            </a>
            <p style="font-size:12px;color:#888;margin-top:20px;">
              If you did not request this, please ignore this email. Your password will not be changed.
            </p>
          </div>
          <div style="padding:14px 24px;background:#f5f5f5;border-top:1px solid #e0e0e0;">
            <p style="font-size:11px;color:#999;margin:0;">This is an automated message from SRMS Portal. Do not reply.</p>
          </div>
        </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"[MAIL ERROR] Password reset failed for {email}: {e}")
        return False

def send_registration_decision_email(student_email, student_name, action, reg_id,
                                      course_name, short_code, semester, acad_year,
                                      subjects, remarks, coordinator_name):
    try:
        is_approved = (action == 'approved')
        status_word  = 'Approved ✅' if is_approved else 'Rejected ❌'
        header_color = '#1a7f37' if is_approved else '#c0392b'
        status_color = '#1a7f37' if is_approved else '#c0392b'
        status_bg    = '#eafbea' if is_approved else '#fbeaea'

        subjects_html = ''.join(
            f'<li style="font-size:13px;color:#333;padding:4px 0;">{s.strip()}</li>'
            for s in subjects.split(',') if s.strip()
        ) if subjects else '<li style="font-size:13px;color:#aaa;">No subjects listed</li>'

        remarks_block = (
            f'<div style="margin-top:16px;padding:12px 14px;background:#fff8e1;'
            f'border-left:3px solid #f0ad4e;border-radius:6px;">'
            f'<div style="font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.4px">Coordinator Remarks</div>'
            f'<div style="font-size:13px;color:#555;">{remarks}</div></div>'
        ) if remarks and remarks.strip() else ''

        action_message = (
            'Your semester registration has been <strong>approved</strong>. '
            'You are now officially registered for the subjects listed below.'
            if is_approved else
            'Unfortunately, your semester registration has been <strong>rejected</strong>. '
            'Please contact your coordinator for further guidance or re-submit after resolving the issue.'
        )

        msg = Message(
            subject=f"[SRMS] Registration {status_word} — {short_code} Sem {semester} ({acad_year})",
            recipients=[student_email]
        )
        msg.html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                    max-width:580px;margin:0 auto;background:#fff;
                    border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
          <div style="background:{header_color};padding:20px 24px;">
            <h2 style="color:#fff;margin:0;font-size:18px;font-weight:500;">
              SRMS — Semester Registration Portal
            </h2>
          </div>
          <div style="padding:24px;">
            <p style="font-size:15px;color:#111;margin-bottom:12px;">
              Dear <strong>{student_name}</strong>,
            </p>
            <p style="font-size:14px;color:#444;line-height:1.7;margin-bottom:20px;">
              {action_message}
            </p>
            <div style="display:inline-block;background:{status_bg};color:{status_color};
                        border:1px solid {status_color};border-radius:20px;
                        padding:6px 18px;font-size:14px;font-weight:600;margin-bottom:20px;">
              {status_word}
            </div>
            <div style="background:#f5f8fc;border-radius:8px;padding:16px;margin-bottom:16px;">
              <div style="font-size:11px;color:#888;text-transform:uppercase;
                          letter-spacing:.5px;margin-bottom:10px;">Registration Details</div>
              <table style="width:100%;border-collapse:collapse;">
                <tr>
                  <td style="font-size:12px;color:#666;padding:5px 0;">Registration ID</td>
                  <td style="font-size:13px;color:#111;font-weight:500;padding:5px 0;">#{reg_id}</td>
                </tr>
                <tr>
                  <td style="font-size:12px;color:#666;padding:5px 0;">Course</td>
                  <td style="font-size:13px;color:#111;font-weight:500;padding:5px 0;">{course_name} ({short_code})</td>
                </tr>
                <tr>
                  <td style="font-size:12px;color:#666;padding:5px 0;">Semester</td>
                  <td style="font-size:13px;color:#111;font-weight:500;padding:5px 0;">Semester {semester}</td>
                </tr>
                <tr>
                  <td style="font-size:12px;color:#666;padding:5px 0;">Academic Year</td>
                  <td style="font-size:13px;color:#111;font-weight:500;padding:5px 0;">{acad_year}</td>
                </tr>
                <tr>
                  <td style="font-size:12px;color:#666;padding:5px 0;">Reviewed By</td>
                  <td style="font-size:13px;color:#111;font-weight:500;padding:5px 0;">{coordinator_name}</td>
                </tr>
              </table>
            </div>
            <div style="background:#f9f9f9;border-radius:8px;padding:16px;margin-bottom:16px;">
              <div style="font-size:11px;color:#888;text-transform:uppercase;
                          letter-spacing:.5px;margin-bottom:8px;">Registered Subjects</div>
              <ul style="margin:0;padding-left:18px;">
                {subjects_html}
              </ul>
            </div>
            {remarks_block}
            <p style="font-size:13px;color:#666;margin-top:20px;line-height:1.6;">
              If you have any questions, please contact your coordinator or visit the SRMS portal.
            </p>
            <a href="http://localhost:5000/student/status"
               style="display:inline-block;background:#185FA5;color:#fff;padding:10px 22px;
                      border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;margin-top:12px;">
              View Registration Status
            </a>
          </div>
          <div style="padding:14px 24px;background:#f5f5f5;border-top:1px solid #e0e0e0;">
            <p style="font-size:11px;color:#999;margin:0;">
              This is an automated message from SRMS Portal. Do not reply directly to this email.
            </p>
          </div>
        </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"[MAIL ERROR] Decision email failed for {student_email}: {e}")
        return False


# ============================================================
# ROUTES
# ============================================================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                "SELECT UserID, FullName, Role, Email FROM Users "
                "WHERE Username=? AND PasswordHash=? AND IsActive=1",
                username, password)
            row = cur.fetchone()
            conn.close()
            if row:
                session.update({'user_id': row.UserID, 'full_name': row.FullName,
                                'role': row.Role, 'email': row.Email or '',
                                'username': username})
                return redirect(url_for('dashboard'))
            error = 'Invalid credentials. Please try again.'
        except Exception as e:
            error = f'Database error: {e}'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================================
# FORGOT PASSWORD
# ============================================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT UserID, FullName, Email FROM Users WHERE Email=? AND IsActive=1", email)
            user = cur.fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(minutes=30)
                cur.execute("DELETE FROM PasswordResetTokens WHERE UserID=?", user.UserID)
                cur.execute(
                    "INSERT INTO PasswordResetTokens (UserID, Token, ExpiresAt) VALUES (?,?,?)",
                    user.UserID, token, expires_at
                )
                conn.commit()
                reset_url = url_for('reset_password', token=token, _external=True)
                send_password_reset_email(user.Email, user.FullName, reset_url)
            conn.close()
        except Exception as e:
            print(f"[FORGOT PW ERROR] {e}")
        return render_template('forgot_password.html', sent=True, email=email)
    return render_template('forgot_password.html', sent=False)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    error = None
    success = False
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT prt.UserID, u.FullName, prt.ExpiresAt
            FROM PasswordResetTokens prt
            JOIN Users u ON u.UserID = prt.UserID
            WHERE prt.Token = ?
        """, token)
        row = cur.fetchone()
        if not row:
            conn.close()
            return render_template('reset_password.html', error='Invalid or expired reset link.', token=token)
        if datetime.now() > row.ExpiresAt:
            cur.execute("DELETE FROM PasswordResetTokens WHERE Token=?", token)
            conn.commit(); conn.close()
            return render_template('reset_password.html',
                                   error='This reset link has expired. Please request a new one.', token=token)
        if request.method == 'POST':
            new_password = request.form.get('password', '').strip()
            confirm      = request.form.get('confirm_password', '').strip()
            if len(new_password) < 6:
                error = 'Password must be at least 6 characters.'
            elif new_password != confirm:
                error = 'Passwords do not match.'
            else:
                cur.execute("UPDATE Users SET PasswordHash=? WHERE UserID=?", new_password, row.UserID)
                cur.execute("DELETE FROM PasswordResetTokens WHERE UserID=?", row.UserID)
                conn.commit(); conn.close()
                return render_template('reset_password.html', success=True)
        conn.close()
    except Exception as e:
        error = f'An error occurred: {e}'
    return render_template('reset_password.html', token=token, error=error, success=success)


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session.get('role')
    if role == 'student':     return redirect(url_for('student_dashboard'))
    if role == 'coordinator': return redirect(url_for('coordinator_dashboard'))
    if role == 'admin':       return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

# ============================================================
# STUDENT ROUTES
# ============================================================
@app.route('/student')
@login_required(role='student')
def student_dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT s.StudentID, s.RollNo, s.CurrentSem, s.Batch,
               c.CourseName, c.ShortCode, c.Duration
        FROM Students s JOIN Courses c ON s.CourseID=c.CourseID
        WHERE s.UserID=?
    """, session['user_id'])
    student = cur.fetchone()
    reg = None; reg_subjects = []
    if student:
        cur.execute("""
            SELECT r.RegID, r.Semester, r.AcadYear, r.Status,
                   r.SubmittedAt, r.Remarks, r.FeeReceiptPath
            FROM Registrations r WHERE r.StudentID=?
            ORDER BY r.SubmittedAt DESC
        """, student.StudentID)
        reg = cur.fetchone()
        if reg:
            cur.execute("""
                SELECT sub.SubjectName FROM RegistrationSubjects rs
                JOIN Subjects sub ON rs.SubjectID=sub.SubjectID WHERE rs.RegID=?
            """, reg.RegID)
            reg_subjects = [r.SubjectName for r in cur.fetchall()]
    conn.close()
    return render_template('student_dashboard.html',
                           student=student, reg=reg, reg_subjects=reg_subjects)

@app.route('/student/register', methods=['GET', 'POST'])
@login_required(role='student')
def student_register():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT s.StudentID, s.RollNo, s.CurrentSem, s.CourseID,
               c.CourseName, c.ShortCode, c.Duration
        FROM Students s JOIN Courses c ON s.CourseID=c.CourseID
        WHERE s.UserID=?
    """, session['user_id'])
    student = cur.fetchone()
    all_semesters = []
    if student:
        try:
            dur_str = student.Duration or ''
            sem_count = 0
            for part in dur_str.replace('/', ',').split(','):
                part = part.strip()
                if 'semester' in part.lower():
                    sem_count = int(''.join(filter(str.isdigit, part)))
                    break
            all_semesters = list(range(1, max(sem_count, student.CurrentSem) + 1))
        except Exception:
            all_semesters = list(range(1, (student.CurrentSem or 1) + 1))
    cur.execute("SELECT TOP 1 PeriodID, AcadYear, IsOpen FROM RegistrationPeriods WHERE IsOpen=1 ORDER BY CreatedAt DESC")
    period = cur.fetchone()
    acad_year = period.AcadYear if period else '2024-25'
    reg_open  = bool(period)
    try:
        selected_sem = int(request.args.get('sem', student.CurrentSem if student else 1))
    except (ValueError, TypeError):
        selected_sem = student.CurrentSem if student else 1
    existing = None
    if student:
        cur.execute("""
            SELECT RegID, Status FROM Registrations
            WHERE StudentID=? AND Semester=? AND AcadYear=?
        """, student.StudentID, selected_sem, acad_year)
        existing = cur.fetchone()
    subjects = []
    if student:
        cur.execute("""
            SELECT SubjectID, SubjectCode, SubjectName, IsElective
            FROM Subjects WHERE CourseID=? AND Semester=?
            ORDER BY IsElective, SubjectName
        """, student.CourseID, selected_sem)
        subjects = cur.fetchall()
    message = None
    if request.method == 'POST' and student and not existing and reg_open:
        selected_ids = request.form.getlist('subjects')
        post_sem     = int(request.form.get('semester', selected_sem))
        fee_file     = request.files.get('fee_receipt')

        fee_display_name = None
        fee_data         = None
        fee_mime         = None

        if fee_file and fee_file.filename:
            if not allowed_file(fee_file.filename):
                message = ('warn', 'Fee receipt must be PDF, JPG or PNG (max 5 MB).')
                conn.close()
                return render_template('student_register.html',
                    student=student, subjects=subjects, existing=existing,
                    message=message, all_semesters=all_semesters,
                    selected_sem=selected_sem, acad_year=acad_year, reg_open=reg_open)

            # Build a safe display name (used for download prompt only — NOT saved to disk)
            safe_name = secure_filename(fee_file.filename)
            fee_display_name = (
                f"{student.RollNo.replace('/', '_')}_{post_sem}_"
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            )
            fee_data = fee_file.read()          # read binary into memory
            fee_mime = get_mime(fee_file.filename)

        if len(selected_ids) < 2:
            message = ('warn', 'Please select at least 2 subjects.')
        else:
            # Store receipt binary directly in the database
            cur.execute("""
                INSERT INTO Registrations
                    (StudentID, Semester, AcadYear, Status,
                     FeeReceiptPath, FeeReceiptData, FeeReceiptMime)
                VALUES (?,?,?,'pending',?,?,?)
            """, student.StudentID, post_sem, acad_year,
                fee_display_name, fee_data, fee_mime)
            conn.commit()
            cur.execute("SELECT @@IDENTITY AS RegID")
            reg_id = int(cur.fetchone().RegID)
            for sid in selected_ids:
                cur.execute("INSERT INTO RegistrationSubjects (RegID,SubjectID) VALUES (?,?)", reg_id, int(sid))
            conn.commit()
            message = ('success', 'Registration submitted successfully!')
            existing = type('obj', (object,), {'RegID': reg_id, 'Status': 'pending'})()
    conn.close()
    return render_template('student_register.html',
        student=student, subjects=subjects, existing=existing, message=message,
        all_semesters=all_semesters, selected_sem=selected_sem,
        acad_year=acad_year, reg_open=reg_open)

@app.route('/student/status')
@login_required(role='student')
def student_status():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT s.StudentID FROM Students s WHERE s.UserID=?", session['user_id'])
    row = cur.fetchone(); regs = []
    if row:
        cur.execute("""
            SELECT r.RegID, r.Semester, r.AcadYear, r.Status,
                   r.SubmittedAt, r.ReviewedAt, r.Remarks, r.FeeReceiptPath
            FROM Registrations r WHERE r.StudentID=? ORDER BY r.SubmittedAt DESC
        """, row.StudentID)
        for r in cur.fetchall():
            cur.execute("""
                SELECT sub.SubjectName FROM RegistrationSubjects rs
                JOIN Subjects sub ON rs.SubjectID=sub.SubjectID WHERE rs.RegID=?
            """, r.RegID)
            regs.append({'reg': r, 'subjects': [s.SubjectName for s in cur.fetchall()]})
    conn.close()
    return render_template('student_status.html', regs=regs)

# ============================================================
# COORDINATOR ROUTES
# ============================================================
@app.route('/coordinator')
@login_required(role='coordinator')
def coordinator_dashboard():
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])
    cur.execute("""
        SELECT u.FullName, u.Email, co.Department, co.CoordID
        FROM Coordinators co JOIN Users u ON co.UserID=u.UserID
        WHERE co.UserID=?
    """, session['user_id'])
    coord_info = cur.fetchone()
    assignments = []
    if coord_id:
        assignments = get_coord_assignments(cur, coord_id)
    if assignments:
        cur.execute("""
            SELECT COUNT(*) FROM Registrations r
            JOIN Students s ON r.StudentID=s.StudentID
            WHERE r.Status='pending'
              AND EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=r.Semester)
        """, coord_id)
        pending_count = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM Registrations r
            JOIN Students s ON r.StudentID=s.StudentID
            WHERE r.Status='approved'
              AND EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=r.Semester)
        """, coord_id)
        approved_count = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(DISTINCT s.StudentID) FROM Students s
            WHERE EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=s.CurrentSem)
        """, coord_id)
        scoped_students = cur.fetchone()[0]
    else:
        pending_count = approved_count = scoped_students = 0

    cur.execute("SELECT TOP 1 AcadYear, IsOpen FROM RegistrationPeriods WHERE IsOpen=1 ORDER BY CreatedAt DESC")
    reg_period = cur.fetchone()
    reg_open   = bool(reg_period)
    acad_year  = reg_period.AcadYear if reg_period else None

    recent = []
    if coord_id:
        cur.execute("""
            SELECT TOP 5 u.FullName, r.Status, r.SubmittedAt, c.ShortCode, r.Semester
            FROM Registrations r
            JOIN Students s ON r.StudentID=s.StudentID
            JOIN Users u ON s.UserID=u.UserID
            JOIN Courses c ON s.CourseID=c.CourseID
            WHERE EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=r.Semester)
            ORDER BY r.SubmittedAt DESC
        """, coord_id)
        recent = cur.fetchall()
    conn.close()
    return render_template('coordinator_dashboard.html',
                           coord_info=coord_info, assignments=assignments,
                           pending=pending_count, approved=approved_count,
                           scoped_students=scoped_students, recent=recent,
                           reg_open=reg_open, acad_year=acad_year)


@app.route('/coordinator/initiate-registration', methods=['POST'])
@login_required(role='coordinator')
def coordinator_initiate_registration():
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])
    cur.execute("SELECT TOP 1 AcadYear FROM RegistrationPeriods WHERE IsOpen=1 ORDER BY CreatedAt DESC")
    period = cur.fetchone()
    if not period:
        conn.close()
        flash('No active registration period. Ask Admin to open a registration period first.', 'danger')
        return redirect(url_for('coordinator_dashboard'))
    acad_year = period.AcadYear
    cur.execute("""
        SELECT DISTINCT u.Email, u.FullName, c.CourseName, s.CurrentSem
        FROM Students s
        JOIN Users u ON s.UserID=u.UserID
        JOIN Courses c ON s.CourseID=c.CourseID
        WHERE u.IsActive=1 AND u.Email IS NOT NULL AND u.Email <> ''
          AND EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                      WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=s.CurrentSem)
    """, coord_id)
    students = cur.fetchall()
    conn.close()
    if not students:
        flash('No students with valid emails found in your assigned courses/semesters.', 'warn')
        return redirect(url_for('coordinator_dashboard'))
    sent_count = failed_count = 0
    for s in students:
        ok = send_registration_initiated_email(
            student_email=s.Email,
            student_name=s.FullName,
            acad_year=acad_year,
            course_name=s.CourseName,
            semester=s.CurrentSem
        )
        if ok: sent_count += 1
        else:  failed_count += 1
    if sent_count > 0:
        flash(f'Registration initiated! Notifications sent to {sent_count} student(s).', 'success')
    if failed_count > 0:
        flash(f'{failed_count} email(s) could not be delivered. Check SMTP configuration.', 'warn')
    return redirect(url_for('coordinator_dashboard'))


@app.route('/coordinator/students')
@login_required(role='coordinator')
def coordinator_students():
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])
    assigned_courses = []; assigned_sems = []
    if coord_id:
        cur.execute("""
            SELECT DISTINCT c.CourseID, c.ShortCode, c.CourseName
            FROM CoordinatorAssignments ca JOIN Courses c ON ca.CourseID=c.CourseID
            WHERE ca.CoordID=? ORDER BY c.ShortCode
        """, coord_id)
        assigned_courses = cur.fetchall()
        cur.execute("SELECT DISTINCT ca.Semester FROM CoordinatorAssignments ca WHERE ca.CoordID=? ORDER BY ca.Semester", coord_id)
        assigned_sems = [r[0] for r in cur.fetchall()]
    search = request.args.get('q', '').strip()
    course_filter = request.args.get('course', '').strip()
    sem_filter = request.args.get('sem', '').strip()
    query = """
        SELECT u.FullName, s.RollNo, c.ShortCode, s.CurrentSem,
               r.Status, r.RegID,
               (SELECT STRING_AGG(sub.SubjectName, ', ')
                FROM RegistrationSubjects rs
                JOIN Subjects sub ON rs.SubjectID=sub.SubjectID
                WHERE rs.RegID=r.RegID) AS Subjects
        FROM Students s
        JOIN Users u ON s.UserID=u.UserID
        JOIN Courses c ON s.CourseID=c.CourseID
        LEFT JOIN (SELECT StudentID, MAX(RegID) AS RegID FROM Registrations GROUP BY StudentID) latest ON latest.StudentID=s.StudentID
        LEFT JOIN Registrations r ON r.RegID=latest.RegID
        WHERE EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                      WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=s.CurrentSem)
    """
    params = [coord_id]
    if search:
        query += " AND (u.FullName LIKE ? OR s.RollNo LIKE ?)"; params += [f'%{search}%', f'%{search}%']
    if course_filter:
        query += " AND c.ShortCode=?"; params.append(course_filter)
    if sem_filter:
        query += " AND s.CurrentSem=?"; params.append(int(sem_filter))
    query += " ORDER BY u.FullName"
    cur.execute(query, *params)
    students = cur.fetchall()
    conn.close()
    return render_template('coordinator_students.html',
                           students=students, search=search,
                           course_filter=course_filter, sem_filter=sem_filter,
                           assigned_courses=assigned_courses, assigned_sems=assigned_sems)


@app.route('/coordinator/export')
@login_required(role='coordinator')
def coordinator_export():
    export_type = request.args.get('type', 'registered')
    fmt = request.args.get('fmt', 'csv')
    course_filter = request.args.get('course', '').strip()
    sem_filter = request.args.get('sem', '').strip()
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])
    if export_type == 'registered':
        query = """
            SELECT u.FullName, s.RollNo, c.ShortCode AS Course,
                   r.Semester, r.AcadYear, r.Status, r.SubmittedAt, r.FeeReceiptPath,
                   (SELECT STRING_AGG(sub.SubjectName, '; ')
                    FROM RegistrationSubjects rs JOIN Subjects sub ON rs.SubjectID=sub.SubjectID
                    WHERE rs.RegID=r.RegID) AS Subjects
            FROM Registrations r
            JOIN Students s ON r.StudentID=s.StudentID
            JOIN Users u ON s.UserID=u.UserID
            JOIN Courses c ON s.CourseID=c.CourseID
            WHERE EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=r.Semester)
        """
        params = [coord_id]
        if course_filter: query += " AND c.ShortCode=?"; params.append(course_filter)
        if sem_filter:    query += " AND r.Semester=?";  params.append(int(sem_filter))
        query += " ORDER BY u.FullName"
        cur.execute(query, *params); rows = cur.fetchall()
        headers = ['Full Name','Roll No','Course','Semester','Acad Year','Status','Submitted At','Fee Receipt','Subjects']
        data = [[r.FullName,r.RollNo,r.Course,r.Semester,r.AcadYear,r.Status,
                 str(r.SubmittedAt)[:19] if r.SubmittedAt else '','Yes' if r.FeeReceiptPath else 'No',r.Subjects or ''] for r in rows]
        filename_base = 'registered_students'
    else:
        cur.execute("SELECT TOP 1 AcadYear FROM RegistrationPeriods WHERE IsOpen=1 ORDER BY CreatedAt DESC")
        prow = cur.fetchone(); acad_year = prow.AcadYear if prow else '2024-25'
        query = """
            SELECT u.FullName, s.RollNo, c.ShortCode AS Course, s.CurrentSem
            FROM Students s JOIN Users u ON s.UserID=u.UserID JOIN Courses c ON s.CourseID=c.CourseID
            WHERE u.IsActive=1
              AND s.StudentID NOT IN (SELECT StudentID FROM Registrations WHERE AcadYear=?)
              AND EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                          WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=s.CurrentSem)
        """
        params = [acad_year, coord_id]
        if course_filter: query += " AND c.ShortCode=?"; params.append(course_filter)
        if sem_filter:    query += " AND s.CurrentSem=?"; params.append(int(sem_filter))
        query += " ORDER BY u.FullName"
        cur.execute(query, *params); rows = cur.fetchall()
        headers = ['Full Name','Roll No','Course','Current Semester']
        data = [[r.FullName,r.RollNo,r.Course,r.CurrentSem] for r in rows]
        filename_base = 'unregistered_students'
    conn.close()
    if fmt == 'excel':
        try:
            import openpyxl
            wb = openpyxl.Workbook(); ws = wb.active; ws.title = export_type.capitalize()
            ws.append(headers)
            for row in data: ws.append(row)
            buf = io.BytesIO(); wb.save(buf); buf.seek(0)
            return send_file(buf, as_attachment=True, download_name=f'{filename_base}.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        except ImportError: pass
    buf = io.StringIO()
    writer = csv.writer(buf); writer.writerow(headers); writer.writerows(data)
    return send_file(io.BytesIO(buf.getvalue().encode('utf-8-sig')),
                     as_attachment=True, download_name=f'{filename_base}.csv', mimetype='text/csv')


@app.route('/coordinator/verify')
@login_required(role='coordinator')
def coordinator_verify():
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])
    cur.execute("""
        SELECT r.RegID, u.FullName, s.RollNo, c.ShortCode,
               r.Semester, r.AcadYear, r.SubmittedAt, r.FeeReceiptPath,
               (r.FeeReceiptData IS NOT NULL) AS HasReceipt,
               (SELECT STRING_AGG(sub.SubjectName, ', ')
                FROM RegistrationSubjects rs JOIN Subjects sub ON rs.SubjectID=sub.SubjectID
                WHERE rs.RegID=r.RegID) AS Subjects
        FROM Registrations r
        JOIN Students s ON r.StudentID=s.StudentID
        JOIN Users u ON s.UserID=u.UserID
        JOIN Courses c ON s.CourseID=c.CourseID
        WHERE r.Status='pending'
          AND EXISTS (SELECT 1 FROM CoordinatorAssignments ca
                      WHERE ca.CoordID=? AND ca.CourseID=s.CourseID AND ca.Semester=r.Semester)
        ORDER BY r.SubmittedAt
    """, coord_id)
    pending = cur.fetchall()
    conn.close()
    return render_template('coordinator_verify.html', pending=pending)


# ============================================================
# FEE RECEIPT ROUTE — serves binary data from the DATABASE
# Route changed from /coordinator/receipt/<filename>
#                to  /coordinator/receipt/<int:reg_id>
# Coordinator-only: fetches FeeReceiptData from Registrations table.
# ============================================================
@app.route('/coordinator/receipt/<int:reg_id>')
@login_required(role='coordinator')
def view_receipt(reg_id):
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])

    # Verify this coordinator is allowed to see this registration
    cur.execute("""
        SELECT r.FeeReceiptData, r.FeeReceiptMime, r.FeeReceiptPath
        FROM Registrations r
        JOIN Students s ON r.StudentID = s.StudentID
        WHERE r.RegID = ?
          AND EXISTS (
              SELECT 1 FROM CoordinatorAssignments ca
              WHERE ca.CoordID = ? AND ca.CourseID = s.CourseID AND ca.Semester = r.Semester
          )
    """, reg_id, coord_id)
    row = cur.fetchone()
    conn.close()

    if not row or not row.FeeReceiptData:
        abort(404)

    file_data = bytes(row.FeeReceiptData)
    mime_type = row.FeeReceiptMime or 'application/octet-stream'
    display_name = row.FeeReceiptPath or f'receipt_{reg_id}'

    return Response(
        file_data,
        mimetype=mime_type,
        headers={
            'Content-Disposition': f'inline; filename="{display_name}"',
            'Content-Length': str(len(file_data)),
        }
    )


@app.route('/coordinator/action', methods=['POST'])
@login_required(role='coordinator')
def coordinator_action():
    reg_id  = request.form.get('reg_id')
    action  = request.form.get('action')
    remarks = request.form.get('remarks', '')
    conn = get_db(); cur = conn.cursor()
    coord_id = get_coord_id(cur, session['user_id'])

    cur.execute("""
        SELECT u.Email, u.FullName, c.CourseName, c.ShortCode,
               r.Semester, r.AcadYear,
               (SELECT STRING_AGG(sub.SubjectName, ', ')
                FROM RegistrationSubjects rs
                JOIN Subjects sub ON rs.SubjectID = sub.SubjectID
                WHERE rs.RegID = r.RegID) AS Subjects,
               cu.FullName AS CoordName
        FROM Registrations r
        JOIN Students s ON r.StudentID = s.StudentID
        JOIN Users u    ON s.UserID    = u.UserID
        JOIN Courses c  ON s.CourseID  = c.CourseID
        JOIN Coordinators co ON co.CoordID = ?
        JOIN Users cu       ON co.UserID   = cu.UserID
        WHERE r.RegID = ?
    """, coord_id, reg_id)
    reg_info = cur.fetchone()

    cur.execute(
        "UPDATE Registrations SET Status=?, ReviewedAt=GETDATE(), ReviewedBy=?, Remarks=? WHERE RegID=?",
        action, coord_id, remarks, reg_id
    )
    conn.commit()
    conn.close()

    if reg_info and reg_info.Email:
        sent = send_registration_decision_email(
            student_email    = reg_info.Email,
            student_name     = reg_info.FullName,
            action           = action,
            reg_id           = reg_id,
            course_name      = reg_info.CourseName,
            short_code       = reg_info.ShortCode,
            semester         = reg_info.Semester,
            acad_year        = reg_info.AcadYear,
            subjects         = reg_info.Subjects or '',
            remarks          = remarks,
            coordinator_name = reg_info.CoordName
        )
        if sent:
            flash(f'Registration {action}. Notification email sent to {reg_info.Email}.', 'success')
        else:
            flash(f'Registration {action}. (Email could not be delivered — check SMTP config.)', 'warn')
    else:
        flash(f'Registration {action} successfully.', 'success')

    return redirect(url_for('coordinator_verify'))


# ============================================================
# ADMIN ROUTES
# ============================================================
@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM Students"); total_students = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Coordinators"); total_coords = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Registrations WHERE Status='pending'"); pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Courses"); total_courses = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM Subjects"); total_subjects = cur.fetchone()[0]
    cur.execute("""
        SELECT TOP 1 PeriodID, AcadYear, IsOpen, StartDate, EndDate, CreatedAt
        FROM RegistrationPeriods
        ORDER BY CreatedAt DESC
    """)
    reg_period = cur.fetchone()
    cur.execute("""
        SELECT PeriodID, AcadYear, IsOpen, StartDate, EndDate, CreatedAt
        FROM RegistrationPeriods
        ORDER BY CreatedAt DESC
    """)
    all_periods = cur.fetchall()
    conn.close()
    return render_template('admin_dashboard.html',
                           total_students=total_students, total_coords=total_coords,
                           pending=pending, total_courses=total_courses,
                           total_subjects=total_subjects, reg_period=reg_period,
                           all_periods=all_periods)


@app.route('/admin/registration-period', methods=['POST'])
@login_required(role='admin')
def admin_toggle_reg_period():
    action    = request.form.get('action')
    acad_year = request.form.get('acad_year', '').strip()
    start_date = request.form.get('start_date') or None
    end_date   = request.form.get('end_date')   or None
    conn = get_db(); cur = conn.cursor()
    if action == 'open':
        cur.execute("UPDATE RegistrationPeriods SET IsOpen=0 WHERE IsOpen=1")
        cur.execute(
            "INSERT INTO RegistrationPeriods (AcadYear, IsOpen, StartDate, EndDate) VALUES (?,1,?,?)",
            acad_year, start_date, end_date
        )
        flash(f'Registration period opened for {acad_year}.', 'success')
    else:
        cur.execute("UPDATE RegistrationPeriods SET IsOpen=0 WHERE IsOpen=1")
        flash('Registration period closed.', 'success')
    conn.commit(); conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/registration-period/edit/<int:period_id>', methods=['POST'])
@login_required(role='admin')
def admin_edit_reg_period(period_id):
    acad_year  = request.form.get('acad_year', '').strip()
    start_date = request.form.get('start_date') or None
    end_date   = request.form.get('end_date')   or None
    is_open    = 1 if request.form.get('is_open') else 0
    conn = get_db(); cur = conn.cursor()
    try:
        if is_open:
            cur.execute("UPDATE RegistrationPeriods SET IsOpen=0 WHERE PeriodID!=?", period_id)
        cur.execute("""
            UPDATE RegistrationPeriods
            SET AcadYear=?, StartDate=?, EndDate=?, IsOpen=?
            WHERE PeriodID=?
        """, acad_year, start_date, end_date, is_open, period_id)
        conn.commit()
        flash(f'Registration period "{acad_year}" updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating period: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/registration-period/delete/<int:period_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_reg_period(period_id):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT AcadYear FROM RegistrationPeriods WHERE PeriodID=?", period_id)
        row = cur.fetchone()
        if not row:
            flash('Period not found.', 'danger')
            conn.close()
            return redirect(url_for('admin_dashboard'))
        cur.execute("DELETE FROM RegistrationPeriods WHERE PeriodID=?", period_id)
        conn.commit()
        flash(f'Registration period "{row.AcadYear}" deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting period: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/users')
@login_required(role='admin')
def admin_users():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT u.UserID, u.Username, u.FullName, u.Email, u.Role,
               u.IsActive, u.CreatedAt,
               s.RollNo, c.ShortCode, s.CurrentSem,
               co.CoordID, co.Department
        FROM Users u
        LEFT JOIN Students s ON s.UserID=u.UserID
        LEFT JOIN Courses c ON c.CourseID=s.CourseID
        LEFT JOIN Coordinators co ON co.UserID=u.UserID
        WHERE u.Role IN ('student','coordinator')
        ORDER BY u.Role, u.FullName
    """)
    users = cur.fetchall()
    coord_assignments = {}
    for u in users:
        if u.Role == 'coordinator' and u.CoordID:
            cur.execute("""
                SELECT ca.AssignID, c.ShortCode, ca.Semester
                FROM CoordinatorAssignments ca JOIN Courses c ON ca.CourseID=c.CourseID
                WHERE ca.CoordID=? ORDER BY c.ShortCode, ca.Semester
            """, u.CoordID)
            coord_assignments[u.CoordID] = cur.fetchall()
    cur.execute("SELECT CourseID, CourseName, ShortCode, Duration FROM Courses ORDER BY ShortCode")
    courses = cur.fetchall()
    cur.execute("""
        SELECT co.CoordID, u.FullName, co.Department
        FROM Coordinators co JOIN Users u ON co.UserID=u.UserID
        WHERE u.IsActive=1 ORDER BY u.FullName
    """)
    coordinators = cur.fetchall()
    conn.close()
    return render_template('admin_users.html', users=users, courses=courses,
                           coordinators=coordinators, coord_assignments=coord_assignments)


@app.route('/admin/users/add', methods=['POST'])
@login_required(role='admin')
def admin_add_user():
    full_name = request.form.get('full_name', '').strip()
    username  = request.form.get('username', '').strip()
    email     = request.form.get('email', '').strip()
    role      = request.form.get('role', 'student')
    password  = request.form.get('password', 'pass123')
    course_id = request.form.get('course_id')
    short_code= request.form.get('short_code', 'BCA')
    init_sem  = int(request.form.get('init_sem', 1))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO Users (Username, PasswordHash, Role, FullName, Email) VALUES (?,?,?,?,?)",
                    username, password, role, full_name, email)
        conn.commit()
        cur.execute("SELECT @@IDENTITY AS UID"); uid = int(cur.fetchone().UID)
        if role == 'student' and course_id:
            roll = f"{short_code}/{datetime.now().year}/{uid:03d}"
            cur.execute("INSERT INTO Students (UserID, RollNo, CourseID, CurrentSem, Batch) VALUES (?,?,?,?,?)",
                        uid, roll, int(course_id), init_sem, f"{datetime.now().year}-{datetime.now().year+3}")
        elif role == 'coordinator':
            cur.execute("INSERT INTO Coordinators (UserID, Department) VALUES (?,?)",
                        uid, request.form.get('department', ''))
        conn.commit(); flash('User created successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_user(user_id):
    action = request.form.get('action', 'deactivate')
    conn = get_db(); cur = conn.cursor()
    if action == 'activate':
        cur.execute("UPDATE Users SET IsActive=1 WHERE UserID=?", user_id)
        flash('User activated.', 'success')
    else:
        cur.execute("UPDATE Users SET IsActive=0 WHERE UserID=?", user_id)
        flash('User deactivated.', 'success')
    conn.commit(); conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required(role='admin')
def admin_edit_user(user_id):
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        full_name  = request.form.get('full_name', '').strip()
        username   = request.form.get('username', '').strip()
        email      = request.form.get('email', '').strip()
        is_active  = 1 if request.form.get('is_active') else 0
        password   = request.form.get('password', '').strip()
        department = request.form.get('department', '').strip()
        course_id  = request.form.get('course_id')
        current_sem= request.form.get('current_sem')
        batch      = request.form.get('batch', '').strip()
        try:
            if password:
                cur.execute(
                    "UPDATE Users SET FullName=?, Username=?, Email=?, IsActive=?, PasswordHash=? WHERE UserID=?",
                    full_name, username, email, is_active, password, user_id)
            else:
                cur.execute(
                    "UPDATE Users SET FullName=?, Username=?, Email=?, IsActive=? WHERE UserID=?",
                    full_name, username, email, is_active, user_id)
            conn.commit()
            cur.execute("SELECT Role FROM Users WHERE UserID=?", user_id)
            role_row = cur.fetchone()
            if role_row:
                role = role_row[0]
                if role == 'coordinator' and department:
                    cur.execute("UPDATE Coordinators SET Department=? WHERE UserID=?", department, user_id)
                elif role == 'student':
                    if course_id:
                        cur.execute("UPDATE Students SET CourseID=? WHERE UserID=?", int(course_id), user_id)
                    if current_sem:
                        cur.execute("UPDATE Students SET CurrentSem=? WHERE UserID=?", int(current_sem), user_id)
                    if batch:
                        cur.execute("UPDATE Students SET Batch=? WHERE UserID=?", batch, user_id)
            conn.commit()
            flash('User updated successfully.', 'success')
        except Exception as e:
            flash(f'Error updating user: {e}', 'danger')
        conn.close()
        return redirect(url_for('admin_users'))
    cur.execute("""
        SELECT u.UserID, u.Username, u.FullName, u.Email, u.Role, u.IsActive,
               s.RollNo, s.CourseID, s.CurrentSem, s.Batch,
               co.Department
        FROM Users u
        LEFT JOIN Students s ON s.UserID=u.UserID
        LEFT JOIN Coordinators co ON co.UserID=u.UserID
        WHERE u.UserID=?
    """, user_id)
    user = cur.fetchone()
    cur.execute("SELECT CourseID, CourseName, ShortCode, Duration FROM Courses ORDER BY ShortCode")
    courses = cur.fetchall()
    conn.close()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))
    return render_template('admin_edit_user.html', user=user, courses=courses)


@app.route('/admin/users/hard-delete/<int:user_id>', methods=['POST'])
@login_required(role='admin')
def admin_hard_delete_user(user_id):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("""
            DELETE rs FROM RegistrationSubjects rs
            JOIN Registrations r ON rs.RegID=r.RegID
            JOIN Students s ON r.StudentID=s.StudentID
            WHERE s.UserID=?
        """, user_id)
        cur.execute("""
            DELETE r FROM Registrations r
            JOIN Students s ON r.StudentID=s.StudentID
            WHERE s.UserID=?
        """, user_id)
        cur.execute("DELETE FROM Students WHERE UserID=?", user_id)
        cur.execute("""
            DELETE ca FROM CoordinatorAssignments ca
            JOIN Coordinators co ON ca.CoordID=co.CoordID
            WHERE co.UserID=?
        """, user_id)
        cur.execute("DELETE FROM Coordinators WHERE UserID=?", user_id)
        cur.execute("DELETE FROM PasswordResetTokens WHERE UserID=?", user_id)
        cur.execute("DELETE FROM Users WHERE UserID=?", user_id)
        conn.commit()
        flash('User permanently deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting user: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/coordinator/assign', methods=['POST'])
@login_required(role='admin')
def admin_assign_coordinator():
    coord_id = request.form.get('coord_id')
    course_id = request.form.get('assign_course_id')
    semester = request.form.get('assign_semester')
    if not (coord_id and course_id and semester):
        flash('Please select coordinator, course and semester.', 'warn')
        return redirect(url_for('admin_users'))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("""
            IF NOT EXISTS (SELECT 1 FROM CoordinatorAssignments WHERE CoordID=? AND CourseID=? AND Semester=?)
            INSERT INTO CoordinatorAssignments (CoordID, CourseID, Semester) VALUES (?,?,?)
        """, coord_id, course_id, semester, coord_id, course_id, semester)
        conn.commit(); flash('Assignment added successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/coordinator/unassign', methods=['POST'])
@login_required(role='admin')
def admin_unassign_coordinator():
    assign_id = request.form.get('assign_id')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM CoordinatorAssignments WHERE AssignID=?", assign_id)
        conn.commit(); flash('Assignment removed.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_users'))


@app.route('/admin/courses')
@login_required(role='admin')
def admin_courses():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.CourseID, c.CourseName, c.ShortCode, c.Duration, COUNT(s.StudentID) AS StudentCount
        FROM Courses c LEFT JOIN Students s ON s.CourseID=c.CourseID
        GROUP BY c.CourseID, c.CourseName, c.ShortCode, c.Duration
    """)
    courses = cur.fetchall(); conn.close()
    return render_template('admin_courses.html', courses=courses)


@app.route('/admin/courses/add', methods=['POST'])
@login_required(role='admin')
def admin_add_course():
    name = request.form.get('course_name', '').strip()
    code = request.form.get('short_code', '').strip().upper()
    dur  = request.form.get('duration', '').strip()
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO Courses (CourseName, ShortCode, Duration) VALUES (?,?,?)", name, code, dur)
        conn.commit(); flash('Course added successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_courses'))


@app.route('/admin/courses/delete/<int:course_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_course(course_id):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM Courses WHERE CourseID=?", course_id)
        conn.commit(); flash('Course deleted.', 'success')
    except Exception as e:
        flash(f'Cannot delete - course may have students/subjects: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_courses'))


@app.route('/admin/subjects')
@login_required(role='admin')
def admin_subjects():
    conn = get_db(); cur = conn.cursor()
    course_filter = request.args.get('course', '')
    query = """
        SELECT sub.SubjectID, sub.SubjectCode, sub.SubjectName,
               c.ShortCode, sub.Semester, sub.IsElective
        FROM Subjects sub JOIN Courses c ON sub.CourseID=c.CourseID WHERE 1=1
    """
    params = []
    if course_filter: query += " AND c.ShortCode=?"; params.append(course_filter)
    query += " ORDER BY c.ShortCode, sub.Semester, sub.SubjectName"
    cur.execute(query, *params)
    subjects = cur.fetchall()
    cur.execute("SELECT CourseID, ShortCode FROM Courses ORDER BY ShortCode")
    courses = cur.fetchall(); conn.close()
    return render_template('admin_subjects.html', subjects=subjects,
                           courses=courses, course_filter=course_filter)


@app.route('/admin/subjects/add', methods=['POST'])
@login_required(role='admin')
def admin_add_subject():
    name=request.form.get('subject_name','').strip()
    code=request.form.get('subject_code','').strip()
    course_id=request.form.get('course_id')
    semester=request.form.get('semester')
    elective=1 if request.form.get('is_elective') else 0
    conn=get_db(); cur=conn.cursor()
    try:
        cur.execute("INSERT INTO Subjects (SubjectCode,SubjectName,CourseID,Semester,IsElective) VALUES (?,?,?,?,?)",
                    code,name,course_id,semester,elective)
        conn.commit(); flash('Subject added.','success')
    except Exception as e:
        flash(f'Error: {e}','danger')
    conn.close()
    return redirect(url_for('admin_subjects'))


@app.route('/admin/subjects/delete/<int:subject_id>', methods=['POST'])
@login_required(role='admin')
def admin_delete_subject(subject_id):
    conn=get_db(); cur=conn.cursor()
    try:
        cur.execute("SELECT SubjectName, IsElective FROM Subjects WHERE SubjectID=?", subject_id)
        sub = cur.fetchone()
        if not sub:
            flash('Subject not found.', 'danger')
            conn.close()
            return redirect(url_for('admin_subjects'))
        if sub.IsElective:
            cur.execute("DELETE FROM RegistrationSubjects WHERE SubjectID=?", subject_id)
            conn.commit()
            cur.execute("DELETE FROM Subjects WHERE SubjectID=?", subject_id)
            conn.commit()
            flash(f'Elective subject "{sub.SubjectName}" deleted and removed from all registrations.', 'success')
        else:
            cur.execute("SELECT COUNT(*) FROM RegistrationSubjects WHERE SubjectID=?", subject_id)
            ref_count = cur.fetchone()[0]
            if ref_count > 0:
                flash(f'Cannot delete core subject "{sub.SubjectName}" — it is referenced in {ref_count} registration(s). '
                      'Remove those registrations first, or convert it to an elective.', 'danger')
                conn.close()
                return redirect(url_for('admin_subjects'))
            cur.execute("DELETE FROM Subjects WHERE SubjectID=?", subject_id)
            conn.commit()
            flash(f'Subject "{sub.SubjectName}" deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_subjects'))


# ============================================================
# API
# ============================================================
@app.route('/api/subjects/<int:course_id>/<int:semester>')
def api_subjects(course_id, semester):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT SubjectID,SubjectName,IsElective FROM Subjects WHERE CourseID=? AND Semester=? ORDER BY IsElective,SubjectName", course_id, semester)
    rows=[{'id':r.SubjectID,'name':r.SubjectName,'elective':bool(r.IsElective)} for r in cur.fetchall()]
    conn.close(); return jsonify(rows)

@app.route('/api/course-semesters/<int:course_id>')
def api_course_semesters(course_id):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT DISTINCT Semester FROM Subjects WHERE CourseID=? ORDER BY Semester", course_id)
    sems=[r[0] for r in cur.fetchall()]; conn.close(); return jsonify(sems)

@app.route('/api/courses')
def api_courses():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT CourseID, ShortCode, CourseName, Duration FROM Courses ORDER BY ShortCode")
    rows=[{'id':r.CourseID,'code':r.ShortCode,'name':r.CourseName,'duration':r.Duration} for r in cur.fetchall()]
    conn.close(); return jsonify(rows)

@app.route('/api/coordinator-semesters/<int:course_id>')
def api_coordinator_semesters(course_id):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT DISTINCT Semester FROM Subjects WHERE CourseID=? ORDER BY Semester", course_id)
    sems=[r[0] for r in cur.fetchall()]; conn.close(); return jsonify(sems)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
