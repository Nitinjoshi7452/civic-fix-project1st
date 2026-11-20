import os, sqlite3, uuid, math
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "civicfix.db")
UPLOAD_DIR = os.path.join(ROOT, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CATEGORIES = ["Pothole", "Garbage", "Streetlight", "Water Leakage", "Drainage", "Other"]
STATUSES = ["Open", "In Progress", "Resolved"]

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'citizen',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        address TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        image TEXT,
        status TEXT NOT NULL DEFAULT 'Open',
        priority REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        UNIQUE(report_id, user_id),
        FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    # Demo admin: admin@civicfix.local / Admin123!
    exists = conn.execute("SELECT id FROM users WHERE email=?", ("admin@civicfix.local",)).fetchone()
    if not exists:
        conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                     ("CivicFix Admin", "admin@civicfix.local", generate_password_hash("Admin123!"), "admin", datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_priority(category, description):
    # Transparent starter heuristic: category severity + urgency keywords.
    severity = {"Pothole": 8, "Water Leakage": 8, "Streetlight": 5, "Drainage": 7, "Garbage": 5, "Other": 3}.get(category, 3)
    urgent_words = ["accident", "danger", "urgent", "school", "hospital", "blocked", "overflow"]
    urgency = min(10, 3 + sum(1 for word in urgent_words if word in description.lower()) * 2)
    impact = 7 if category in ("Pothole", "Water Leakage", "Drainage") else 5
    return round(0.50 * severity + 0.25 * urgency + 0.25 * impact, 2)

def report_query(where="", params=()):
    return db().execute(f"""
        SELECT r.*, u.name AS reporter,
        (SELECT COUNT(*) FROM votes v WHERE v.report_id=r.id) AS votes
        FROM reports r JOIN users u ON u.id=r.user_id
        {where} ORDER BY CASE r.status WHEN 'Open' THEN 0 WHEN 'In Progress' THEN 1 ELSE 2 END,
        r.priority DESC, r.created_at DESC
    """, params).fetchall()

@app.route("/")
def index():
    reports = report_query("WHERE r.status != 'Resolved'")[:6]
    stats = db().execute("""
        SELECT COUNT(*) total,
        SUM(CASE WHEN status='Open' THEN 1 ELSE 0 END) open_count,
        SUM(CASE WHEN status='In Progress' THEN 1 ELSE 0 END) progress_count,
        SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END) resolved_count
        FROM reports
    """).fetchone()
    return render_template("index.html", reports=reports, stats=stats)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email, and a password of at least 8 characters.", "danger")
        else:
            try:
                db().execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                             (name, email, generate_password_hash(password), datetime.now().isoformat(timespec="seconds")))
                db().commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            flash("Welcome back!", "success")
            return redirect(url_for("admin") if user["role"] == "admin" else url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    reports = report_query("WHERE r.user_id=?", (session["user_id"],))
    return render_template("dashboard.html", reports=reports)

@app.route("/reports")
def reports():
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    clauses, params = [], []
    if category in CATEGORIES:
        clauses.append("r.category=?"); params.append(category)
    if status in STATUSES:
        clauses.append("r.status=?"); params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return render_template("reports.html", reports=report_query(where, params), categories=CATEGORIES, statuses=STATUSES,
                           selected_category=category, selected_status=status)

@app.route("/report/new", methods=["GET", "POST"])
@login_required
def new_report():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        address = request.form.get("address", "").strip()
        lat = request.form.get("latitude") or None
        lng = request.form.get("longitude") or None
        if not title or not description or category not in CATEGORIES or not address:
            flash("Please complete all required fields.", "danger")
            return render_template("new_report.html", categories=CATEGORIES)
        image_name = None
        upload = request.files.get("image")
        if upload and upload.filename:
            if not allowed_file(upload.filename):
                flash("Upload a PNG, JPG, JPEG, or WEBP image.", "danger")
                return render_template("new_report.html", categories=CATEGORIES)
            ext = secure_filename(upload.filename).rsplit(".", 1)[1].lower()
            image_name = f"{uuid.uuid4().hex}.{ext}"
            upload.save(os.path.join(UPLOAD_DIR, image_name))
        try:
            lat_val = float(lat) if lat else None
            lng_val = float(lng) if lng else None
        except ValueError:
            lat_val = lng_val = None
        priority = calculate_priority(category, description)
        # Flag similar reports within approximately 100m and same category.
        possible_duplicate = False
        if lat_val is not None and lng_val is not None:
            recent = db().execute("SELECT latitude,longitude FROM reports WHERE category=? AND created_at >= datetime('now','-30 days')",
                                  (category,)).fetchall()
            for item in recent:
                if item["latitude"] is not None and item["longitude"] is not None:
                    dlat = (lat_val - item["latitude"]) * 111000
                    dlng = (lng_val - item["longitude"]) * 111000 * math.cos(math.radians(lat_val))
                    if math.sqrt(dlat*dlat + dlng*dlng) <= 100:
                        possible_duplicate = True
                        break
        now = datetime.now().isoformat(timespec="seconds")
        cur = db().execute("""INSERT INTO reports(user_id,title,description,category,address,latitude,longitude,image,priority,created_at,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                           (session["user_id"], title, description, category, address, lat_val, lng_val, image_name, priority, now, now))
        db().commit()
        flash("Report submitted successfully." + (" A similar nearby report may already exist; please check the reports list." if possible_duplicate else ""), "success")
        return redirect(url_for("report_detail", report_id=cur.lastrowid))
    return render_template("new_report.html", categories=CATEGORIES)

@app.route("/report/<int:report_id>")
def report_detail(report_id):
    report = db().execute("""SELECT r.*,u.name reporter,
        (SELECT COUNT(*) FROM votes WHERE report_id=r.id) votes
        FROM reports r JOIN users u ON u.id=r.user_id WHERE r.id=?""", (report_id,)).fetchone()
    if not report:
        flash("Report not found.", "danger")
        return redirect(url_for("reports"))
    comments = db().execute("SELECT c.*,u.name FROM comments c JOIN users u ON u.id=c.user_id WHERE c.report_id=? ORDER BY c.created_at", (report_id,)).fetchall()
    voted = False
    if session.get("user_id"):
        voted = bool(db().execute("SELECT id FROM votes WHERE report_id=? AND user_id=?", (report_id, session["user_id"])).fetchone())
    return render_template("report_detail.html", report=report, comments=comments, voted=voted)

@app.route("/report/<int:report_id>/vote", methods=["POST"])
@login_required
def vote(report_id):
    try:
        db().execute("INSERT INTO votes(report_id,user_id) VALUES(?,?)", (report_id, session["user_id"]))
        db().commit()
        flash("Your support has been recorded.", "success")
    except sqlite3.IntegrityError:
        db().execute("DELETE FROM votes WHERE report_id=? AND user_id=?", (report_id, session["user_id"]))
        db().commit()
        flash("Your support was removed.", "info")
    return redirect(url_for("report_detail", report_id=report_id))

@app.route("/report/<int:report_id>/comment", methods=["POST"])
@login_required
def comment(report_id):
    body = request.form.get("body", "").strip()
    exists = db().execute("SELECT id FROM reports WHERE id=?", (report_id,)).fetchone()
    if body and exists:
        db().execute("INSERT INTO comments(report_id,user_id,body,created_at) VALUES(?,?,?,?)",
                     (report_id, session["user_id"], body[:1000], datetime.now().isoformat(timespec="seconds")))
        db().commit()
    return redirect(url_for("report_detail", report_id=report_id))

@app.route("/admin")
@admin_required
def admin():
    reports = report_query()
    stats = db().execute("""SELECT COUNT(*) total,
        SUM(status='Open') open_count, SUM(status='In Progress') progress_count,
        SUM(status='Resolved') resolved_count FROM reports""").fetchone()
    return render_template("admin.html", reports=reports, stats=stats, statuses=STATUSES)

@app.route("/admin/report/<int:report_id>/status", methods=["POST"])
@admin_required
def update_status(report_id):
    status = request.form.get("status")
    if status in STATUSES:
        db().execute("UPDATE reports SET status=?,updated_at=? WHERE id=?",
                     (status, datetime.now().isoformat(timespec="seconds"), report_id))
        db().commit()
        flash("Report status updated.", "success")
    return redirect(url_for("admin"))

@app.errorhandler(413)
def too_large(error):
    flash("Image is too large. Maximum upload size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("new_report"))

@app.context_processor
def inject_globals():
    return {"current_user": session, "categories": CATEGORIES}

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
