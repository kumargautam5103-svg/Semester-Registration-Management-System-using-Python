SRMS - Semester Registration Management System
==============================================
Version: v8 (Fee Receipt stored in Database)

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

WHAT CHANGED IN v8
------------------
Fee Receipt: DATABASE STORAGE (not local files)

  BEFORE (v7):
  - Student uploads fee receipt → saved to uploads/fee_receipts/ folder on server disk
  - FeeReceiptPath stored the filename (e.g. BCA_2026_010_3_..._receipt.jpg)
  - Coordinator accessed: GET /coordinator/receipt/<filename>  (read from disk)

  AFTER (v8):
  - Student uploads fee receipt → binary data stored in Registrations.FeeReceiptData (VARBINARY MAX)
  - FeeReceiptPath stores only the original display filename (NOT written to disk)
  - FeeReceiptMime stores the MIME type (image/jpeg, image/png, application/pdf)
  - Coordinator accesses: GET /coordinator/receipt/<reg_id>  (streamed from database)
  - No uploads/ folder is created or used

  Database changes (migration):
    ALTER TABLE Registrations ADD FeeReceiptData VARBINARY(MAX) NULL;
    ALTER TABLE Registrations ADD FeeReceiptMime NVARCHAR(100) NULL;

  The uploads/ directory is no longer needed and is not created.
