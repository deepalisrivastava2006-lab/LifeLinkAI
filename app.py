
import os
import hmac
import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort
)
from dotenv import load_dotenv


# ==========================================
# 1. APP CONFIGURATION
# ==========================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY missing. Add it to your .env file."
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "lifelink.db")

os.makedirs(DATABASE_DIR, exist_ok=True)


# ==========================================
# 2. DATABASE CONNECTION
# ==========================================

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# 3. CREATE DATABASE TABLES
# ==========================================

def create_database():
    conn = get_db_connection()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS donors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                blood_group TEXT NOT NULL,
                city TEXT NOT NULL,
                phone TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS blood_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                blood_group TEXT NOT NULL,
                city TEXT NOT NULL,
                units INTEGER NOT NULL,
                urgency TEXT NOT NULL,
                hospital TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

    finally:
        conn.close()


# ==========================================
# 4. COMMON VALIDATION
# ==========================================

VALID_BLOOD_GROUPS = {
    "A+", "A-", "B+", "B-",
    "AB+", "AB-", "O+", "O-"
}

VALID_URGENCIES = {
    "Normal", "Urgent", "Emergency"
}

VALID_STATUSES = {
    "Pending", "In Progress", "Fulfilled"
}


# ==========================================
# 5. HOME PAGE
# ==========================================

@app.route("/")
def home():
    return render_template("index.html")


# ==========================================
# 6. DONOR REGISTRATION
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        blood_group = request.form.get(
            "blood_group", ""
        ).strip()
        city = request.form.get("city", "").strip()
        phone = request.form.get("phone", "").strip()

        if (
            not name
            or not city
            or not phone
            or blood_group not in VALID_BLOOD_GROUPS
        ):
            return "Please enter valid donor details.", 400

        conn = get_db_connection()

        try:
            conn.execute("""
                INSERT INTO donors
                (name, blood_group, city, phone)
                VALUES (?, ?, ?, ?)
            """, (name, blood_group, city, phone))

            conn.commit()

        finally:
            conn.close()

        return redirect(url_for("search"))

    return render_template("register.html")


# ==========================================
# 7. SEARCH BLOOD DONORS
# ==========================================

@app.route("/search", methods=["GET", "POST"])
def search():

    donors = []

    if request.method == "POST":
        blood_group = request.form.get(
            "blood_group", ""
        ).strip()
        city = request.form.get("city", "").strip()

        if (
            blood_group not in VALID_BLOOD_GROUPS
            or not city
        ):
            return "Please enter a valid blood group and city.", 400

        conn = get_db_connection()

        try:
            donors = conn.execute("""
                SELECT name, blood_group, city, phone
                FROM donors
                WHERE blood_group = ?
                AND LOWER(TRIM(city)) = LOWER(TRIM(?))
            """, (blood_group, city)).fetchall()

        finally:
            conn.close()

    return render_template("search.html", donors=donors)


# ==========================================
# 8. AI FIRST AID ASSISTANT
# ==========================================

@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():

    answer = ""

    if request.method == "POST":
        question = request.form.get(
            "question", ""
        ).strip()

        if not question:
            answer = "Please enter your question."

        elif len(question) > 2000:
            answer = "Please keep your question under 2000 characters."

        else:
            api_key = os.getenv("GEMINI_API_KEY")

            if not api_key:
                answer = (
                    "AI service is not configured. "
                    "Please add GEMINI_API_KEY to your .env file."
                )

            else:
                try:
                    from google import genai

                    client = genai.Client(api_key=api_key)

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=(
                            "You are a cautious first-aid information "
                            "assistant. Provide basic first-aid guidance, "
                            "not diagnosis or prescriptions. For serious "
                            "or life-threatening emergencies, advise the "
                            "user to contact emergency services immediately. "
                            "Never delay professional medical care. "
                            "User question: " + question
                        )
                    )

                    answer = response.text or (
                        "No response received. Please seek professional help."
                    )

                except Exception:
                    app.logger.exception(
                        "Gemini API request failed"
                    )

                    answer = (
                        "AI service is temporarily unavailable. "
                        "For a serious emergency, contact emergency "
                        "services immediately."
                    )

    return render_template(
        "chatbot.html",
        answer=answer
    )


# ==========================================
# 9. HOSPITALS
# ==========================================

@app.route("/hospitals")
def hospitals():
    return render_template("hospitals.html")


# ==========================================
# 10. EMERGENCY SOS
# ==========================================

@app.route("/emergency")
def emergency():
    return render_template("emergency.html")


# ==========================================
# 11. BLOOD AVAILABILITY DASHBOARD
# ==========================================

@app.route("/dashboard")
def dashboard():

    blood_counts = {
        group: 0 for group in VALID_BLOOD_GROUPS
    }

    conn = get_db_connection()

    try:
        results = conn.execute("""
            SELECT blood_group, COUNT(*) AS total
            FROM donors
            GROUP BY blood_group
        """).fetchall()

        for row in results:
            if row["blood_group"] in blood_counts:
                blood_counts[row["blood_group"]] = row["total"]

    finally:
        conn.close()

    return render_template(
        "dashboard.html",
        blood_counts=blood_counts
    )


# ==========================================
# 12. SUBMIT BLOOD REQUEST
# ==========================================

@app.route("/request-blood", methods=["GET", "POST"])
def request_blood():

    if request.method == "POST":
        patient_name = request.form.get(
            "patient_name", ""
        ).strip()
        blood_group = request.form.get(
            "blood_group", ""
        ).strip()
        city = request.form.get("city", "").strip()
        urgency = request.form.get("urgency", "").strip()
        hospital = request.form.get("hospital", "").strip()

        try:
            units = int(request.form.get("units", ""))
        except (ValueError, TypeError):
            return "Units must be a whole number.", 400

        if (
            not patient_name
            or not city
            or not hospital
            or blood_group not in VALID_BLOOD_GROUPS
            or urgency not in VALID_URGENCIES
            or not 1 <= units <= 20
        ):
            return "Please enter valid blood request details.", 400

        conn = get_db_connection()

        try:
            conn.execute("""
                INSERT INTO blood_requests
                (
                    patient_name,
                    blood_group,
                    city,
                    units,
                    urgency,
                    hospital
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                patient_name,
                blood_group,
                city,
                units,
                urgency,
                hospital
            ))

            conn.commit()

        finally:
            conn.close()

        return redirect(url_for("blood_requests"))

    return render_template("request_blood.html")


# ==========================================
# 13. VIEW PENDING BLOOD REQUESTS
# ==========================================

@app.route("/requests")
def blood_requests():

    conn = get_db_connection()

    try:
        requests_list = conn.execute("""
            SELECT
                id,
                patient_name,
                blood_group,
                city,
                units,
                urgency,
                hospital,
                status,
                created_at
            FROM blood_requests
            WHERE status = 'Pending'
            ORDER BY
                CASE urgency
                    WHEN 'Emergency' THEN 1
                    WHEN 'Urgent' THEN 2
                    ELSE 3
                END,
                id DESC
        """).fetchall()

    finally:
        conn.close()

    return render_template(
        "requests.html",
        requests=requests_list
    )


# ==========================================
# 14. ADMIN AUTHENTICATION
# ==========================================

def admin_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))

        return view(*args, **kwargs)

    return wrapped_view


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":
        password = request.form.get("password", "")
        expected_password = os.getenv("ADMIN_PASSWORD", "")

        if (
            expected_password
            and hmac.compare_digest(
                password, expected_password
            )
        ):
            session.clear()
            session["is_admin"] = True

            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Invalid admin password."
        ), 401

    return render_template("admin_login.html")


# ==========================================
# 15. ADMIN DASHBOARD
# ==========================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    conn = get_db_connection()

    try:
        requests_list = conn.execute("""
            SELECT
                id,
                patient_name,
                blood_group,
                city,
                units,
                urgency,
                hospital,
                status,
                created_at
            FROM blood_requests
            ORDER BY
                CASE urgency
                    WHEN 'Emergency' THEN 1
                    WHEN 'Urgent' THEN 2
                    ELSE 3
                END,
                id DESC
        """).fetchall()

    finally:
        conn.close()

    return render_template(
        "admin_dashboard.html",
        requests=requests_list
    )


# ==========================================
# FIND MATCHING DONORS FOR A BLOOD REQUEST
# ==========================================

@app.route("/admin/request/<int:request_id>/donors")
@admin_required
def find_matching_donors(request_id):

    conn = get_db_connection()

    try:
        # Fetch the blood request
        blood_request = conn.execute("""
            SELECT id, patient_name, blood_group,
                   city, units, urgency, hospital, status
            FROM blood_requests
            WHERE id = ?
        """, (request_id,)).fetchone()

        if blood_request is None:
            abort(404, "Blood request not found.")

        # Find donors matching blood group and city
        matching_donors = conn.execute("""
            SELECT id, name, blood_group, city
            FROM donors
            WHERE UPPER(TRIM(blood_group)) = ?
              AND LOWER(TRIM(city)) = LOWER(TRIM(?))
            ORDER BY name COLLATE NOCASE
        """, (
            blood_request["blood_group"].strip().upper(),
            blood_request["city"]
        )).fetchall()

    finally:
        conn.close()

    return render_template(
        "matching_donors.html",
        blood_request=blood_request,
        donors=matching_donors
    )

# ==========================================
# 16. UPDATE REQUEST STATUS
# ==========================================

@app.route(
    "/admin/request/<int:request_id>/status",
    methods=["POST"]
)
@admin_required
def update_request_status(request_id):

    new_status = request.form.get("status", "")

    allowed_statuses = {
        "Pending", "In Progress", "Fulfilled"
    }

    if new_status not in VALID_STATUSES:
        abort(400, "Invalid request status.")

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            UPDATE blood_requests
            SET status = ?
            WHERE id = ?
        """, (new_status, request_id))

        conn.commit()

        if cursor.rowcount == 0:
            abort(404, "Blood request not found.")

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


# ==========================================
# 17. ADMIN LOGOUT
# ==========================================

@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():

    session.clear()

    return redirect(url_for("admin_login"))


# ==========================================
# 18. INITIALIZE DATABASE
# ==========================================

create_database()


# ==========================================
# 19. RUN APPLICATION
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)