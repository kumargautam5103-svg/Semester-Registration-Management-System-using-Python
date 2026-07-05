
USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'SRMS_DB3')
BEGIN
    CREATE DATABASE SRMS_DB3;
END
GO

USE SRMS_DB3;
GO


IF OBJECT_ID('dbo.PasswordResetTokens',   'U') IS NOT NULL DROP TABLE dbo.PasswordResetTokens;
IF OBJECT_ID('dbo.CoordinatorAssignments','U') IS NOT NULL DROP TABLE dbo.CoordinatorAssignments;
IF OBJECT_ID('dbo.RegistrationSubjects',  'U') IS NOT NULL DROP TABLE dbo.RegistrationSubjects;
IF OBJECT_ID('dbo.Registrations',         'U') IS NOT NULL DROP TABLE dbo.Registrations;
IF OBJECT_ID('dbo.RegistrationPeriods',   'U') IS NOT NULL DROP TABLE dbo.RegistrationPeriods;
IF OBJECT_ID('dbo.Subjects',              'U') IS NOT NULL DROP TABLE dbo.Subjects;
IF OBJECT_ID('dbo.Coordinators',          'U') IS NOT NULL DROP TABLE dbo.Coordinators;
IF OBJECT_ID('dbo.Students',              'U') IS NOT NULL DROP TABLE dbo.Students;
IF OBJECT_ID('dbo.Users',                 'U') IS NOT NULL DROP TABLE dbo.Users;
IF OBJECT_ID('dbo.Courses',               'U') IS NOT NULL DROP TABLE dbo.Courses;
GO

-- ============================================================
-- COURSES
-- ============================================================
CREATE TABLE dbo.Courses (
    CourseID   INT IDENTITY(1,1) PRIMARY KEY,
    CourseName NVARCHAR(100) NOT NULL,
    ShortCode  NVARCHAR(10)  NOT NULL UNIQUE,
    Duration   NVARCHAR(50)  NOT NULL,
    CreatedAt  DATETIME      DEFAULT GETDATE()
);
GO


CREATE TABLE dbo.Users (
    UserID       INT IDENTITY(1,1) PRIMARY KEY,
    Username     NVARCHAR(50)  NOT NULL UNIQUE,
    PasswordHash NVARCHAR(256) NOT NULL,
    Role         NVARCHAR(20)  NOT NULL CHECK (Role IN ('student','coordinator','admin')),
    FullName     NVARCHAR(100) NOT NULL,
    Email        NVARCHAR(150),
    IsActive     BIT           DEFAULT 1,
    CreatedAt    DATETIME      DEFAULT GETDATE()
);
GO


CREATE TABLE dbo.Students (
    StudentID  INT IDENTITY(1,1) PRIMARY KEY,
    UserID     INT NOT NULL REFERENCES dbo.Users(UserID),
    RollNo     NVARCHAR(30) NOT NULL UNIQUE,
    CourseID   INT NOT NULL REFERENCES dbo.Courses(CourseID),
    CurrentSem INT NOT NULL DEFAULT 1,
    Batch      NVARCHAR(20),
    CreatedAt  DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- COORDINATORS
-- ============================================================
CREATE TABLE dbo.Coordinators (
    CoordID    INT IDENTITY(1,1) PRIMARY KEY,
    UserID     INT NOT NULL REFERENCES dbo.Users(UserID),
    Department NVARCHAR(100),
    CreatedAt  DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- COORDINATOR ASSIGNMENTS
-- ============================================================
CREATE TABLE dbo.CoordinatorAssignments (
    AssignID   INT IDENTITY(1,1) PRIMARY KEY,
    CoordID    INT NOT NULL REFERENCES dbo.Coordinators(CoordID) ON DELETE CASCADE,
    CourseID   INT NOT NULL REFERENCES dbo.Courses(CourseID)     ON DELETE CASCADE,
    Semester   INT NOT NULL,
    AssignedAt DATETIME DEFAULT GETDATE(),
    CONSTRAINT UQ_CoordAssign UNIQUE (CoordID, CourseID, Semester)
);
GO

-- ============================================================
-- SUBJECTS
-- ============================================================
CREATE TABLE dbo.Subjects (
    SubjectID   INT IDENTITY(1,1) PRIMARY KEY,
    SubjectCode NVARCHAR(20)  NOT NULL UNIQUE,
    SubjectName NVARCHAR(100) NOT NULL,
    CourseID    INT NOT NULL REFERENCES dbo.Courses(CourseID),
    Semester    INT NOT NULL,
    IsElective  BIT DEFAULT 0,
    CreatedAt   DATETIME DEFAULT GETDATE()
);
GO

-- ============================================================
-- REGISTRATION PERIODS
-- ============================================================
CREATE TABLE dbo.RegistrationPeriods (
    PeriodID  INT IDENTITY(1,1) PRIMARY KEY,
    AcadYear  NVARCHAR(20) NOT NULL,
    IsOpen    BIT NOT NULL DEFAULT 0,
    StartDate DATE NULL,
    EndDate   DATE NULL,
    CreatedAt DATETIME DEFAULT GETDATE()
);
GO


CREATE TABLE dbo.Registrations (
    RegID             INT IDENTITY(1,1) PRIMARY KEY,
    StudentID         INT NOT NULL REFERENCES dbo.Students(StudentID),
    Semester          INT NOT NULL,
    AcadYear          NVARCHAR(20) NOT NULL,
    Status            NVARCHAR(20) DEFAULT 'pending' CHECK (Status IN ('pending','approved','rejected')),
    -- Fee receipt stored in database (not on filesystem)
    FeeReceiptPath    NVARCHAR(500) NULL,   -- original filename for display
    FeeReceiptData    VARBINARY(MAX) NULL,  -- binary file content
    FeeReceiptMime    NVARCHAR(100)  NULL,  -- e.g. image/jpeg, image/png, application/pdf
    SubmittedAt       DATETIME DEFAULT GETDATE(),
    ReviewedAt        DATETIME,
    ReviewedBy        INT REFERENCES dbo.Coordinators(CoordID),
    Remarks           NVARCHAR(500)
);
GO


CREATE TABLE dbo.RegistrationSubjects (
    ID        INT IDENTITY(1,1) PRIMARY KEY,
    RegID     INT NOT NULL REFERENCES dbo.Registrations(RegID),
    SubjectID INT NOT NULL REFERENCES dbo.Subjects(SubjectID)
);
GO

-- ============================================================
-- PASSWORD RESET TOKENS
-- ============================================================
CREATE TABLE dbo.PasswordResetTokens (
    TokenID   INT IDENTITY(1,1) PRIMARY KEY,
    UserID    INT NOT NULL REFERENCES dbo.Users(UserID) ON DELETE CASCADE,
    Token     NVARCHAR(100) NOT NULL UNIQUE,
    ExpiresAt DATETIME NOT NULL,
    CreatedAt DATETIME DEFAULT GETDATE()
);
GO

CREATE INDEX IX_PRT_Token         ON dbo.PasswordResetTokens(Token);
CREATE INDEX IX_RegPeriods_CreatedAt ON dbo.RegistrationPeriods(CreatedAt DESC);
CREATE INDEX IX_RegSubjects_SubjectID ON dbo.RegistrationSubjects(SubjectID);
GO

-- ============================================================
-- SEED DATA
-- ============================================================
INSERT INTO dbo.Courses (CourseName, ShortCode, Duration) VALUES
('Bachelor of Computer Applications', 'BCA', '3 years / 6 semesters'),
('Master of Computer Applications',   'MCA', '2 years / 4 semesters');
GO

INSERT INTO dbo.Users (Username, PasswordHash, Role, FullName, Email) VALUES
('admin',   'pass123', 'admin',       'Administrator',    'admin@university.edu'),
('coord',   'pass123', 'coordinator', 'Dr. Anita Mishra', 'anita@university.edu'),
('student', 'pass123', 'student',     'Rahul Sharma',     'rahul@university.edu'),
('s002',    'pass123', 'student',     'Priya Nair',       'priya@university.edu'),
('s003',    'pass123', 'student',     'Ankit Verma',      'ankit@university.edu'),
('s004',    'pass123', 'student',     'Sneha Pillai',     'sneha@university.edu'),
('s005',    'pass123', 'student',     'Mohit Gupta',      'mohit@university.edu'),
('coord2',  'pass123', 'coordinator', 'Prof. Vikram Sen',  'vikram@university.edu');
GO

INSERT INTO dbo.Students (UserID, RollNo, CourseID, CurrentSem, Batch) VALUES
(3, 'BCA/2022/041', 1, 4, '2022-2025'),
(4, 'MCA/2023/012', 2, 2, '2023-2025'),
(5, 'BCA/2022/055', 1, 4, '2022-2025'),
(6, 'MCA/2023/018', 2, 2, '2023-2025'),
(7, 'BCA/2021/031', 1, 6, '2021-2024');
GO

INSERT INTO dbo.Coordinators (UserID, Department) VALUES
(2, 'Computer Science'),
(8, 'Information Technology');
GO

INSERT INTO dbo.CoordinatorAssignments (CoordID, CourseID, Semester) VALUES
(1, 1, 3),(1, 1, 4),(1, 1, 5),
(2, 2, 1),(2, 2, 2);
GO

-- BCA Subjects
INSERT INTO dbo.Subjects (SubjectCode, SubjectName, CourseID, Semester, IsElective) VALUES
('BCA-S1-CP',  'C Programming',        1, 1, 0),
('BCA-S1-MA',  'Mathematics I',        1, 1, 0),
('BCA-S2-OOP', 'OOP with Java',        1, 2, 0),
('BCA-S2-DS',  'Data Structures',      1, 2, 0),
('BCA-S3-DS2', 'Advanced DSA',         1, 3, 0),
('BCA-S3-DM',  'Discrete Mathematics', 1, 3, 0),
('BCA-S4-DB',  'DBMS',                 1, 4, 0),
('BCA-S4-OS',  'Operating Systems',    1, 4, 0),
('BCA-S4-CN',  'Computer Networks',    1, 4, 0),
('BCA-S4-WT',  'Web Technologies',     1, 4, 0),
('BCA-S4-AI',  'Elective: AI Basics',  1, 4, 1),
('BCA-S5-SE',  'Software Engineering', 1, 5, 0),
('BCA-S5-CC',  'Cloud Computing',      1, 5, 0),
('BCA-S5-IS',  'Elective: InfoSec',    1, 5, 1),
('BCA-S6-PJ',  'Project Work',         1, 6, 0),
('BCA-S6-IN',  'Industry Internship',  1, 6, 0),
-- MCA Subjects
('MCA-S1-AJ',  'Advanced Java',        2, 1, 0),
('MCA-S1-DM',  'Discrete Maths',       2, 1, 0),
('MCA-S2-ML',  'ML Basics',            2, 2, 0),
('MCA-S2-CC',  'Cloud Computing',      2, 2, 0),
('MCA-S2-SE',  'Software Engineering', 2, 2, 0),
('MCA-S2-AR',  'AR/VR Technologies',   2, 2, 1),
('MCA-S3-BD',  'Big Data Analytics',   2, 3, 0),
('MCA-S3-CY',  'Cybersecurity',        2, 3, 0),
('MCA-S4-PJ',  'Research Project',     2, 4, 0);
GO

INSERT INTO dbo.RegistrationPeriods (AcadYear, IsOpen, StartDate, EndDate)
VALUES ('2024-25', 1, CAST(GETDATE() AS DATE), DATEADD(DAY, 30, CAST(GETDATE() AS DATE)));
GO

INSERT INTO dbo.Registrations (StudentID, Semester, AcadYear, Status) VALUES
(1, 4, '2024-25', 'pending'),
(2, 2, '2024-25', 'pending'),
(3, 4, '2024-25', 'approved'),
(4, 2, '2024-25', 'approved'),
(5, 6, '2024-25', 'rejected');
GO

INSERT INTO dbo.RegistrationSubjects (RegID, SubjectID) VALUES
(1, 7),(1, 8),(1, 9),(1,10),
(2,19),(2,20),(2,21),
(3, 7),(3, 8),(3,10),
(4,19),(4,20),(4,21),(4,22),
(5,15),(5,16);
GO

PRINT 'SRMS_DB3 setup complete — v8: Fee receipt stored in database (FeeReceiptData column).';
GO

