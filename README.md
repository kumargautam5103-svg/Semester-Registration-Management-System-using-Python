# Semester-Registration-Management-System-using-Python
FILE STRUCTURE
--------------
SRMS/
├── frontend/
│   ├── templates/          All Jinja2 HTML templates
│   └── static/
│       ├── css/            Stylesheets
│       ├── js/             JavaScript files
│       └── images/         Static images (logo, banners)
│
├── backend/
│   ├── app.py              Main Flask application
│   └── requirements.txt    Python dependencies
│
└── database/
    └── database_setup.sql  SQL Server setup script (v8)

SETUP INSTRUCTIONS
------------------
1. Run database/database_setup.sql on SQL Server (SSMS or sqlcmd).
2. Edit backend/app.py:
   - DB_CONFIG: set your server name, database, credentials
   - MAIL_USERNAME / MAIL_PASSWORD: your Gmail App Password
3. Install dependencies:
   cd backend
   pip install -r requirements.txt
4. Run the app:
   python app.py
5. Open http://localhost:5000

Default logins: admin/pass123 | coord/pass123 | student/pass123

