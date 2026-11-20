# CivicFix — Smart City Problem Reporter

A full-stack Flask + SQLite starter application for reporting and tracking local civic issues.

## Features
- Citizen registration and login (passwords are securely hashed)
- Submit reports for potholes, garbage, streetlights, water leakage, drainage and other issues
- Optional image upload (PNG/JPG/JPEG/WEBP, max 5 MB)
- Optional map coordinates captured from the browser
- Public report directory with category/status filters
- Report detail pages, comments and community support votes
- Admin dashboard and status changes (Open → In Progress → Resolved)
- Transparent priority score using a simple severity/urgency/impact heuristic
- Nearby same-category report warning when coordinates are within about 100 metres

## Run on Windows (VS Code)
1. Install Python 3.10 or newer.
2. Extract this ZIP and open the `CivicFix_Full_Stack` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:
   ```powershell
   py -m venv venv
   .\venv\Scripts\activate
   ```
5. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
6. Start the app:
   ```powershell
   python app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

The SQLite database is created automatically on first run.

## Demo admin login
- Email: `admin@civicfix.local`
- Password: `Admin123!`

Change this password and set a strong `SECRET_KEY` before deploying publicly. For example, set the `SECRET_KEY` environment variable before running the app.

## Project structure
```text
CivicFix_Full_Stack/
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── reports.html
│   ├── new_report.html
│   ├── report_detail.html
│   └── admin.html
└── static/
    ├── css/style.css
    └── uploads/
```

## Notes / next steps
This is a hackathon-ready local prototype, not a production deployment. Before public launch, add CSRF protection, rate limiting, email verification, stronger admin provisioning, database migrations, moderation, backups and cloud object storage. The demo admin credentials are intentionally provided for local evaluation only.
