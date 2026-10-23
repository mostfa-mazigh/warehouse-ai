# ===================== PROFESSIONAL WAREHOUSE AI LOGISTICS SYSTEM v6.0 AGENT =====================
# COMPLETE ENTERPRISE SYSTEM WITH EVERYTHING
# - QR Code Generation & Scanning (including LIVE camera scanning to add/check containers)
# - Real Warehouse SVG Map (150m x 100m with 6 Zones)
# - Container Details on Hover
# - Complete Database Page
# - Utilization Analytics
# - Exit Schedule Management
# - AI Chatbot as its own dedicated section, powered by Groq (fast free-tier LLM
#   inference on open models) with Retrieval-Augmented Generation (RAG) over the
#   live warehouse database
# - Professional Financial Dashboard with KPIs
# - USD/TND Currency Support
# Founded: April 13, 2026

from flask import Flask, render_template_string, jsonify, request, redirect, session, abort
import re
import math
import time as _t0
from collections import deque as _deque
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
import random
import json
import sqlite3
import os
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(ENV_PATH)

def _ensure_secrets():
    """First-run bootstrap: if the access token / session key are missing, generate them and
    save them to .env so the secret link and logins stay stable across restarts."""
    import secrets as _s
    new = {}
    if not os.environ.get('WAREHOUSE_ACCESS_TOKEN'):
        new['WAREHOUSE_ACCESS_TOKEN'] = _s.token_urlsafe(24)
    if not os.environ.get('WAREHOUSE_SECRET_KEY'):
        new['WAREHOUSE_SECRET_KEY'] = _s.token_hex(32)
    if new:
        os.environ.update(new)
        try:
            prefix = ''
            if os.path.exists(ENV_PATH) and os.path.getsize(ENV_PATH) > 0:
                with open(ENV_PATH, 'rb') as f:
                    f.seek(-1, os.SEEK_END)
                    prefix = '' if f.read(1) == b'\n' else '\n'
            with open(ENV_PATH, 'a', encoding='utf-8') as f:
                f.write(prefix + ''.join(f"{k}={v}\n" for k, v in new.items()))
            print(f"[setup] Generated {', '.join(new)} and saved to {ENV_PATH}")
        except OSError as e:
            print(f"[setup] Could not write .env ({e}); secrets are valid for this run only.")
    return list(new)

_ensure_secrets()
import secrets
import uuid
from collections import defaultdict
import qrcode
import io
import base64
import requests
try:  # scikit-learn is optional: without it, retrieval falls back to a tiny built-in TF-IDF
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    HAVE_SKLEARN = True
except ImportError:
    HAVE_SKLEARN = False

app = Flask(__name__)
# Same-origin app: no CORS by default (a credentialed wildcard CORS policy would be unsafe on a public
# host). Set CORS_ORIGINS=https://a.com,https://b.com only if a separate front-end needs the API.
if os.environ.get('CORS_ORIGINS'):
    from flask_cors import CORS
    CORS(app, supports_credentials=True, origins=[o.strip() for o in os.environ['CORS_ORIGINS'].split(',')])
# Behind a host's HTTPS proxy (Render, etc.) so redirects/cookies see the real scheme.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
DEMO_OPEN_ACCESS = os.environ.get('DEMO_OPEN_ACCESS', '0') == '1'   # public demo: no secret link needed
PUBLIC_MODE = os.environ.get('PUBLIC_MODE', '0') == '1'      # disables the destructive /api/clear
MAX_CONTAINERS = int(os.environ.get('MAX_CONTAINERS', '5000'))  # protects small free-tier hosts

# ===================== SECRET-LINK ACCESS =====================
# This site has no per-person login. Instead, ONE secret link grants full access to
# anyone who has it (meant for a small warehouse team sharing one URL, not a public
# audience). Visiting /access/<ACCESS_TOKEN> sets a signed session cookie in that
# browser; every other route checks for that cookie and returns a plain 404 (not a
# 403) if it's missing, so the site doesn't even reveal that a hidden door exists.
#
# The token is read from the WAREHOUSE_ACCESS_TOKEN environment variable so it stays
# stable across restarts. If that variable isn't set, a random token is generated
# each time the app starts and printed to the console — fine for a quick test, but
# set the env var for anything longer-lived.
ACCESS_TOKEN = os.environ.get('WAREHOUSE_ACCESS_TOKEN') or secrets.token_urlsafe(24)

# Flask signs the session cookie with this key so it can't be forged or edited by the
# person holding it. Set WAREHOUSE_SECRET_KEY yourself in production so sessions
# survive an app restart; otherwise a new key (and therefore logged-out browsers) is
# generated every time the process starts.
app.secret_key = os.environ.get('WAREHOUSE_SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,   # not readable from page JavaScript
    SESSION_COOKIE_SAMESITE='Lax',  # not sent on cross-site requests
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',  # set COOKIE_SECURE=1 on HTTPS hosts
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    # SESSION_COOKIE_SECURE=True,   # uncomment once served only over HTTPS
)

# Routes reachable WITHOUT the access-granting cookie. Keep this list minimal.
PUBLIC_PATHS = {'/favicon.ico'}

@app.before_request
def _require_site_access():
    if DEMO_OPEN_ACCESS:
        session.permanent = True
        session['warehouse_access_ok'] = True
        return
    if request.path.startswith(f'/access/{ACCESS_TOKEN}'):
        return  # this is the secret link itself; handled by its own route below
    if request.path in PUBLIC_PATHS:
        return
    if session.get('warehouse_access_ok'):
        return  # this browser already used the secret link
    abort(404)  # no hint that a hidden route exists

@app.route('/access/<token>')
def grant_access(token):
    # Constant-time compare so response timing can't be used to guess the token
    # character-by-character.
    if secrets.compare_digest(token, ACCESS_TOKEN):
        session.permanent = True
        session['warehouse_access_ok'] = True
        return redirect('/')
    abort(404)

# ===================== CONFIGURATION =====================
COMPANY_CONFIG = {
    "name": "Warehouse AI Logistics Inc.",
    "description": "Advanced AI-powered intelligent warehouse management platform",
    "founding_date": "September 27",
    "founding_year": 2026,
    "version": "6.0",
    "license": "Enterprise",
    "email": "mustapha28.mazigh@gmail.com",
    "phone": "+21628039777",
    "website": "https://www.warehouseai.com",
    "city": "Tunis",
    "country": "Tunisia",
    "address": "3 Oran Street, Medina Jedida, Tunis, Tunisia",
    "founder": "Mustapha Mazigh",
    "team_name": "GLG",
    "daily_operational_cost": 3500,
    "theft_prevention_value_per_container": 500,
    "loss_prevention_value_per_container": 300,
    "insurance_savings_percentage": 0.15,
    "processing_fee_per_container": 150,
    "currency": "TND",
    "exchange_rate_usd_to_tnd": 3.15,
    "warehouse_length_m": 150,
    "warehouse_width_m": 100,
}

DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'warehouse_v54.db')

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS containers (
        id TEXT PRIMARY KEY,
        qr_code TEXT,
        order_number INTEGER,
        entry_date TEXT NOT NULL,
        exit_date TEXT,
        status TEXT DEFAULT 'in_warehouse',
        contents TEXT NOT NULL,
        weight REAL NOT NULL,
        risk_level TEXT,
        fragility REAL,
        warehouse_x REAL,
        warehouse_y REAL,
        zone TEXT,
        temperature REAL,
        humidity REAL,
        utilization_percentage REAL,
        gate_problems TEXT,
        scheduled_exit_date TEXT,
        container_value REAL DEFAULT 5000,
        last_scanned TEXT,
        scan_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS qr_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_id TEXT NOT NULL,
        scan_time TEXT,
        scan_location TEXT,
        scan_details TEXT,
        FOREIGN KEY(container_id) REFERENCES containers(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_id TEXT NOT NULL,
        alert_type TEXT,
        alert_message TEXT,
        severity TEXT,
        is_resolved INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(container_id) REFERENCES containers(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS gate_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_id TEXT NOT NULL,
        gate_type TEXT,
        scan_time TEXT,
        problems TEXT,
        FOREIGN KEY(container_id) REFERENCES containers(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS location_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_id TEXT NOT NULL,
        x REAL,
        y REAL,
        z INTEGER,
        timestamp TEXT,
        FOREIGN KEY(container_id) REFERENCES containers(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS financial_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_date TEXT NOT NULL,
        transaction_type TEXT,
        description TEXT,
        amount_usd REAL,
        amount_tnd REAL,
        container_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(container_id) REFERENCES containers(id)
    )''')

    conn.commit()
    conn.close()

init_database()

# ===================== QR CODE GENERATOR =====================
# QR payload format used by this app: a JSON object carrying EVERY field needed to fully
# reconstruct the container, e.g.:
#   {
#     "app": "WAREHOUSE_AI", "id": "CONT_DEMO_001", "contents": "electronics",
#     "weight": 8452.3, "risk_level": "high", "fragility": 0.62, "zone": "B",
#     "warehouse_x": 63.4, "warehouse_y": 12.7, "temperature": 21.5, "humidity": 55.2,
#     "utilization_percentage": 88.0, "gate_problems": "None", "priority": 3,
#     "container_value": 24500.0, "timestamp": "..."
#   }
# This means a container can be fully registered from its QR code alone, with no random
# guessing needed. For backward compatibility, the legacy "WAREHOUSE_AI|<id>|<timestamp>"
# pipe format is still accepted when scanning (missing fields are then filled randomly).

QR_PREFIX = "WAREHOUSE_AI"

def build_qr_payload(fields):
    """Build the full-info JSON string encoded into a container's QR code."""
    payload = {
        "app": QR_PREFIX,
        "id": fields["id"],
        "contents": fields["contents"],
        "weight": fields["weight"],
        "risk_level": fields["risk_level"],
        "fragility": fields["fragility"],
        "zone": fields["zone"],
        "warehouse_x": fields["warehouse_x"],
        "warehouse_y": fields["warehouse_y"],
        "temperature": fields["temperature"],
        "humidity": fields["humidity"],
        "utilization_percentage": fields["utilization_percentage"],
        "gate_problems": fields["gate_problems"],
        "priority": fields["priority"],
        "container_value": fields["container_value"],
        "timestamp": datetime.now().isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False)

def generate_qr_image(payload_str):
    """Render a JSON (or any) payload string into a QR code, returned as a base64 data URI."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(payload_str)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return f"data:image/png;base64,{img_str}"

def parse_qr_payload(qr_data):
    """Parse a scanned QR string (from camera or an uploaded image).
    Returns a dict with at least an 'id' key, or None if unrecognized.
    Accepts both the full-info JSON format and the legacy pipe format."""
    if not qr_data:
        return None
    qr_data = qr_data.strip()

    # Preferred: full-info JSON payload
    try:
        data = json.loads(qr_data)
        if isinstance(data, dict) and data.get("app") == QR_PREFIX and data.get("id"):
            return data
    except (ValueError, TypeError):
        pass

    # Legacy fallback: "WAREHOUSE_AI|<container_id>|<timestamp>"
    parts = qr_data.split('|')
    if len(parts) >= 2 and parts[0] == QR_PREFIX:
        container_id = parts[1].strip()
        if container_id:
            return {"id": container_id}

    return None

# ===================== ZONE SYSTEM =====================

class ZoneSystem:
    ZONES = {
        'A': {'x': 0, 'y': 0, 'width': 50, 'height': 50, 'name': 'Reception Zone', 'color': '#C6551A'},
        'B': {'x': 50, 'y': 0, 'width': 50, 'height': 50, 'name': 'Primary Storage', 'color': '#2B5C7A'},
        'C': {'x': 100, 'y': 0, 'width': 50, 'height': 50, 'name': 'Cold Storage', 'color': '#3F7A68'},
        'D': {'x': 0, 'y': 50, 'width': 50, 'height': 50, 'name': 'High-Value Storage', 'color': '#7A4B6B'},
        'E': {'x': 50, 'y': 50, 'width': 50, 'height': 50, 'name': 'Archive Storage', 'color': '#6B6558'},
        'F': {'x': 100, 'y': 50, 'width': 50, 'height': 50, 'name': 'Dispatch Area', 'color': '#B8862B'},
    }

    @staticmethod
    def get_zone(x, y):
        for zone_id, zone in ZoneSystem.ZONES.items():
            if zone['x'] <= x < zone['x'] + zone['width'] and zone['y'] <= y < zone['y'] + zone['height']:
                return zone_id
        return 'A'

# ===================== CONTAINER CLASS =====================

class Container:
    """A warehouse container. Every container in this system is created exclusively
    from data decoded out of a scanned QR code — see from_scanned_data() below. There
    is intentionally no path that fabricates a container with random data end-to-end;
    random values are only used as a last-resort fallback for individual fields a
    scanned QR code happens to omit (see from_scanned_data)."""
    counter = 0

    @staticmethod
    def _risk_for_contents(contents):
        risk_map = {
            "fragile": "high", "electronics": "high", "chemicals": "critical",
            "heavy_machinery": "medium", "textiles": "low", "mixed": "medium"
        }
        return risk_map.get(contents, "medium")

    def _qr_fields(self):
        """The full set of fields encoded into this container's QR code."""
        return {
            "id": self.id,
            "contents": self.contents,
            "weight": self.weight,
            "risk_level": self.risk_level,
            "fragility": self.fragility,
            "zone": self.zone,
            "warehouse_x": self.warehouse_x,
            "warehouse_y": self.warehouse_y,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "utilization_percentage": self.utilization_percentage,
            "gate_problems": self.gate_problems,
            "priority": self.priority,
            "container_value": self.container_value,
        }

    @classmethod
    def from_scanned_data(cls, data):
        """Reconstruct a container entirely from data decoded out of a QR code.
        Any field not present in the QR payload (e.g. an older/legacy QR that only
        carries the ID) is filled in with a sensible random default, exactly like
        the simulator does, so the container is always fully usable."""
        container_id = data.get("id")
        if not container_id:
            return None

        obj = cls.__new__(cls)
        Container.counter += 1
        obj.order_number = Container.counter
        obj.id = str(container_id)
        obj.entry_date = datetime.now()
        obj.exit_date = None
        obj.status = "in_warehouse"

        obj.contents = data.get("contents") or random.choice(
            ["fragile", "electronics", "heavy_machinery", "textiles", "mixed", "chemicals"])
        obj.weight = float(data.get("weight", round(random.uniform(1000, 25000), 2)))
        obj.risk_level = data.get("risk_level") or Container._risk_for_contents(obj.contents)
        obj.fragility = float(data.get("fragility", round(random.uniform(0.1, 0.95), 2)))
        obj.warehouse_x = float(data.get("warehouse_x", round(random.uniform(0, 150), 2)))
        obj.warehouse_y = float(data.get("warehouse_y", round(random.uniform(0, 100), 2)))
        obj.zone = data.get("zone") or ZoneSystem.get_zone(obj.warehouse_x, obj.warehouse_y)
        obj.temperature = float(data.get("temperature", round(random.uniform(15, 28), 1)))
        obj.humidity = float(data.get("humidity", round(random.uniform(30, 80), 1)))
        obj.utilization_percentage = float(data.get("utilization_percentage", round(random.uniform(60, 100), 1)))
        obj.gate_problems = data.get("gate_problems") or "None"
        obj.priority = int(data.get("priority", random.randint(1, 7)))
        obj.scheduled_exit_date = datetime.now() + timedelta(days=obj.priority)
        obj.scan_count = 1
        obj.container_value = float(data.get("container_value", round(random.uniform(3000, 50000), 2)))
        obj.last_scanned = datetime.now()
        obj.qr_code = generate_qr_image(build_qr_payload(obj._qr_fields()))
        return obj

    def save_to_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''INSERT OR REPLACE INTO containers
                     (id, qr_code, order_number, entry_date, exit_date, status, contents, weight, risk_level,
                      fragility, warehouse_x, warehouse_y, zone, temperature, humidity,
                      utilization_percentage, gate_problems, scheduled_exit_date, container_value, last_scanned, scan_count)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (self.id, self.qr_code, self.order_number, self.entry_date.isoformat(),
                   self.exit_date.isoformat() if self.exit_date else None,
                   self.status, self.contents, self.weight, self.risk_level,
                   self.fragility, self.warehouse_x, self.warehouse_y, self.zone,
                   self.temperature, self.humidity, self.utilization_percentage,
                   self.gate_problems, self.scheduled_exit_date.isoformat(), self.container_value,
                   self.last_scanned.isoformat(), self.scan_count))

        conn.commit()
        conn.close()

    def to_dict(self):
        time_in = (self.exit_date if self.exit_date else datetime.now()) - self.entry_date
        hours = time_in.total_seconds() / 3600
        return {
            "id": self.id,
            "order_number": self.order_number,
            "qr_code": self.qr_code,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "status": self.status,
            "contents": self.contents,
            "weight": self.weight,
            "risk_level": self.risk_level,
            "fragility": round(self.fragility * 100, 1),
            "location": {"x": self.warehouse_x, "y": self.warehouse_y, "zone": self.zone},
            "temperature": self.temperature,
            "humidity": self.humidity,
            "utilization": self.utilization_percentage,
            "gate_problems": self.gate_problems,
            "time_in_hours": round(hours, 1),
            "priority": self.priority,
            "scheduled_exit_date": self.scheduled_exit_date.isoformat(),
            "scan_count": self.scan_count,
            "container_value": self.container_value,
            "last_scanned": self.last_scanned.isoformat()
        }

RAG_TOP_K = 8   # retrieval is now just ONE of the agent's tools (search_knowledge)

def build_knowledge_documents(warehouse_obj):
    """Turn the current warehouse state into a list of (doc_id, text) documents.
    This is the 'knowledge base' the RAG retriever searches over. It's rebuilt on every
    chat request (rather than kept in a persistent vector index) because container data
    changes constantly here — every QR scan can add/update a container — and rebuilding
    a TF-IDF index over a few hundred short text documents takes milliseconds. If this
    warehouse ever holds many thousands of containers, this is the place to add caching
    (e.g. rebuild only every N seconds, or on every scan/checkout instead of every chat
    message) rather than doing it per-request.
    """
    stats = warehouse_obj.get_stats()
    fin = stats['financial']
    docs = []

    docs.append(("summary",
        f"Warehouse summary: {stats['total']} total containers, {stats['checked_in']} "
        f"currently in the warehouse, {stats['checked_out']} processed/exited. Average "
        f"space utilization is {stats['avg_utilization']}%. There are "
        f"{len(stats['alerts'])} active alerts right now."))

    docs.append(("financial",
        f"Financial performance: total revenue is ${fin['revenue']['total_usd']:,.0f} "
        f"(processing fees ${fin['revenue']['processing_usd']:,.0f}, theft prevention "
        f"${fin['revenue']['theft_prevention_usd']:,.0f}, loss prevention "
        f"${fin['revenue']['loss_prevention_usd']:,.0f}, insurance savings "
        f"${fin['revenue']['insurance_usd']:,.0f}, high-risk premiums "
        f"${fin['revenue']['high_risk_usd']:,.0f}). Total operating costs are "
        f"${fin['costs']['total_usd']:,.0f}. Net profit is ${fin['profit']['net_usd']:,.0f} "
        f"with a {fin['profit']['margin']}% margin and {fin['kpis']['roi_percentage']}% ROI. "
        f"Average container value is ${fin['kpis']['avg_container_value']:,.0f}."))

    for zone_id, zone in ZoneSystem.ZONES.items():
        count = stats['zone_dist'].get(zone_id, 0)
        docs.append((f"zone_{zone_id}",
            f"Zone {zone_id} is the {zone['name']}, spanning x={zone['x']}-{zone['x']+zone['width']}m, "
            f"y={zone['y']}-{zone['y']+zone['height']}m of the warehouse floor. It currently holds "
            f"{count} container{'s' if count != 1 else ''}."))

    for alert in stats['alerts'][:25]:
        docs.append((f"alert_{alert['id']}",
            f"Active {alert['severity']} alert (id {alert['id']}) on container "
            f"{alert['container_id']}: {alert['alert_type']} — {alert['alert_message']}"))

    for c in warehouse_obj.containers.values():
        cd = c.to_dict()
        text = (
            f"Container #{cd['order_number']} with ID {cd['id']} is {cd['status']} in "
            f"Zone {cd['location']['zone']} at coordinates ({cd['location']['x']}m, "
            f"{cd['location']['y']}m). It contains {cd['contents']} weighing {cd['weight']} kg "
            f"with a {cd['risk_level']} risk level and {cd['fragility']}% fragility. Its "
            f"declared value is ${cd['container_value']:,.2f}. Current conditions: "
            f"{cd['temperature']}°C and {cd['humidity']}% humidity, {cd['utilization']}% "
            f"space utilization. Gate check status: {cd['gate_problems']}. Priority level "
            f"{cd['priority']}/7. Entered the warehouse on {cd['entry_date'][:10]}, scheduled "
            f"to exit on {cd['scheduled_exit_date'][:10]}. It has been scanned "
            f"{cd['scan_count']} time(s), last scanned at "
            f"{cd['last_scanned'][:19].replace('T', ' ')}."
        )
        docs.append((cd['id'], text))

    return docs


_STOP = set("the a an of in on at to is are was were be and or for with by it its this that what which who how many much do does "
            "me my show tell about from as".split())

def _simple_tfidf_scores(texts, query):
    """Dependency-free TF-IDF-style scoring (used when scikit-learn isn't installed)."""
    tok = lambda t: [w for w in re.findall(r"[a-z0-9_#.\-]+", t.lower()) if w not in _STOP]
    docs = [tok(t) for t in texts]
    q = set(tok(query))
    n = len(docs)
    df = {w: sum(1 for d in docs if w in d) for w in q}
    scores = []
    for d in docs:
        ds = set(d)
        sc = sum(math.log((n + 1) / (df[w] + 1)) + 1 for w in q if w in ds)
        scores.append(sc / math.sqrt(len(d) or 1))
    return scores


def retrieve_relevant_context(query, warehouse_obj, top_k=RAG_TOP_K):
    """The RETRIEVE step of RAG. Scores every document from build_knowledge_documents()
    against the user's query with TF-IDF (term frequency–inverse document frequency)
    vectors and cosine similarity, then returns the text of the best-matching ones
    joined together as a single context block. The two aggregate 'summary' and
    'financial' documents are always included so the model has global counts on hand
    even when the question is about one specific container."""
    documents = build_knowledge_documents(warehouse_obj)
    if not documents:
        return "The warehouse currently has no containers or data recorded yet."

    ids = [doc_id for doc_id, _ in documents]
    texts = [text for _, text in documents]
    always_include_ids = {"summary", "financial"}

    if HAVE_SKLEARN:
        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform(texts + [query])
            query_vector = tfidf_matrix[-1]
            document_vectors = tfidf_matrix[:-1]
            similarities = cosine_similarity(query_vector, document_vectors).flatten()
        except ValueError:
            # Can happen if every document and the query are empty/only stop-words.
            similarities = [0.0] * len(texts)
    else:
        similarities = _simple_tfidf_scores(texts, query)

    ranked = sorted(zip(ids, texts, similarities), key=lambda item: item[2], reverse=True)

    forced_texts = [text for doc_id, text in documents if doc_id in always_include_ids]
    retrieved_texts = []
    for doc_id, text, _score in ranked:
        if doc_id in always_include_ids:
            continue
        if len(retrieved_texts) >= top_k:
            break
        retrieved_texts.append(text)

    return "\n".join(forced_texts + retrieved_texts)




# ===================== AGENT CORE (v6.0) =====================
# This block REPLACES the old RAG-only chatbot. The assistant is now an agent:
#   * it has TOOLS (read + write) that wrap the real WarehouseSystem methods,
#   * it runs a reason -> call tool -> observe -> repeat loop until it can answer,
#   * every WRITE action is queued for human approval (unless AGENT_AUTONOMY=auto),
#   * every tool call / approval is written to an audit table (agent_log),
#   * a background monitor watches the warehouse and posts insights without being asked.
import threading
import time as _time
from collections import deque

# ---- AI provider: any OpenAI-compatible chat API, or none (offline agent) ----
# .env examples:
#   (nothing)                                  -> offline agent, zero setup
#   LLM_PROVIDER=ollama   LLM_MODEL=qwen2.5:7b -> free, local, private (install Ollama, `ollama pull qwen2.5:7b`)
#   LLM_PROVIDER=openrouter LLM_API_KEY=...  LLM_MODEL=<a tool-calling model id>
#   LLM_PROVIDER=gemini     LLM_API_KEY=...  LLM_MODEL=<model id>
#   LLM_PROVIDER=groq       LLM_API_KEY=...  (old GROQ_API_KEY / GROQ_MODEL still work)
#   LLM_BASE_URL=https://.../v1/chat/completions  (any other OpenAI-compatible service)
LLM_PRESETS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
}
LLM_API_KEY = os.environ.get('LLM_API_KEY') or os.environ.get('GROQ_API_KEY')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', '').strip().lower()
if not LLM_PROVIDER:
    LLM_PROVIDER = 'custom' if os.environ.get('LLM_BASE_URL') else ('groq' if LLM_API_KEY else 'offline')
LLM_URL = os.environ.get('LLM_BASE_URL') or LLM_PRESETS.get(LLM_PROVIDER)
_m = (os.environ.get('LLM_MODEL') or os.environ.get('GROQ_MODEL') or '').strip()
_m = '' if _m.lower() in ('auto', '-', 'none', 'default') else _m   # "auto" = let the app discover a model
LLM_MODEL_PINNED = _m or (
    'qwen2.5:7b' if LLM_PROVIDER == 'ollama' and not os.environ.get('LLM_AUTO_MODEL') else None)
LLM_MODEL = LLM_MODEL_PINNED          # kept for older references; None means "auto-discover"
LLM_ENABLED = bool(LLM_PROVIDER != 'offline' and LLM_URL and (LLM_PROVIDER in ('ollama', 'custom') or LLM_API_KEY))
LLM_PROBLEM = None
if LLM_PROVIDER != 'offline' and not LLM_ENABLED:
    LLM_PROBLEM = f"LLM_PROVIDER={LLM_PROVIDER} needs LLM_API_KEY; running in offline mode."

AGENT_MAX_STEPS = int(os.environ.get('AGENT_MAX_STEPS', '6'))
# "ask"  (default): write actions wait for the user to click Approve.
# "auto": write actions execute immediately (use only on a trusted/demo setup).
AGENT_AUTONOMY = os.environ.get('AGENT_AUTONOMY', 'ask').lower()
AGENT_MONITOR_SECONDS = int(os.environ.get('AGENT_MONITOR_SECONDS', '60'))

WRITE_LOCK = threading.RLock()


def _init_agent_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS agent_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, kind TEXT, tool TEXT, args TEXT, result TEXT, status TEXT)''')
    conn.commit()
    conn.close()


def agent_log(kind, tool, args, result, status="ok"):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO agent_log (ts, kind, tool, args, result, status) VALUES (?,?,?,?,?,?)',
                     (datetime.now().isoformat(timespec='seconds'), kind, tool,
                      json.dumps(args, default=str)[:2000], json.dumps(result, default=str)[:2000], status))
        conn.commit()
        conn.close()
    except Exception as e:  # logging must never break the agent
        print(f"[agent_log] {e}")


# ---------- helpers ----------
def _compact(c):
    """Short container view so tool results stay small (saves tokens)."""
    d = c.to_dict()
    return {
        "id": d["id"], "order": d["order_number"], "status": d["status"], "contents": d["contents"],
        "zone": d["location"]["zone"], "risk": d["risk_level"], "weight_kg": d["weight"],
        "value_usd": d["container_value"], "utilization_pct": d["utilization"],
        "temp_c": d["temperature"], "humidity_pct": d["humidity"], "gate": d["gate_problems"],
        "priority": d["priority"], "scheduled_exit": d["scheduled_exit_date"][:16],
        "hours_in_warehouse": d["time_in_hours"], "scans": d["scan_count"],
    }


def _resolve(cid):
    """Find a container by exact id, case-insensitive id, or order number."""
    if cid is None:
        return None
    cid = str(cid).strip().lstrip('#')
    if cid in warehouse.containers:
        return warehouse.containers[cid]
    for k, c in warehouse.containers.items():
        if k.lower() == cid.lower() or str(c.order_number) == cid:
            return c
    return None


# ---------- READ TOOLS ----------
def tool_get_warehouse_summary(**_):
    s = warehouse.get_stats()
    f = s["financial"]
    return {"total": s["total"], "in_warehouse": s["checked_in"], "checked_out": s["checked_out"],
            "avg_utilization_pct": s["avg_utilization"], "by_zone": s["zone_dist"], "by_risk": s["risk_dist"],
            "by_contents": s["contents_dist"], "active_alerts": len(s["alerts"]),
            "net_profit_usd": f["profit"]["net_usd"], "total_revenue_usd": f["revenue"]["total_usd"],
            "capacity_used_pct": f["kpis"]["warehouse_utilization"]}


def tool_search_containers(zone=None, risk_level=None, contents=None, status=None, min_weight=None,
                           min_value=None, has_gate_problems=None, exits_within_days=None,
                           overdue=None, not_overdue=None, sort_by=None, descending=True, limit=10, **_):
    now = datetime.now()
    rows = list(warehouse.containers.values())
    if zone: rows = [c for c in rows if c.zone.upper() == str(zone).upper()]
    if risk_level: rows = [c for c in rows if c.risk_level.lower() == str(risk_level).lower()]
    if contents:
        want = str(contents).lower().replace(" ", "_")
        rows = [c for c in rows if c.contents.lower() == want]
    if status: rows = [c for c in rows if c.status == status]
    if min_weight is not None: rows = [c for c in rows if c.weight >= float(min_weight)]
    if min_value is not None: rows = [c for c in rows if c.container_value >= float(min_value)]
    if has_gate_problems is True: rows = [c for c in rows if c.gate_problems and c.gate_problems != "None"]
    if exits_within_days is not None:
        lim = now + timedelta(days=float(exits_within_days))
        rows = [c for c in rows if c.status == "in_warehouse" and c.scheduled_exit_date <= lim]
    if not_overdue is True:
        rows = [c for c in rows if c.status == "in_warehouse" and c.scheduled_exit_date >= now]
    if overdue is True:
        rows = [c for c in rows if c.status == "in_warehouse" and c.scheduled_exit_date < now]
    keys = {"value": lambda c: c.container_value, "weight": lambda c: c.weight,
            "exit_date": lambda c: c.scheduled_exit_date, "utilization": lambda c: c.utilization_percentage,
            "temperature": lambda c: c.temperature, "priority": lambda c: c.priority,
            "entry_date": lambda c: c.entry_date}
    if sort_by in keys:
        rows.sort(key=keys[sort_by], reverse=bool(descending))
    limit = max(1, min(int(limit or 10), 25))
    return {"matched": len(rows), "returned": min(limit, len(rows)), "containers": [_compact(c) for c in rows[:limit]]}


def tool_get_container(container_id=None, **_):
    c = _resolve(container_id)
    if not c:
        return {"error": f"No container found for '{container_id}'. New containers only enter via the Scan QR page."}
    return {"container": _compact(c), "revenue_usd": warehouse.get_container_revenue(c.id)["total_usd"]}


def tool_aggregate(group_by="zone", metric="count", status=None, **_):
    attr = {"zone": "zone", "risk": "risk_level", "contents": "contents", "status": "status"}.get(group_by)
    if not attr:
        return {"error": "group_by must be one of: zone, risk, contents, status"}
    val = {"count": lambda c: 1, "value_usd": lambda c: c.container_value, "weight_kg": lambda c: c.weight,
           "avg_utilization": lambda c: c.utilization_percentage}.get(metric)
    if not val:
        return {"error": "metric must be one of: count, value_usd, weight_kg, avg_utilization"}
    groups = defaultdict(list)
    for c in warehouse.containers.values():
        if status and c.status != status:
            continue
        groups[getattr(c, attr)].append(val(c))
    out = {}
    for k, v in groups.items():
        out[k] = round(sum(v) / len(v), 1) if metric == "avg_utilization" else round(sum(v), 2)
    return {"group_by": group_by, "metric": metric, "result": out}


def tool_get_zone_status(zone=None, **_):
    z = str(zone or "").upper()
    if z not in ZoneSystem.ZONES:
        return {"error": f"Zone must be one of {list(ZoneSystem.ZONES)}"}
    cs = warehouse.get_containers_by_zone(z)
    live = [c for c in cs if c.status == "in_warehouse"]
    return {"zone": z, "name": ZoneSystem.ZONES[z]["name"], "total": len(cs), "in_warehouse": len(live),
            "risk_mix": dict(defaultdict(int, {r: sum(1 for c in live if c.risk_level == r) for r in {c.risk_level for c in live}})),
            "total_value_usd": round(sum(c.container_value for c in live), 2),
            "avg_utilization_pct": round(sum(c.utilization_percentage for c in live) / len(live), 1) if live else 0}


def tool_get_alerts(limit=15, **_):
    al = warehouse.alert_system.get_active_alerts()[:max(1, min(int(limit or 15), 25))]
    return {"active_alerts": len(warehouse.alert_system.get_active_alerts()), "alerts": al}


def tool_get_exit_schedule(days=7, **_):
    res = tool_search_containers(exits_within_days=days, not_overdue=True, status="in_warehouse", sort_by="exit_date",
                                 descending=False, limit=20)
    res["already_overdue_not_included"] = tool_search_containers(overdue=True, limit=1)["matched"]
    return res


def tool_get_financials(**_):
    f = warehouse.get_financial_summary()
    return {"revenue_usd": f["revenue"], "costs_usd": f["costs"], "profit": f["profit"], "kpis": f["kpis"],
            "exchange_rate_usd_to_tnd": COMPANY_CONFIG["exchange_rate_usd_to_tnd"]}


def tool_get_container_revenue(container_id=None, **_):
    c = _resolve(container_id)
    if not c:
        return {"error": f"No container found for '{container_id}'"}
    return warehouse.get_container_revenue(c.id)


def tool_get_insights(**_):
    run_monitor_if_stale()
    return {"last_run": MONITOR_STATE["last_run"], "insights": MONITOR_STATE["insights"]}


def tool_search_knowledge(query="", **_):
    """Fuzzy text search (TF-IDF) — for descriptions like 'the electronics shipment in cold storage'."""
    return {"context": retrieve_relevant_context(query or "", warehouse, top_k=6)}


# ---------- WRITE TOOLS (validated, then approval-gated) ----------
def _w_checkout(container_id=None, **_):
    c = _resolve(container_id)
    if not c: return None, f"Container '{container_id}' not found."
    if c.status != "in_warehouse": return None, f"{c.id} is already {c.status}."
    return c, f"Check out container {c.id} ({c.contents}, Zone {c.zone})"


def _w_ack(alert_ids=None, **_):
    ids = [int(i) for i in (alert_ids or [])]
    if not ids: return None, "No alert ids given."
    return ids, f"Acknowledge/resolve alert(s) {ids}"


def _w_resched(container_id=None, new_exit_date=None, **_):
    c = _resolve(container_id)
    if not c: return None, f"Container '{container_id}' not found."
    if c.status != "in_warehouse": return None, f"{c.id} is already {c.status}."
    try:
        d = datetime.fromisoformat(str(new_exit_date))
    except Exception:
        return None, "new_exit_date must be ISO format, e.g. 2026-11-02 or 2026-11-02T14:00"
    return (c, d), f"Reschedule exit of {c.id} to {d.strftime('%Y-%m-%d %H:%M')} (currently {c.scheduled_exit_date.strftime('%Y-%m-%d %H:%M')})"


def _w_flag(container_id=None, message=None, severity="warning", **_):
    c = _resolve(container_id)
    if not c: return None, f"Container '{container_id}' not found."
    if not message: return None, "A message is required."
    sev = severity if severity in ("info", "warning", "critical") else "warning"
    return (c, str(message)[:300], sev), f"Raise a {sev} alert on {c.id}: \"{str(message)[:120]}\""


def _do_checkout(c):
    with WRITE_LOCK:
        warehouse.checkout_container(c.id)
    return f"{c.id} checked out."


def _do_ack(ids):
    with WRITE_LOCK:
        conn = sqlite3.connect(DB_PATH)
        conn.executemany('UPDATE alerts SET is_resolved = 1 WHERE id = ?', [(i,) for i in ids])
        conn.commit(); conn.close()
    return f"Alerts {ids} resolved."


def _do_resched(payload):
    c, d = payload
    with WRITE_LOCK:
        c.scheduled_exit_date = d
        c.save_to_db()
    return f"{c.id} exit rescheduled to {d.strftime('%Y-%m-%d %H:%M')}."


def _do_flag(payload):
    c, msg, sev = payload
    with WRITE_LOCK:
        warehouse.alert_system.create_alert(c.id, "AGENT_FLAG", f"🤖 {msg}", sev)
    return f"Alert raised on {c.id}."


WRITE_TOOLS = {
    "checkout_container": (_w_checkout, _do_checkout),
    "acknowledge_alerts": (_w_ack, _do_ack),
    "reschedule_exit": (_w_resched, _do_resched),
    "flag_container": (_w_flag, _do_flag),
}

PENDING_ACTIONS = {}   # action_id -> dict(sid, tool, args, summary, status, created)
PENDING_LOCK = threading.Lock()


def propose_write(tool, args, sid):
    validate, _ = WRITE_TOOLS[tool]
    payload, summary = validate(**args)
    if payload is None:
        return {"error": summary}
    if AGENT_AUTONOMY == "auto":
        res = WRITE_TOOLS[tool][1](payload)
        agent_log("action", tool, args, res, "auto_executed")
        return {"status": "executed", "result": res}
    aid = uuid.uuid4().hex[:8]
    with PENDING_LOCK:
        PENDING_ACTIONS[aid] = {"id": aid, "sid": sid, "tool": tool, "args": args, "summary": summary,
                                "status": "pending", "created": datetime.now().isoformat(timespec='seconds')}
    agent_log("action", tool, args, summary, "proposed")
    return {"status": "pending_user_approval", "action_id": aid, "summary": summary,
            "note": "Not executed yet. Tell the user it is waiting for their approval."}


def decide_action(aid, sid, approve):
    with PENDING_LOCK:
        act = PENDING_ACTIONS.get(aid)
        if not act or act["sid"] != sid:
            return None, "Action not found."
        if act["status"] != "pending":
            return None, f"Action already {act['status']}."
        act["status"] = "approved" if approve else "rejected"
    if not approve:
        agent_log("action", act["tool"], act["args"], "rejected by user", "rejected")
        return act, "Rejected — nothing was changed."
    # re-validate at execution time: the world may have changed since it was proposed
    payload, msg = WRITE_TOOLS[act["tool"]][0](**act["args"])
    if payload is None:
        act["status"] = "failed"
        agent_log("action", act["tool"], act["args"], msg, "failed")
        return act, f"Could not execute: {msg}"
    res = WRITE_TOOLS[act["tool"]][1](payload)
    agent_log("action", act["tool"], act["args"], res, "approved_executed")
    return act, res


# ---------- ANALYTICS TOOLS (shared by the LLM agent and the offline agent) ----------
RISK_W = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _risk_score(c, now=None):
    """Explainable 0-20ish score: base risk + overdue + gate problem + temperature/humidity + value."""
    now = now or datetime.now()
    score = RISK_W.get(c.risk_level, 2) * 2.0
    why = [f"{c.risk_level} risk"]
    if c.status == "in_warehouse" and c.scheduled_exit_date < now:
        days = (now - c.scheduled_exit_date).total_seconds() / 86400
        score += 3 + min(days, 10) * 0.3
        why.append(f"{days:.0f} day(s) past exit" if days >= 1 else "past exit time")
    if c.gate_problems not in (None, "None", ""):
        score += 3
        why.append(f"gate problem: {c.gate_problems}")
    if c.contents == "chemicals" and c.temperature > 25:
        score += 3
        why.append(f"chemicals at {c.temperature}°C")
    if c.zone == "C" and c.temperature > 8:
        score += 1.5
        why.append(f"{c.temperature}°C in Cold Storage")
    if c.contents in ("electronics", "fragile", "textiles") and c.humidity > 70:
        score += 1.5
        why.append(f"{c.humidity}% humidity")
    if c.container_value >= 30000:
        score += 1
        why.append(f"high value ${c.container_value:,.0f}")
    return round(score, 1), why


def tool_get_risk_report(limit=5, **_):
    now = datetime.now()
    live = [c for c in warehouse.containers.values() if c.status == "in_warehouse"]
    scored = sorted(((_risk_score(c, now), c) for c in live), key=lambda t: t[0][0], reverse=True)
    top = [{"id": c.id, "score": sc, "zone": c.zone, "value_usd": c.container_value, "reasons": why}
           for (sc, why), c in scored[:max(1, min(int(limit or 5), 15))]]
    zones = defaultdict(list)
    for (sc, _), c in scored:
        zones[c.zone].append(sc)
    zr = sorted(({"zone": z, "name": ZoneSystem.ZONES.get(z, {}).get("name", z), "containers": len(v),
                  "total_score": round(sum(v), 1), "avg_score": round(sum(v) / len(v), 1)} for z, v in zones.items()),
                key=lambda r: r["total_score"], reverse=True)
    return {"scored": len(scored), "top_containers": top, "zones_by_risk": zr}


def tool_get_recommendations(**_):
    """Prioritised, explainable to-do list built from the live data (no LLM needed)."""
    now = datetime.now()
    live = [c for c in warehouse.containers.values() if c.status == "in_warehouse"]
    recs = []

    def add(pri, icon, title, why, cs, command):
        if cs:
            recs.append({"priority": pri, "icon": icon, "title": f"{len(cs)} {title}", "why": why,
                         "containers": [c.id for c in cs[:5]], "try": command})

    overdue = sorted([c for c in live if c.scheduled_exit_date < now], key=lambda c: -c.container_value)
    add(1, "🚨", "overdue container(s)", "They are past their scheduled exit, still occupy space and add risk.",
        overdue, f"check out {overdue[0].id}" if overdue else "")
    gate = [c for c in live if c.risk_level in ("high", "critical") and c.gate_problems not in (None, "None", "")]
    add(1, "🚧", "risky container(s) with gate problems", "High/critical goods with an unresolved gate issue should be inspected.",
        gate, f"flag {gate[0].id}: inspect gate problem" if gate else "")
    hot = [c for c in live if c.contents == "chemicals" and c.temperature > 25]
    add(1, "🔥", "chemical container(s) above 25°C", "Heat raises the hazard level; move to a cooler zone or inspect.",
        hot, f"flag {hot[0].id}: chemicals too warm" if hot else "")
    crit_alerts = [a for a in warehouse.alert_system.get_active_alerts() if a.get("severity") == "critical"]
    if crit_alerts:
        recs.append({"priority": 2, "icon": "🔔", "title": f"{len(crit_alerts)} unresolved critical alert(s)",
                     "why": "Review them, then resolve once handled.", "containers": [a["container_id"] for a in crit_alerts[:5]],
                     "try": "alerts"})
    soon = sorted([c for c in live if now <= c.scheduled_exit_date <= now + timedelta(hours=24)], key=lambda c: c.scheduled_exit_date)
    add(2, "📤", "container(s) leaving within 24h", "Prepare dispatch and paperwork.", soon, "exits in 1 day")
    cold = [c for c in live if c.zone == "C" and c.temperature > 8]
    add(3, "🌡️", "container(s) warmer than 8°C in Cold Storage", "Check the cold-chain / cooling.", cold, "zone C")
    humid = [c for c in live if c.contents in ("electronics", "fragile", "textiles") and c.humidity > 70]
    add(3, "💧", "humidity-sensitive container(s) above 70%", "Risk of moisture damage.", humid, "why is " + humid[0].id + " risky" if humid else "")
    cap = warehouse.get_financial_summary()["kpis"]["warehouse_utilization"]
    if cap >= 85:
        recs.append({"priority": 2, "icon": "📦", "title": f"Warehouse capacity at {cap}%", "why": "Little room left; schedule exits.",
                     "containers": [], "try": "exits in 3 days"})
    recs.sort(key=lambda r: r["priority"])
    return {"count": len(recs), "recommendations": recs}


READ_TOOLS = {
    "get_warehouse_summary": tool_get_warehouse_summary,
    "search_containers": tool_search_containers,
    "get_container": tool_get_container,
    "aggregate": tool_aggregate,
    "get_zone_status": tool_get_zone_status,
    "get_alerts": tool_get_alerts,
    "get_exit_schedule": tool_get_exit_schedule,
    "get_financials": tool_get_financials,
    "get_container_revenue": tool_get_container_revenue,
    "get_insights": tool_get_insights,
    "search_knowledge": tool_search_knowledge,
    "get_risk_report": tool_get_risk_report,
    "get_recommendations": tool_get_recommendations,
}


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


_S, _N, _I, _B = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}
TOOL_SCHEMAS = [
    _fn("get_warehouse_summary", "Counts, risk/zone/contents distribution, alerts count, headline financials."),
    _fn("search_containers", "Filter/sort containers. Use for lists, 'heaviest', 'most valuable', 'overdue', 'in zone B', etc.",
        {"zone": {"type": "string", "description": "A-F"}, "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
         "contents": _S, "status": {"type": "string", "enum": ["in_warehouse", "checked_out"]},
         "min_weight": _N, "min_value": _N, "has_gate_problems": _B, "exits_within_days": _N, "overdue": _B,
         "sort_by": {"type": "string", "enum": ["value", "weight", "exit_date", "utilization", "temperature", "priority", "entry_date"]},
         "descending": _B, "not_overdue": _B, "limit": _I}),
    _fn("get_container", "Full details of ONE container by id or order number.", {"container_id": _S}, ["container_id"]),
    _fn("aggregate", "Group containers and sum/count a metric (counts, total value, total weight, avg utilization).",
        {"group_by": {"type": "string", "enum": ["zone", "risk", "contents", "status"]},
         "metric": {"type": "string", "enum": ["count", "value_usd", "weight_kg", "avg_utilization"]},
         "status": {"type": "string", "enum": ["in_warehouse", "checked_out"]}}, ["group_by", "metric"]),
    _fn("get_zone_status", "Occupancy, risk mix and value of one zone.", {"zone": _S}, ["zone"]),
    _fn("get_alerts", "Active (unresolved) alerts with their ids.", {"limit": _I}),
    _fn("get_exit_schedule", "Containers due to exit within N days (default 7), soonest first.", {"days": _N}),
    _fn("get_financials", "Revenue breakdown, costs, profit margin, ROI and KPIs (USD; TND = USD x rate)."),
    _fn("get_container_revenue", "Revenue attributable to one container.", {"container_id": _S}, ["container_id"]),
    _fn("get_insights", "Latest findings from the background monitor (overdue exits, gate problems, humidity, capacity)."),
    _fn("search_knowledge", "Fuzzy text search over container descriptions when the user doesn't give an exact id.", {"query": _S}, ["query"]),
    _fn("get_risk_report", "Explainable risk ranking: top risky containers (with reasons) and zones ranked by total risk.", {"limit": _I}),
    _fn("get_recommendations", "Prioritised to-do list (overdue, gate problems, heat, alerts, upcoming exits) with a suggested next command for each."),
    _fn("checkout_container", "PROPOSE checking a container out. Needs user approval.", {"container_id": _S, "reason": _S}, ["container_id"]),
    _fn("acknowledge_alerts", "PROPOSE resolving alerts by id. Needs user approval.", {"alert_ids": {"type": "array", "items": _I}, "reason": _S}, ["alert_ids"]),
    _fn("reschedule_exit", "PROPOSE a new scheduled exit date. Needs user approval.", {"container_id": _S, "new_exit_date": {"type": "string", "description": "ISO date/time"}, "reason": _S}, ["container_id", "new_exit_date"]),
    _fn("flag_container", "PROPOSE raising a new alert on a container. Needs user approval.", {"container_id": _S, "message": _S, "severity": {"type": "string", "enum": ["info", "warning", "critical"]}}, ["container_id", "message"]),
]

AGENT_SYSTEM_PROMPT = """You are the Warehouse Operations Agent for Warehouse AI Logistics Inc (Tunis). \
You monitor and help run a live container warehouse (150m x 100m, zones A-F: A Reception, B Primary Storage, \
C Cold Storage, D High-Value, E Archive, F Dispatch). You work through TOOLS that read the real database.

How to work:
- NEVER answer from memory about containers, alerts, money or schedules. Call tools first, then answer from the results. \
Chain several tool calls when a question needs it (e.g. find overdue containers, then check their value).
- For 'what should we do', 'what's risky' or 'brief me', call get_recommendations / get_risk_report / get_insights first, then explain the findings in plain language and say which write action you would propose.
- If a tool returns an error or nothing, say so plainly. Never invent ids, numbers or statuses.
- Money is stored in USD; TND = USD x the exchange rate returned by get_financials. Give both when asked about money.
- When you spot a problem the user should act on, you may PROPOSE an action with a write tool \
(checkout_container, acknowledge_alerts, reschedule_exit, flag_container). Proposals are NOT executed until the human \
approves them in the UI — say clearly that it is waiting for approval. Only propose actions that are clearly useful \
or requested; never propose bulk changes the user did not ask for. Always pass a short `reason`.
- If a request is ambiguous about WHICH container, ask one short clarifying question instead of guessing.
- New containers only enter the system via the Scan QR page; you cannot create them.
- Keep answers under ~150 words unless asked for detail.
- Style: concise, plain text (no markdown tables), short bullets, a few emoji (📦 📍 💰 ⚠️ ✅). Lead with the answer, then the key numbers, then a recommended next step if there is one."""


# ---------- LLM call with tools: provider-agnostic, auto model discovery + failover ----------
_BAD_MODEL = re.compile(r'whisper|tts|embed|guard|moderat|image|vision|audio|speech|transcri|rerank|imagen|veo|live|dall|safeguard|nano-banana', re.I)
_PREFERRED = [r'gpt-oss-120b', r'gpt-oss-20b', r'llama-?3\.3-70b', r'qwen3?.*(?:32b|30b|27b|235b)',
              r'gemini.*flash.*lite', r'gemini.*flash(?!.*lite)', r'gemini', r'llama', r'mistral|mixtral', r'qwen', r'deepseek']
_MODELS = {"candidates": None, "i": 0}
_LLM_USE = {"day": None, "n": 0}
LLM_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '35'))             # seconds to wait for each model reply
LLM_DAILY_LIMIT = int(os.environ.get('LLM_DAILY_LIMIT', '400'))   # protects a free quota on a public demo
_LLM_LOCK = threading.Lock()
_COOL = {}     # model -> epoch time until which it is skipped (after a 429)


def _auth_headers():
    h = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        h["Authorization"] = f"Bearer {LLM_API_KEY}"
    return h


def _discover_models():
    """Ask the provider which models it currently serves (model names change; don't hardcode)."""
    out = []
    try:
        r = requests.get(LLM_URL.replace("/chat/completions", "/models"), headers=_auth_headers(), timeout=10)
        r.raise_for_status()
        j = r.json()
        for m in (j.get("data") or j.get("models") or []):
            mid = (m.get("id") or m.get("name") or "").replace("models/", "")
            if not mid or _BAD_MODEL.search(mid):
                continue
            if "supported_parameters" in m and "tools" not in (m.get("supported_parameters") or []):
                continue                                   # OpenRouter: tool-capable models only
            if LLM_PROVIDER == "openrouter" and not mid.endswith(":free"):
                continue                                   # stay on free models
            out.append(mid)
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        _MODELS["auth_error"] = code in (401, 403)
        print(f"[llm] model discovery failed: {e}")
    rank = lambda mid: next((i for i, rx in enumerate(_PREFERRED) if re.search(rx, mid, re.I)), 99)
    slow = lambda mid: 1 if re.search(r'pro|think|reason|deep|r1|exp(?:erimental)?\b|preview|latest', mid, re.I) else 0
    out = sorted(dict.fromkeys(out), key=lambda m: (rank(m), slow(m)))
    default = {"groq": "openai/gpt-oss-20b"}.get(LLM_PROVIDER)
    if default and default in out:
        out.remove(default); out.insert(0, default)
    return out


def current_model():
    if LLM_MODEL_PINNED:
        return LLM_MODEL_PINNED
    with _LLM_LOCK:
        if _MODELS["candidates"] is None:
            found = _discover_models()
            _MODELS["candidates"] = found if found else None      # empty -> retry on the next call
        c = _MODELS["candidates"] or []
        now = _time.time()
        for m in c[_MODELS["i"]:]:
            if _COOL.get(m, 0) <= now:
                return m
        return None


def _next_model():
    with _LLM_LOCK:
        _MODELS["i"] += 1


def _budget_ok():
    today = datetime.now().strftime("%Y-%m-%d")
    with _LLM_LOCK:
        if _LLM_USE["day"] != today:
            _LLM_USE.update(day=today, n=0)
        if _LLM_USE["n"] >= LLM_DAILY_LIMIT:
            return False
        _LLM_USE["n"] += 1
        return True


def _llm_chat(messages, tools=None):
    if not LLM_ENABLED:
        return None, "LLM not configured."
    if not _budget_ok():
        return None, "the demo's daily AI quota is used up (it resets tomorrow)."
    headers = _auth_headers()
    drop_reasoning = False
    if LLM_MODEL_PINNED and _COOL.get(LLM_MODEL_PINNED, 0) > _time.time():
        return None, f"provider rate limit (429): '{LLM_MODEL_PINNED}' is cooling down, retry in ~{int(_COOL[LLM_MODEL_PINNED] - _time.time())}s."
    for attempt in range(4):
        model = current_model()
        if not model and _MODELS["candidates"]:
            wait = int(max(1, min(_COOL.values(), default=0) - _time.time()))
            return None, f"provider rate limit (429): every model is cooling down, retry in ~{wait}s."
        if not model:
            if _MODELS.get("auth_error"):
                return None, "the provider rejected the API key (401/403) — check LLM_API_KEY."
            return None, "couldn't list models at the provider — set LLM_MODEL explicitly, or check the URL/network."
        body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1200}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if LLM_PROVIDER == "gemini" and not drop_reasoning:
            body["reasoning_effort"] = "low"          # keeps Gemini fast; dropped automatically if rejected
        try:
            r = requests.post(LLM_URL, headers=headers, json=body,
                              timeout=(10, 180) if LLM_PROVIDER == 'ollama' else (10, LLM_TIMEOUT))
            txt = r.text[:300].lower()
            if r.status_code == 429:
                if re.search(r'per ?day|daily|limit: ?0|exhausted', txt):
                    secs = 3600
                else:
                    try:
                        secs = max(5, min(float(r.headers.get("Retry-After", 60)), 300))
                    except ValueError:
                        secs = 60
                _COOL[model] = _time.time() + secs
                if not LLM_MODEL_PINNED and attempt < 3:
                    print(f"[llm] model '{model}' is rate-limited (429); cooling it for {int(secs)}s and trying the next one")
                    continue
                return None, f"provider rate limit (429) on '{model}'; retry in ~{int(secs)}s."
            if r.status_code == 400 and "reasoning" in txt and "reasoning_effort" in body:
                drop_reasoning = True
                continue
            model_problem = r.status_code == 404 or (r.status_code in (400, 403) and 'thought_signature' not in txt and re.search(
                r'model.*(not found|not supported|decommission|deprecat|does not exist|invalid|unavailable)|(does not|doesn.t|not) support.*tool|tool.*not supported', txt))
            if model_problem and not LLM_MODEL_PINNED and attempt < 2:
                print(f"[llm] model '{model}' rejected ({r.status_code}); trying the next one")
                _next_model()
                continue
            if r.status_code == 404:
                return None, f"model/URL not found (404) for '{model}' — check LLM_MODEL / LLM_BASE_URL."
            if r.status_code in (401, 403):
                return None, f"the provider rejected the API key ({r.status_code}) — check LLM_API_KEY."
            if r.status_code == 429:
                return None, "provider rate limit (429)."
            if r.status_code == 400:
                return None, f"the provider rejected the request (400): {r.text[:200]}"
            r.raise_for_status()
            return r.json()["choices"][0]["message"], None
        except requests.exceptions.Timeout:
            if not LLM_MODEL_PINNED and attempt < 2:
                print(f"[llm] model '{model}' timed out; trying the next one")
                _next_model()
                continue
            return None, f"the AI provider timed out (model: {model})."
        except requests.exceptions.ConnectionError:
            return None, ("can't connect to Ollama — is it running?" if LLM_PROVIDER == 'ollama'
                          else "can't reach the AI provider (network/DNS).")
        except requests.exceptions.RequestException as e:
            return None, f"AI provider error ({e})."
        except (KeyError, IndexError, ValueError):
            return None, "unexpected response from the AI provider."
    return None, "no working model was found at the provider."


def llm_status():
    return {"mode": "llm" if LLM_ENABLED else "offline", "provider": LLM_PROVIDER if LLM_ENABLED else None,
            "model": (LLM_MODEL_PINNED or (current_model() if _MODELS["candidates"] is not None else "auto")) if LLM_ENABLED else None,
            "calls_today": _LLM_USE["n"], "daily_limit": LLM_DAILY_LIMIT}


# ---------- OFFLINE AGENT v2 (no LLM needed) ----------
# A small language-understanding layer: it extracts entities (container refs incl. "first container"/"it",
# zones, risk, contents, sort, counts, time windows), then composes the same tools the LLM agent uses.
# It remembers the last container/list per browser session, so follow-ups work ("what about its revenue?").
import re

OFFLINE_CTX = {}     # sid -> {"last": container_id, "list": [ids]}
SUGGESTIONS = {}     # sid -> chips to show under the next answer

_ZONE_PHRASES = {"reception": "A", "primary storage": "B", "cold storage": "C", "high-value storage": "D",
                 "high value storage": "D", "archive": "E", "dispatch area": "F"}
_CONTENT_WORDS = {"electronic": "electronics", "fragile": "fragile", "chemical": "chemicals", "textile": "textiles",
                  "machinery": "heavy_machinery", "mixed": "mixed"}
_ORD = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "fifth": 4, "5th": 4}
_SORTS = [  # (regex, sort_by, descending)
    (r'heaviest|biggest|most weight|largest', "weight", True), (r'lightest|least weight|smallest', "weight", False),
    (r'most valuable|most expensive|highest value|worth (?:the )?most|priciest', "value", True),
    (r'cheapest|least valuable|lowest value', "value", False),
    (r'hottest|warmest|highest temp', "temperature", True), (r'coldest|lowest temp', "temperature", False),
    (r'fullest|highest util|most utili[sz]ed', "utilization", True), (r'emptiest|lowest util|least utili[sz]ed', "utilization", False),
    (r'(?:earliest|soonest|next) exit|exit(?:ing)? (?:first|soonest)|leaving soonest', "exit_date", False),
    (r'latest exit', "exit_date", True),
    (r'newest|most recent|latest|recently', "entry_date", True), (r'oldest|longest', "entry_date", False),
    (r'highest priority|most urgent', "priority", True),
]
_COMPACT_KEY = {"value": "value_usd", "weight": "weight_kg", "exit_date": "scheduled_exit", "utilization": "utilization_pct",
                "temperature": "temp_c", "priority": "priority", "entry_date": "hours_in_warehouse"}


def _W(ql, *stems):
    return any(re.search(r'\b' + re.escape(s), ql) for s in stems)


def _global_order():
    return sorted(warehouse.containers.values(), key=lambda c: (c.entry_date, c.order_number))


def _parse(q, ctx):
    ql = q.lower().strip()
    e = {"ql": ql, "zones": [], "risk": None, "contents": None, "status": None, "n": None, "sort": None,
         "desc": True, "days": None, "ref": None, "all": bool(re.search(r'\ball\b', ql))}
    m = re.search(r'\bzones?\s*([a-f])\b', ql)
    if m:
        e["zones"].append(m.group(1).upper())
        tail = ql[m.end():]
        while True:
            m2 = re.match(r'\s*(?:,|and|&|vs\.?|versus|or|with)\s*(?:zone\s*)?([a-f])\b', tail)
            if not m2:
                break
            e["zones"].append(m2.group(1).upper())
            tail = tail[m2.end():]
    for ph, z in _ZONE_PHRASES.items():
        if ph in ql and z not in e["zones"]:
            e["zones"].append(z)
    m = re.search(r'\b(critical|high|medium|low)(?:[- ]risk)?\b(?![- ]value)', ql)
    if m and (m.group(1) == "critical" or "risk" in ql):
        e["risk"] = m.group(1)
    for stem, val in _CONTENT_WORDS.items():
        if re.search(r'\b' + stem, ql):
            e["contents"] = val
            break
    if re.search(r'checked[- ]?out|exited|already left|processed|departed', ql):
        e["status"] = "checked_out"
    elif re.search(r'in (?:the )?warehouse|currently|inside|\bstill\b', ql):
        e["status"] = "in_warehouse"
    m = (re.search(r'\b(?:top|bottom|show(?: me)?|list|give me)\s+(\d{1,2})\b', ql)
         or re.search(r'\b(\d{1,2})\s+(?:most|heaviest|lightest|biggest|hottest|coldest|oldest|newest|latest|highest|lowest|cheapest|riskiest|containers?)', ql))
    if m:
        e["n"] = max(1, min(int(m.group(1)), 25))
    for rx, key, desc in _SORTS:
        if re.search(rx, ql):
            e["sort"], e["desc"] = key, desc
            break
    m = re.search(r'(\d+(?:\.\d+)?)\s*(hour|hr|day|week)s?', ql)
    if m:
        v = float(m.group(1)); u = m.group(2)
        e["days"] = v / 24 if u in ("hour", "hr") else (v * 7 if u == "week" else v)
    elif "tomorrow" in ql:
        e["days"] = 2
    elif "today" in ql:
        e["days"] = 1
    elif "next week" in ql:
        e["days"] = 14
    elif "this week" in ql or "week" in ql:
        e["days"] = 7
    # --- which single container is being talked about? ---
    cid = warehouse.find_container_id_in_text(q)
    if not cid:
        m = re.search(r'(?:container\s*|#)(\d+)\b', ql)
        if m and _resolve(m.group(1)):
            cid = _resolve(m.group(1)).id
    if not cid:
        m = re.search(r'\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|latest|newest|oldest)\s+(container|one)\b', ql)
        if m:
            w = m.group(1)
            seq = [warehouse.containers[i] for i in ctx["list"] if i in warehouse.containers] if (m.group(2) == "one" and ctx["list"]) else _global_order()
            if seq:
                idx = _ORD.get(w, -1 if w in ("last", "latest", "newest") else 0)
                if w == "oldest": idx = 0
                if -len(seq) <= idx < len(seq):
                    cid = seq[idx].id
    if not cid and re.search(r'\b(it|its|this one|that one|this container|that container|the same one)\b', ql):
        cid = ctx.get("last")
    e["ref"] = cid if cid in warehouse.containers else None
    return e


def _detail_text(cid):
    c = warehouse.containers[cid]
    r = _compact(c)
    score, why = _risk_score(c)
    zname = ZoneSystem.ZONES.get(r["zone"], {}).get("name", "")
    return (f"📦 {r['id']} (#{r['order']}) — {r['status'].replace('_', ' ')}\n"
            f"📍 Zone {r['zone']} ({zname}) • {r['contents']} • {r['weight_kg']:,.0f} kg\n"
            f"⚠️ Risk: {r['risk']} • gate: {r['gate']}\n"
            f"🧮 Risk score {score}: {'; '.join(why)}\n"
            f"💰 Value ${r['value_usd']:,.2f}\n"
            f"🌡️ {r['temp_c']}°C • 💧 {r['humidity_pct']}% • utilization {r['utilization_pct']}%\n"
            f"📤 Scheduled exit {r['scheduled_exit']} • scanned {r['scans']}×")


def _fmt_c(c):
    return (f"• {c['id']} — {c['contents']}, Zone {c['zone']}, {c['risk']} risk, "
            f"${c['value_usd']:,.0f}, {c['weight_kg']:,.0f} kg, exits {c['scheduled_exit']}")


def run_offline_agent(q, sid, note=""):
    if q == BRIEFING_PROMPT:      # the UI button sends a long prompt written for an LLM
        q = "briefing"
    ctx = OFFLINE_CTX.setdefault(sid, {"last": None, "list": []})
    e = _parse(q, ctx)
    ql, ref = e["ql"], e["ref"]
    steps, pending = [], []

    def call(name, **kw):
        res = READ_TOOLS[name](**kw)
        steps.append({"tool": name, "args": kw})
        return res

    def finish(text, chips=None):
        SUGGESTIONS[sid] = chips or []
        return (note + text).strip(), steps, pending

    def propose(tool, args):
        r = propose_write(tool, args, sid)
        steps.append({"tool": tool, "args": args})
        if r.get("status") == "pending_user_approval":
            pending.append({"id": r["action_id"], "tool": tool, "summary": r["summary"], "reason": "Requested by you"})
            return f"⚡ Queued for your approval: {r['summary']}"
        if r.get("status") == "executed":
            return f"✅ {r['result']}"
        return f"⚠️ {r.get('error', 'Could not do that.')}"

    def search(limit=None, **extra):
        """search_containers with the filters found in the question (supports several zones)."""
        kw = dict(risk_level=e["risk"], contents=e["contents"], status=e["status"] or "in_warehouse",
                  has_gate_problems=True if _W(ql, "gate") else None, sort_by=e["sort"], descending=e["desc"],
                  limit=limit or e["n"] or 10)
        kw.update(extra)
        kw = {k: v for k, v in kw.items() if v is not None}
        if len(e["zones"]) > 1:
            merged, matched = [], 0
            for z in e["zones"]:
                r = call("search_containers", zone=z, **{**kw, "limit": 25})
                merged += r["containers"]; matched += r["matched"]
            if e["sort"]:
                k = _COMPACT_KEY[e["sort"]]
                rev = e["desc"] if e["sort"] != "entry_date" else not e["desc"]
                merged.sort(key=lambda c: c[k], reverse=rev)
            return {"matched": matched, "containers": merged[:kw["limit"]]}
        if e["zones"]:
            kw["zone"] = e["zones"][0]
        return call("search_containers", **kw)

    def show(res, title):
        cs = res["containers"]
        ctx["list"] = [c["id"] for c in cs]
        if len(cs) == 1:
            ctx["last"] = cs[0]["id"]
        if not cs:
            return f"{title}: none found."
        more = f"\n…and {res['matched'] - len(cs)} more." if res["matched"] > len(cs) else ""
        return f"{title} ({res['matched']}):\n" + "\n".join(_fmt_c(c) for c in cs) + more

    def adj():
        bits = []
        if e["risk"]: bits.append(f"{e['risk']}-risk")
        if e["contents"]: bits.append(e["contents"].replace("_", " "))
        if e["status"] == "checked_out": bits.append("checked-out")
        return " ".join(bits)

    def loc():
        return f" in zone {'/'.join(e['zones'])}" if e["zones"] else ""

    def tidy(t):
        return re.sub(r"\s+", " ", t).replace(" ,", ",").strip()

    # ================= WRITE REQUESTS =================
    if re.search(r'\b(check\s*-?\s*out|checkout|release)\b', ql):
        if e["all"] and _W(ql, "overdue", "late"):
            res = call("search_containers", overdue=True, sort_by="value", limit=5)
            if not res["containers"]:
                return finish("✅ No overdue containers to check out.")
            lines = [propose("checkout_container", {"container_id": c["id"]}) for c in res["containers"]]
            extra = f"\n(Only the 5 most valuable of {res['matched']} are queued; ask again for the rest.)" if res["matched"] > 5 else ""
            return finish("\n".join(lines) + extra)
        if ref:
            ctx["last"] = ref
            return finish(propose("checkout_container", {"container_id": ref}))
        return finish("Which container? e.g. “check out CONT_123”, “check out the first container”, or “check out all overdue”.")
    if re.search(r'\b(acknowledge|resolve|dismiss|clear)\b', ql) and "alert" in ql:
        ids = [int(x) for x in re.findall(r'\b\d+\b', q)]
        if not ids and e["all"]:
            ids = [a["id"] for a in warehouse.alert_system.get_active_alerts()]
        if not ids:
            return finish("Which alert ids? e.g. “resolve alert 12” or “resolve all alerts”.", ["🚨 alerts"])
        return finish(propose("acknowledge_alerts", {"alert_ids": ids}))
    if re.search(r'\b(reschedule|postpone|delay|push back)\b', ql):
        if not ref:
            return finish("Which container? e.g. “reschedule CONT_1 in 3 days”.")
        m = re.search(r'\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?', q)
        d = m.group(0).replace(" ", "T") if m else None
        if not d and e["days"] is not None:
            d = (datetime.now() + timedelta(days=e["days"] if "tomorrow" not in ql else 1)).strftime("%Y-%m-%d")
        if not d:
            return finish("To which date? e.g. “…to 2026-11-05” or “…in 3 days”.")
        ctx["last"] = ref
        return finish(propose("reschedule_exit", {"container_id": ref, "new_exit_date": d}))
    if re.search(r'\bflag\b', ql) and ref:
        msg = q.split(":", 1)[1].strip() if ":" in q else "Flagged for review by operator"
        ctx["last"] = ref
        return finish(propose("flag_container", {"container_id": ref, "message": msg, "severity": "warning"}))

    # ================= SMALL TALK / HELP =================
    if re.fullmatch(r'\s*(hi|hello|hey|hola|salam|bonjour|good (morning|afternoon|evening))\W*', ql):
        return finish("👋 Hi! I can brief you, rank risks, recommend next steps, look up containers/zones, and queue actions "
                      "for your approval. Try “what should I do?” or “riskiest containers”.",
                      ["📋 Give me a briefing", "🧭 What should I do?", "⚠️ Riskiest containers"])
    if len(ql) < 30 and re.search(r'\b(thanks|thank you|merci|great|perfect|ok(ay)?)\b', ql):
        return finish("You're welcome! Anything else?", ["📋 Give me a briefing", "🧭 What should I do?"])
    if _W(ql, "help", "what can you do", "commands", "capabilit"):
        return finish(HELP_TEXT, ["📋 Give me a briefing", "🧭 What should I do?", "⚠️ Riskiest containers"])

    # ================= ONE SPECIFIC CONTAINER =================
    if ref and not (e["all"] or _W(ql, "list", "containers")):
        ctx["last"] = ref
        chips = [f"💰 {ref} revenue", f"⚠️ Why is {ref} risky?", f"✅ Check out {ref}", "🧭 What should I do?"]
        if _W(ql, "revenue", "money", "profit", "earn", "worth", "financ", "income", "make"):
            r = call("get_container_revenue", container_id=ref)
            return finish(f"💰 {ref}: total ${r['total_usd']:,.2f} (≈ {r['total_tnd']:,.2f} TND). Of that, ${r['ai_generated_usd']:,.2f} "
                          f"comes from AI-driven protection/insurance value; goods value is ${r['container_value']:,.2f}.", chips)
        if _W(ql, "where", "which zone", "location", "located"):
            call("get_container", container_id=ref)
            c = _compact(warehouse.containers[ref])
            return finish(f"📍 {ref} is in Zone {c['zone']} ({ZoneSystem.ZONES.get(c['zone'], {}).get('name', '')}).", chips)
        if re.search(r'\bwhen\b|\bexit|leav|depart', ql):
            c = _compact(warehouse.containers[ref]); call("get_container", container_id=ref)
            return finish(f"📤 {ref} is scheduled to exit {c['scheduled_exit']} (priority {c['priority']}/7).", chips)
        if _W(ql, "why", "risk", "danger", "safe", "problem", "wrong"):
            c = warehouse.containers[ref]; call("get_container", container_id=ref)
            sc, why = _risk_score(c)
            return finish(f"⚠️ {ref} has a risk score of {sc}. Reasons: {'; '.join(why)}.", chips)
        call("get_container", container_id=ref)
        return finish(_detail_text(ref), chips)

    # ================= COMPARE / ZONE STATUS =================
    if len(e["zones"]) >= 2 and _W(ql, "compare", "vs", "versus", "difference", "between", "against"):
        rows = [call("get_zone_status", zone=z) for z in e["zones"][:4]]
        lines = [f"📍 Zone {r['zone']} ({r['name']}): {r['in_warehouse']} containers • ${r['total_value_usd']:,.0f} • "
                 f"avg utilization {r['avg_utilization_pct']}% • risk mix {r['risk_mix']}" for r in rows]
        best_v = max(rows, key=lambda r: r["total_value_usd"]); best_n = max(rows, key=lambda r: r["in_warehouse"])
        lines.append(f"➡️ Most value: Zone {best_v['zone']} • most containers: Zone {best_n['zone']}.")
        return finish("\n".join(lines), [f"📋 containers in zone {z}" for z in e["zones"][:3]])
    if (len(e["zones"]) == 1 and not (e["risk"] or e["contents"] or e["sort"] or e["n"])
            and not re.search(r'\bcontainers?\b|\blist\b|\bwhich\b|\bshow\b|exit|overdue|alert|risk', ql)):
        r = call("get_zone_status", zone=e["zones"][0])
        z = r["zone"]
        return finish(f"📍 Zone {z} — {r['name']}: {r['in_warehouse']} in warehouse ({r['total']} ever), value ${r['total_value_usd']:,.0f}, "
                      f"avg utilization {r['avg_utilization_pct']}%, risk mix {r['risk_mix']}.",
                      [f"📋 containers in zone {z}", f"⚠️ risk in zone {z}", "🧭 What should I do?"])

    # ================= BRIEFING =================
    if _W(ql, "briefing", "overview", "attention", "insight", "situation", "status report", "summary", "summar"):
        ins = call("get_insights")["insights"]
        s = call("get_warehouse_summary")
        al = call("get_alerts", limit=5)
        rec = call("get_recommendations")["recommendations"]
        lines = [f"📋 Briefing — {s['in_warehouse']} containers in warehouse, capacity {s['capacity_used_pct']}%, "
                 f"{al['active_alerts']} active alert(s), net profit ${s['net_profit_usd']:,.0f}."]
        if rec:
            lines.append("Top priorities:")
            for i, r in enumerate(rec[:3], 1):
                ids = f" — {', '.join(r['containers'][:3])}" if r["containers"] else ""
                lines.append(f"{i}. {r['icon']} {r['title']}{ids}\n   {r['why']}" + (f"\n   → try: “{r['try']}”" if r["try"] else ""))
        else:
            lines.append("✅ Nothing needs attention right now.")
        rest = [i for i in ins if i["severity"] != "info"]
        if rest:
            lines.append("Monitor: " + "; ".join(i["title"] for i in rest[:4]))
        return finish("\n".join(lines), [f"▶ {r['try']}" for r in rec[:3] if r["try"]] + ["⚠️ Riskiest containers"])

    # ================= ANALYTICS (can be combined: "overdue and revenue") =================
    parts, chips = [], []
    want_risk = re.search(r'riskiest|most risk|dangerous|risk (?:report|analysis|ranking|score)|biggest risk|at risk|highest risk|worst', ql)
    want_rec = _W(ql, "recommend", "suggest", "advice", "advise", "what should", "what do i", "next step", "priorit", "action plan", "to do", "todo")
    want_over = _W(ql, "overdue", "late", "past due", "behind schedule")
    want_exit = re.search(r'\b(exit|exits|exiting|leaving|leave|depart\w*|schedule\w*|due)\b', ql) and not (want_over and not re.search(r'\bexits?\b', ql))
    want_alert = _W(ql, "alert", "alarm", "notification")
    want_fin = _W(ql, "revenue", "profit", "financ", "money", "roi", "cost", "margin", "income", "earning")

    if want_rec:
        rec = call("get_recommendations")["recommendations"]
        if rec:
            lines = ["🧭 Recommended actions, most important first:"]
            for i, r in enumerate(rec[:6], 1):
                ids = f" — {', '.join(r['containers'][:4])}" if r["containers"] else ""
                lines.append(f"{i}. {r['icon']} {r['title']}{ids}\n   {r['why']}" + (f"\n   → try: “{r['try']}”" if r["try"] else ""))
            parts.append("\n".join(lines))
            chips += [f"▶ {r['try']}" for r in rec[:3] if r["try"]]
        else:
            parts.append("✅ Nothing urgent — no overdue containers, gate problems or temperature issues found.")
    if want_risk:
        rr = call("get_risk_report", limit=e["n"] or 5)
        if _W(ql, "zone") and not e["zones"]:
            z = rr["zones_by_risk"]
            parts.append("🗺️ Zones ranked by total risk score:\n" + "\n".join(
                f"{i}. Zone {r['zone']} ({r['name']}): total {r['total_score']} over {r['containers']} containers (avg {r['avg_score']})"
                for i, r in enumerate(z[:6], 1)))
        else:
            tc = rr["top_containers"]
            ctx["list"] = [t["id"] for t in tc]
            if tc: ctx["last"] = tc[0]["id"]
            parts.append("⚠️ Highest-risk containers (score = risk level + overdue + gate + heat/humidity + value):\n" + "\n".join(
                f"{i}. {t['id']} — score {t['score']} • Zone {t['zone']} • ${t['value_usd']:,.0f}\n   {'; '.join(t['reasons'])}"
                for i, t in enumerate(tc, 1)))
            chips += [f"⚠️ Why is {tc[0]['id']} risky?"] if tc else []
    if want_over:
        parts.append(show(search(overdue=True, sort_by=e["sort"] or "exit_date", descending=False if not e["sort"] else e["desc"],
                                 limit=e["n"] or 10), tidy(f"⏰ Overdue {adj()} containers{loc()}")))
        chips += ["✅ check out all overdue"]
    if want_exit and not want_over:
        days = e["days"] if e["days"] is not None else 7
        lbl = "by tomorrow" if "tomorrow" in ql else (f"within {days:g} day(s)" if days != 1 else "within 24 hours")
        res = search(exits_within_days=days, not_overdue=True, sort_by="exit_date", descending=False, limit=e["n"] or 15)
        txt = show(res, tidy(f"📤 Exits {lbl}{loc()}" + (f" — {adj()} only" if adj() else "")))
        od = call("search_containers", overdue=True, limit=1, **({"zone": e["zones"][0]} if len(e["zones"]) == 1 else {}))["matched"]
        if od:
            txt += f"\nℹ️ {od} more are already overdue (ask “overdue”)."
        parts.append(txt)
    if want_alert:
        r = call("get_alerts")
        parts.append("✅ No active alerts." if not r["alerts"] else f"🚨 {r['active_alerts']} active alert(s):\n" + "\n".join(
            f"• #{a['id']} [{a['severity']}] {a['container_id']}: {a['alert_message']}" for a in r["alerts"][:10]))
        if r["alerts"]: chips += ["✔ resolve all alerts"]
    if want_fin and not ref:
        f = call("get_financials")
        parts.append(f"💰 Revenue ${f['revenue_usd']['total_usd']:,.0f} • costs ${f['costs_usd']['total_usd']:,.0f} • net profit "
                     f"${f['profit']['net_usd']:,.0f} (≈ {f['profit']['net_tnd']:,.0f} TND) • margin {f['profit']['margin']}% • "
                     f"ROI {f['kpis']['roi_percentage']}%.")
    if parts:
        return finish("\n\n".join(parts), chips[:4] or ["📋 Give me a briefing", "🧭 What should I do?"])

    # ================= COUNTS / AGGREGATES =================
    filt = e["zones"] or e["risk"] or e["contents"]
    if _W(ql, "how many", "count", "number of") and filt:
        res = search(limit=5)
        ctx["list"] = [c["id"] for c in res["containers"]]
        body = "\n".join(_fmt_c(c) for c in res["containers"])
        more = f"\n…and {res['matched'] - len(res['containers'])} more." if res["matched"] > len(res["containers"]) else ""
        return finish(tidy(f"🔢 {res['matched']} {adj()} container(s){loc()}:") + ("\n" + body + more if body else " none."))
    if _W(ql, "how many", "count", "total", "average", "avg", "sum", "busiest", "emptiest", "distribution", "by zone", "by risk", "by content", "per zone") \
            or re.search(r'(most|least|highest|lowest) (valuable|full|busy|crowded) zone|zone with', ql):
        group = "risk" if re.search(r'by risk|per risk|risk level', ql) else ("contents" if re.search(r'by content|per content|by type', ql) else "zone")
        metric = ("value_usd" if _W(ql, "value", "worth", "money") else "weight_kg" if _W(ql, "weight") else
                  "avg_utilization" if _W(ql, "utili") else "count")
        r = call("aggregate", group_by=group, metric=metric, status=e["status"] or "in_warehouse")
        items = sorted(r["result"].items(), key=lambda kv: kv[1], reverse=True)
        unit = {"count": "", "value_usd": " USD", "weight_kg": " kg", "avg_utilization": " %"}[metric]
        txt = f"📊 {metric.replace('_', ' ')} by {group}: " + ", ".join(f"{k}: {v:,.0f}{unit}" for k, v in items)
        if items:
            low = _W(ql, "emptiest", "least", "lowest", "fewest")
            pick = items[-1] if low else items[0]
            if _W(ql, "busiest", "emptiest", "most", "least", "highest", "lowest", "fewest", "largest"):
                txt += f"\n➡️ {'Lowest' if low else 'Highest'}: {group} {pick[0]} ({pick[1]:,.0f}{unit})."
        return finish(txt)

    # ================= GENERAL LIST / SEARCH =================
    if e["zones"] or e["risk"] or e["contents"] or e["sort"] or e["n"] or e["status"] or _W(ql, "gate", "containers", "list", "show", "all", "everything"):
        res = search(sort_by=e["sort"])
        title = tidy(f"📦 {'Top ' + str(e['n']) + ' ' if e['n'] else ''}{adj()} containers{loc()}"
                     f"{' with gate problems' if _W(ql, 'gate') else ''}{' (sorted by ' + e['sort'].replace('_', ' ') + ')' if e['sort'] else ''}")
        return finish(show(res, title), ["🧭 What should I do?", "⚠️ Riskiest containers"] + (["🔎 first one"] if res["containers"] else []))

    # ================= FALLBACK =================
    return finish("🤔 I didn't quite get that — I'm running offline, so I match patterns rather than free-form language.\n\n" + HELP_TEXT,
                  ["📋 Give me a briefing", "🧭 What should I do?", "⚠️ Riskiest containers"])


HELP_TEXT = ("Things I understand:\n"
             "• “briefing” • “what should I do?” (prioritised recommendations) • “riskiest containers” / “riskiest zone”\n"
             "• “first container”, “newest container”, a container id, then follow-ups like “its revenue”, “why is it risky?”\n"
             "• filters you can combine: “top 3 heaviest critical containers in zone B”, “electronics in cold storage”, “most valuable overdue”\n"
             "• “compare zone B and C” • “zone D” • “how many by risk” • “total value by zone” • “busiest zone”\n"
             "• “overdue and revenue” • “exits tomorrow in zone B” • “alerts”\n"
             "• actions (you approve them): “check out <id>”, “check out all overdue”, “reschedule it in 3 days”, “flag <id>: reason”, “resolve all alerts”")


AGENT_SESSIONS = {}   # sid -> deque of {"role","content"} (text only, server-side; not in the cookie)


def _sid():
    if 'agent_sid' not in session:
        session['agent_sid'] = uuid.uuid4().hex
    return session['agent_sid']


def _history(sid):
    return AGENT_SESSIONS.setdefault(sid, deque(maxlen=16))


def run_agent(user_query, sid):
    """The agent loop. Returns (answer_text, steps, pending_actions)."""
    if not LLM_ENABLED:
        return run_offline_agent(user_query, sid)
    now = datetime.now()
    system = (AGENT_SYSTEM_PROMPT + f"\n\nNow: {now.strftime('%A %Y-%m-%d %H:%M')}. "
              f"Autonomy mode: {AGENT_AUTONOMY} ({'actions run immediately' if AGENT_AUTONOMY == 'auto' else 'actions need user approval'}).")
    hint = warehouse.find_container_id_in_text(user_query)
    user_msg = user_query + (f"\n(Container id detected in the message: {hint})" if hint else "")
    messages = [{"role": "system", "content": system}, *list(_history(sid)), {"role": "user", "content": user_msg}]
    steps, pending = [], []

    for _ in range(AGENT_MAX_STEPS):
        msg, err = _llm_chat(messages, TOOL_SCHEMAS)
        if err:
            return run_offline_agent(user_query, sid, note=f"📴 AI model unavailable ({err}) — answering in offline mode.\n\n")
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "I couldn't produce an answer.").strip(), steps, pending
        norm = []
        for k, call in enumerate(calls):
            fn = call.get("function") or {}
            nm = re.sub(r"<\|.*?\|>", "", str(fn.get("name") or "")).strip().split(".")[-1]
            raw = fn.get("arguments")
            entry = dict(call)                       # keep unknown fields, e.g. Gemini's extra_content.google.thought_signature
            entry.pop("index", None)
            entry.update({"id": call.get("id") or f"call_{k}", "type": "function",
                          "function": {**fn, "name": nm, "arguments": raw if isinstance(raw, str) else json.dumps(raw or {})}})
            norm.append(entry)
        calls = norm
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                if not isinstance(args, dict): args = {}
            except ValueError:
                args = {}
            try:
                if name in READ_TOOLS:
                    result = READ_TOOLS[name](**args)
                elif name in WRITE_TOOLS:
                    result = propose_write(name, {k: v for k, v in args.items() if k != "reason"}, sid)
                    if result.get("status") == "pending_user_approval":
                        pending.append({"id": result["action_id"], "tool": name, "summary": result["summary"],
                                        "reason": args.get("reason", "")})
                else:
                    result = {"error": f"Unknown tool {name}"}
            except Exception as e:
                result = {"error": f"Tool {name} failed: {e}"}
            steps.append({"tool": name, "args": args})
            agent_log("tool", name, args, result if len(json.dumps(result, default=str)) < 600 else "(large result)")
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": json.dumps(result, default=str)[:6000]})
    return "I hit my step limit before finishing. Try a narrower question.", steps, pending


# ---------- BACKGROUND MONITOR (proactive, rule-based: no LLM cost) ----------
MONITOR_STATE = {"last_run": None, "insights": []}


def run_monitor_once():
    now = datetime.now()
    live = [c for c in list(warehouse.containers.values()) if c.status == "in_warehouse"]
    out = []

    def add(rule, sev, title, cs):
        if cs:
            ids = [c.id for c in cs]
            out.append({"rule": rule, "severity": sev, "title": f"{len(cs)} {title}",
                        "containers": ids[:8], "more": max(0, len(ids) - 8)})

    add("overdue_exit", "critical", "container(s) past their scheduled exit", [c for c in live if c.scheduled_exit_date < now])
    add("exit_24h", "info", "container(s) due to exit within 24h",
        [c for c in live if now <= c.scheduled_exit_date <= now + timedelta(hours=24)])
    add("gate_risk", "warning", "high/critical container(s) with gate problems",
        [c for c in live if c.risk_level in ("high", "critical") and c.gate_problems not in (None, "None", "")])
    add("humidity", "warning", "humidity-sensitive container(s) above 70% humidity",
        [c for c in live if c.contents in ("electronics", "fragile", "textiles") and c.humidity > 70])
    add("cold_zone_temp", "warning", "container(s) in Cold Storage warmer than 8°C", [c for c in live if c.zone == "C" and c.temperature > 8])
    add("chem_heat", "critical", "chemical container(s) above 25°C", [c for c in live if c.contents == "chemicals" and c.temperature > 25])
    cap = warehouse.get_financial_summary()["kpis"]["warehouse_utilization"]
    if cap >= 85:
        out.append({"rule": "capacity", "severity": "warning", "title": f"Warehouse capacity at {cap}%", "containers": [], "more": 0})
    sev_rank = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda i: sev_rank[i["severity"]])
    MONITOR_STATE["insights"] = out
    MONITOR_STATE["last_run"] = now.isoformat(timespec='seconds')


_MON_LOCK = threading.Lock()

def run_monitor_if_stale():
    """Free hosts sleep and may run several workers, so the monitor also refreshes on demand:
    whenever the UI or the agent asks for insights and they're older than the interval."""
    last = MONITOR_STATE["last_run"]
    if last and (datetime.now() - datetime.fromisoformat(last)).total_seconds() < AGENT_MONITOR_SECONDS:
        return
    if _MON_LOCK.acquire(blocking=False):
        try:
            run_monitor_once()
        finally:
            _MON_LOCK.release()


def _monitor_loop():
    while True:
        try:
            run_monitor_once()
        except Exception as e:
            print(f"[monitor] {e}")
        _time.sleep(AGENT_MONITOR_SECONDS)


def start_monitor():
    threading.Thread(target=_monitor_loop, daemon=True, name="warehouse-monitor").start()


# ---------- keep retrieval as one tool (kept from v5.6) ----------


# ===================== ALERT SYSTEM =====================

class AlertSystem:
    def __init__(self):
        self.acknowledged_alerts = set()

    def create_alert(self, container_id, alert_type, message, severity="warning"):
        """Create an alert for a container"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO alerts (container_id, alert_type, alert_message, severity)
                     VALUES (?, ?, ?, ?)''',
                  (container_id, alert_type, message, severity))
        conn.commit()
        conn.close()

    def get_active_alerts(self):
        """Get only unacknowledged alerts"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT * FROM alerts WHERE is_resolved = 0 ORDER BY created_at DESC LIMIT 20')

        columns = [desc[0] for desc in c.description]
        alerts = [dict(zip(columns, row)) for row in c.fetchall()]
        conn.close()

        return alerts

# ===================== WAREHOUSE SYSTEM =====================

class WarehouseSystem:
    def __init__(self):
        self.containers = {}
        self.start_time = datetime.now()
        self.total_processed = 0
        self.alert_system = AlertSystem()

    def _register_container(self, container):
        """Shared bookkeeping for any newly created container, however it was created."""
        self.containers[container.id] = container
        container.save_to_db()

        if container.risk_level == "critical":
            self.alert_system.create_alert(container.id, "CRITICAL_ITEM",
                f"⚠️ CRITICAL: {container.contents} requires special handling in Zone {container.zone}", "critical")
        elif container.risk_level == "high":
            self.alert_system.create_alert(container.id, "HIGH_RISK",
                f"High-risk {container.contents} detected in Zone {container.zone}", "warning")

        return container

    def get_containers_by_zone(self, zone_letter):
        return [c for c in self.containers.values() if c.zone.upper() == zone_letter.upper()]

    def get_containers_by_risk(self, risk_level):
        return [c for c in self.containers.values() if c.risk_level.lower() == risk_level.lower()]

    def get_containers_by_contents(self, contents):
        normalized = contents.lower().replace(" ", "_")
        return [c for c in self.containers.values() if c.contents.lower() == normalized]

    def get_containers_with_gate_problems(self):
        return [c for c in self.containers.values() if c.gate_problems and c.gate_problems != "None"]

    def find_container_id_in_text(self, text):
        """Look for any known container ID appearing anywhere in free text. This works
        for any ID format (not just a specific regex pattern), since QR codes can carry
        arbitrary container IDs."""
        if not text:
            return None
        text_lower = text.lower()
        for cid in self.containers.keys():
            if cid.lower() in text_lower:
                return cid
        return None

    def _full(self):
        return len(self.containers) >= MAX_CONTAINERS

    def add_container_from_qr(self, data):
        """Register a container from data decoded out of a scanned QR code (camera or
        uploaded image). `data` is whatever parse_qr_payload() returned. Returns None if
        a container with that ID already exists, or if the data has no usable ID."""
        container_id = data.get("id") if data else None
        if not container_id or container_id in self.containers or self._full():
            return None
        container = Container.from_scanned_data(data)
        if container is None:
            return None
        return self._register_container(container)

    def generate_random_container(self):
        if self._full():
            return None
        random_id = f"CONT_RAND_{uuid.uuid4().hex[:8].upper()}"
        container = Container.from_scanned_data({"id": random_id})
        if container is None:
            return None
        return self._register_container(container)

    def scan_container(self, container_id):
        if container_id in self.containers:
            c = self.containers[container_id]
            c.scan_count += 1
            c.last_scanned = datetime.now()
            c.save_to_db()
            return c.to_dict()
        return None

    def checkout_container(self, container_id):
        if container_id in self.containers:
            c = self.containers[container_id]
            c.exit_date = datetime.now()
            c.status = "checked_out"
            c.save_to_db()
            self.total_processed += 1
            return True
        return False

    def get_upcoming_exits(self):
        all_containers = list(self.containers.values())
        in_warehouse = [c for c in all_containers if c.status == "in_warehouse"]
        sorted_containers = sorted(in_warehouse, key=lambda x: x.scheduled_exit_date)
        return [c.to_dict() for c in sorted_containers[:10]]

    def get_financial_summary(self):
        all_containers = list(self.containers.values())
        checked_in = [c for c in all_containers if c.status == "in_warehouse"]
        checked_out = [c for c in all_containers if c.status == "checked_out"]

        exchange_rate = COMPANY_CONFIG['exchange_rate_usd_to_tnd']

        processing_revenue_usd = len(checked_out) * COMPANY_CONFIG['processing_fee_per_container']
        theft_prevention_usd = len(checked_in) * COMPANY_CONFIG['theft_prevention_value_per_container']
        loss_prevention_usd = len(checked_in) * COMPANY_CONFIG['loss_prevention_value_per_container']

        total_goods_value = sum([c.container_value for c in all_containers])
        insurance_savings_usd = total_goods_value * COMPANY_CONFIG['insurance_savings_percentage']

        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        uptime_days = max(uptime_seconds / 86400, 1)
        operational_cost_usd = uptime_days * COMPANY_CONFIG['daily_operational_cost']

        high_risk_containers = len([c for c in all_containers if c.risk_level in ['high', 'critical']])
        high_risk_premium_usd = high_risk_containers * 200

        total_revenue_usd = processing_revenue_usd + theft_prevention_usd + loss_prevention_usd + insurance_savings_usd + high_risk_premium_usd
        net_profit_usd = total_revenue_usd - operational_cost_usd
        profit_margin = (net_profit_usd / total_revenue_usd * 100) if total_revenue_usd > 0 else 0

        revenue_per_container = total_revenue_usd / len(all_containers) if all_containers else 0
        avg_container_value = total_goods_value / len(all_containers) if all_containers else 0
        containers_per_day = len(all_containers) / uptime_days if uptime_days else 0
        roi = (net_profit_usd / operational_cost_usd * 100) if operational_cost_usd > 0 else 0
        warehouse_utilization = (len(checked_in) / 500) * 100

        return {
            "revenue": {
                "processing_usd": round(processing_revenue_usd, 2),
                "processing_tnd": round(processing_revenue_usd * exchange_rate, 2),
                "theft_prevention_usd": round(theft_prevention_usd, 2),
                "theft_prevention_tnd": round(theft_prevention_usd * exchange_rate, 2),
                "loss_prevention_usd": round(loss_prevention_usd, 2),
                "loss_prevention_tnd": round(loss_prevention_usd * exchange_rate, 2),
                "insurance_usd": round(insurance_savings_usd, 2),
                "insurance_tnd": round(insurance_savings_usd * exchange_rate, 2),
                "high_risk_usd": round(high_risk_premium_usd, 2),
                "high_risk_tnd": round(high_risk_premium_usd * exchange_rate, 2),
                "total_usd": round(total_revenue_usd, 2),
                "total_tnd": round(total_revenue_usd * exchange_rate, 2),
            },
            "costs": {
                "daily_usd": COMPANY_CONFIG['daily_operational_cost'],
                "daily_tnd": round(COMPANY_CONFIG['daily_operational_cost'] * exchange_rate, 2),
                "total_usd": round(operational_cost_usd, 2),
                "total_tnd": round(operational_cost_usd * exchange_rate, 2),
            },
            "profit": {
                "net_usd": round(net_profit_usd, 2),
                "net_tnd": round(net_profit_usd * exchange_rate, 2),
                "margin": round(profit_margin, 2),
            },
            "kpis": {
                "revenue_per_container_usd": round(revenue_per_container, 2),
                "avg_container_value": round(avg_container_value, 2),
                "containers_per_day": round(containers_per_day, 2),
                "roi_percentage": round(roi, 2),
                "warehouse_utilization": round(warehouse_utilization, 2),
                "total_containers": len(all_containers),
                "in_warehouse": len(checked_in),
                "processed": len(checked_out),
                "high_risk_items": high_risk_containers,
            }
        }

    def get_container_revenue(self, container_id):
        """Revenue/value attributable to ONE specific container, using the exact same
        per-unit figures as get_financial_summary(), so the numbers always add up to
        the warehouse-wide totals. Also expresses it against the "no AI system" baseline
        (processing fee only) to show how much extra value the AI agent is generating."""
        if container_id not in self.containers:
            return None
        c = self.containers[container_id]
        exchange_rate = COMPANY_CONFIG['exchange_rate_usd_to_tnd']

        processing_usd = COMPANY_CONFIG['processing_fee_per_container'] if c.status == 'checked_out' else 0
        theft_prevention_usd = COMPANY_CONFIG['theft_prevention_value_per_container'] if c.status == 'in_warehouse' else 0
        loss_prevention_usd = COMPANY_CONFIG['loss_prevention_value_per_container'] if c.status == 'in_warehouse' else 0
        insurance_usd = c.container_value * COMPANY_CONFIG['insurance_savings_percentage']
        high_risk_usd = 200 if c.risk_level in ('high', 'critical') else 0

        ai_generated_usd = theft_prevention_usd + loss_prevention_usd + insurance_usd + high_risk_usd
        total_usd = processing_usd + ai_generated_usd
        baseline_usd = processing_usd

        return {
            "id": c.id,
            "order_number": c.order_number,
            "status": c.status,
            "contents": c.contents,
            "risk_level": c.risk_level,
            "zone": c.zone,
            "container_value": round(c.container_value, 2),
            "breakdown_usd": {
                "processing": round(processing_usd, 2),
                "theft_prevention": round(theft_prevention_usd, 2),
                "loss_prevention": round(loss_prevention_usd, 2),
                "insurance_savings": round(insurance_usd, 2),
                "high_risk_premium": round(high_risk_usd, 2),
            },
            "breakdown_tnd": {
                "processing": round(processing_usd * exchange_rate, 2),
                "theft_prevention": round(theft_prevention_usd * exchange_rate, 2),
                "loss_prevention": round(loss_prevention_usd * exchange_rate, 2),
                "insurance_savings": round(insurance_usd * exchange_rate, 2),
                "high_risk_premium": round(high_risk_usd * exchange_rate, 2),
            },
            "ai_generated_usd": round(ai_generated_usd, 2),
            "ai_generated_tnd": round(ai_generated_usd * exchange_rate, 2),
            "baseline_usd": round(baseline_usd, 2),
            "baseline_tnd": round(baseline_usd * exchange_rate, 2),
            "total_usd": round(total_usd, 2),
            "total_tnd": round(total_usd * exchange_rate, 2),
            "ai_uplift_pct": round((ai_generated_usd / baseline_usd * 100), 1) if baseline_usd > 0 else None,
        }

    def get_stats(self):
        all_containers = list(self.containers.values())
        checked_in = [c for c in all_containers if c.status == "in_warehouse"]
        checked_out = [c for c in all_containers if c.status == "checked_out"]

        contents_dist = defaultdict(int)
        for c in all_containers:
            contents_dist[c.contents] += 1

        risk_dist = defaultdict(int)
        for c in all_containers:
            risk_dist[c.risk_level] += 1

        zone_dist = defaultdict(int)
        for c in all_containers:
            zone_dist[c.zone] += 1

        avg_util = sum([c.utilization_percentage for c in all_containers]) / len(all_containers) if all_containers else 0

        return {
            "total": len(all_containers),
            "checked_in": len(checked_in),
            "checked_out": len(checked_out),
            "contents_dist": dict(contents_dist),
            "risk_dist": dict(risk_dist),
            "zone_dist": dict(zone_dist),
            "avg_utilization": round(avg_util, 1),
            "containers": {cid: c.to_dict() for cid, c in self.containers.items()},
            "financial": self.get_financial_summary(),
            "alerts": self.alert_system.get_active_alerts(),
            "zones": ZoneSystem.ZONES,
            "upcoming_exits": self.get_upcoming_exits()
        }

warehouse = WarehouseSystem()

def load_containers_from_db():
    """Rebuild in-memory containers from SQLite so data survives restarts (v5.6 started
    empty every time even though the DB file persisted)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM containers ORDER BY order_number').fetchall()
    conn.close()
    loaded = 0
    for r in rows:
        try:
            c = Container.__new__(Container)
            c.id = r['id']
            c.qr_code = r['qr_code'] or ''
            c.order_number = r['order_number'] or 0
            c.entry_date = datetime.fromisoformat(r['entry_date'])
            c.exit_date = datetime.fromisoformat(r['exit_date']) if r['exit_date'] else None
            c.status = r['status'] or 'in_warehouse'
            c.contents = r['contents']
            c.weight = float(r['weight'])
            c.risk_level = r['risk_level'] or Container._risk_for_contents(c.contents)
            c.fragility = float(r['fragility'] or 0)
            c.warehouse_x = float(r['warehouse_x'] or 0)
            c.warehouse_y = float(r['warehouse_y'] or 0)
            c.zone = r['zone'] or ZoneSystem.get_zone(c.warehouse_x, c.warehouse_y)
            c.temperature = float(r['temperature'] or 20)
            c.humidity = float(r['humidity'] or 50)
            c.utilization_percentage = float(r['utilization_percentage'] or 0)
            c.gate_problems = r['gate_problems'] or 'None'
            c.scheduled_exit_date = (datetime.fromisoformat(r['scheduled_exit_date'])
                                     if r['scheduled_exit_date'] else c.entry_date + timedelta(days=3))
            # priority is not a DB column; it was defined as days-until-exit at entry (1-7)
            c.priority = max(1, min(7, round((c.scheduled_exit_date - c.entry_date).total_seconds() / 86400)))
            c.container_value = float(r['container_value'] or 5000)
            c.last_scanned = datetime.fromisoformat(r['last_scanned']) if r['last_scanned'] else c.entry_date
            c.scan_count = int(r['scan_count'] or 0)
            warehouse.containers[c.id] = c
            Container.counter = max(Container.counter, c.order_number)
            if c.status == 'checked_out':
                warehouse.total_processed += 1
            loaded += 1
        except Exception as e:
            print(f"[load] skipped container {r['id']}: {e}")
    # Older runs reused order numbers, so never let the counter fall below the row count.
    Container.counter = max(Container.counter, len(warehouse.containers))
    return loaded

# ---------- DEMO DATA (so a submitted/deployed demo is never empty) ----------
DEMO_SEED = os.environ.get('DEMO_SEED', '0') == '1'


def seed_demo_data(n=28):
    """Create realistic, deterministic demo containers relative to *now* (some overdue, some leaving soon,
    a few hot/humid/gate problems, a few already checked out). Runs only when the database is empty."""
    rnd = random.Random(42)
    now = datetime.now()
    kinds = ["electronics", "fragile", "chemicals", "textiles", "heavy_machinery", "mixed"]
    weights = [3, 2, 3, 2, 2, 2]
    gate_issues = ["Seal broken", "Documents missing", "Weight mismatch"]
    created = []
    for i in range(1, n + 1):
        zone = rnd.choice("ABCDEF")
        z = ZoneSystem.ZONES[zone]
        contents = rnd.choices(kinds, weights)[0]
        temp = round(rnd.uniform(2, 12), 1) if zone == "C" else (round(rnd.uniform(18, 31), 1) if contents == "chemicals" else round(rnd.uniform(16, 27), 1))
        risk = Container._risk_for_contents(contents)
        data = {"id": f"CONT_DEMO_{i:03d}", "contents": contents, "weight": round(rnd.uniform(800, 24000), 1),
                "risk_level": risk, "fragility": round(rnd.uniform(0.1, 0.95), 2), "zone": zone,
                "warehouse_x": round(rnd.uniform(z["x"] + 2, z["x"] + z["width"] - 2), 1),
                "warehouse_y": round(rnd.uniform(z["y"] + 2, z["y"] + z["height"] - 2), 1),
                "temperature": temp, "humidity": round(rnd.uniform(35, 82), 1),
                "utilization_percentage": round(rnd.uniform(55, 98), 1),
                "gate_problems": rnd.choice(gate_issues) if (risk in ("high", "critical") and rnd.random() < 0.22) else "None",
                "priority": rnd.randint(1, 7), "container_value": round(rnd.uniform(4000, 52000), 2)}
        c = Container.from_scanned_data(data)
        if c is None:
            continue
        c.entry_date = now - timedelta(days=rnd.uniform(0.4, 6))
        c.scheduled_exit_date = c.entry_date + timedelta(days=c.priority)
        c.last_scanned = c.entry_date
        warehouse._register_container(c)
        created.append(c)
    # make sure a couple of containers are due within 24h
    for c, hours in zip(created[:2], (6, 18)):
        c.scheduled_exit_date = now + timedelta(hours=hours)
        c.save_to_db()
    # a few already processed so the financial dashboard shows processing revenue
    for c in created[-4:]:
        warehouse.checkout_container(c.id)
    return len(created)



_init_agent_tables()
LOADED_ON_START = load_containers_from_db()
if DEMO_SEED and not warehouse.containers:
    LOADED_ON_START = seed_demo_data()
    print(f"[demo] database was empty -> seeded {LOADED_ON_START} demo containers")
run_monitor_once()

# ===================== HTML TEMPLATE =====================

BASE_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏭 Warehouse AI Logistics v6.0 AGENT</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-1: #f3ecdd;
            --bg-2: #e9dfc8;
            --card-1: #fffdf8;
            --card-2: #fbf4e6;
            --accent: #a9754b;
            --accent-2: #7c5636;
            --accent-soft: rgba(169, 117, 75, 0.12);
            --accent-soft-2: rgba(169, 117, 75, 0.22);
            --text-main: #3d3126;
            --text-soft: #8c7a63;
            --text-faint: #a99a84;
            --success: #6f9a56;
            --success-2: #557a40;
            --warning: #cf9a3e;
            --danger: #c15b45;
            --danger-2: #9c4433;
            --critical: #ad3f2e;
            --border-soft: rgba(169, 117, 75, 0.28);
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--bg-1) 0%, var(--bg-2) 100%);
            color: var(--text-main);
            min-height: 100vh;
        }

        .navbar {
            background: linear-gradient(135deg, #fffdf8 0%, #f6ecd9 100%);
            padding: 18px 35px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(140, 105, 65, 0.12);
            position: sticky;
            top: 0;
            z-index: 1000;
            border-bottom: 3px solid var(--accent);
            flex-wrap: wrap;
            gap: 20px;
        }

        .navbar h1 {
            font-size: 26px;
            font-weight: 700;
            color: var(--accent-2);
            letter-spacing: 0.5px;
        }

        .nav-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .nav-btn {
            background: var(--accent-soft);
            color: var(--accent-2);
            border: 2px solid var(--accent);
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 12px;
        }

        .nav-btn:hover, .nav-btn.active {
            background: var(--accent);
            color: #fffdf8;
        }

        .status-badge {
            background: linear-gradient(135deg, var(--success), var(--success-2));
            color: #fffdf8;
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 12px;
            font-weight: 700;
            box-shadow: 0 4px 15px rgba(111, 154, 86, 0.3);
        }

        .container {
            max-width: 1900px;
            margin: 0 auto;
            padding: 25px;
        }

        .page { display: none; }
        .page.active { display: block; animation: slideIn 0.4s ease-out; }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .controls {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
            border-left: 4px solid var(--accent);
            box-shadow: 0 5px 18px rgba(140, 105, 65, 0.08);
        }

        button {
            background: linear-gradient(135deg, var(--accent), var(--accent-2));
            color: #fffdf8;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 13px;
        }

        button:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(169, 117, 75, 0.35); }
        button.danger { background: linear-gradient(135deg, var(--danger), var(--danger-2)); }
        button.success { background: linear-gradient(135deg, var(--success), var(--success-2)); }

        select, .select-like {
            background: #fffdf8;
            color: var(--text-main);
            border: 2px solid var(--accent);
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }

        .card {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 18px rgba(140, 105, 65, 0.10);
            border: 2px solid var(--border-soft);
            transition: all 0.3s ease;
        }

        .card:hover {
            transform: translateY(-8px);
            border-color: var(--accent);
        }

        .card.clickable {
            cursor: pointer;
            position: relative;
        }

        .card.clickable::after {
            content: "Click to view →";
            position: absolute;
            bottom: 14px;
            right: 18px;
            font-size: 10px;
            font-weight: 700;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.3px;
            opacity: 0.75;
        }

        .back-to-dashboard-btn {
            margin-bottom: 18px;
        }

        .card h3 {
            color: var(--accent-2);
            margin-bottom: 12px;
            font-size: 14px;
            font-weight: 700;
            text-transform: uppercase;
        }

        .stat-value {
            font-size: 42px;
            font-weight: 800;
            color: var(--accent);
            margin: 12px 0;
        }

        .stat-label {
            color: var(--text-soft);
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 600;
        }

        .section {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border-left: 4px solid var(--accent);
            box-shadow: 0 5px 18px rgba(140, 105, 65, 0.10);
        }

        .section h2 {
            color: var(--accent-2);
            margin-bottom: 20px;
            font-size: 22px;
            font-weight: 700;
        }

        .section h3 { color: var(--accent-2); }

        .subtext { color: var(--text-soft); font-size: 13px; }

        /* TOAST NOTIFICATION SYSTEM */
        .toast-container {
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 350px;
        }

        .toast {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-left: 4px solid var(--accent);
            border-radius: 8px;
            padding: 15px;
            color: var(--text-main);
            font-size: 13px;
            box-shadow: 0 5px 20px rgba(140, 105, 65, 0.22);
            animation: slideInRight 0.3s ease-out;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 10px;
        }

        .toast.critical {
            border-left-color: var(--critical);
            background: linear-gradient(135deg, rgba(173, 63, 46, 0.10), rgba(173, 63, 46, 0.05));
        }

        .toast.warning {
            border-left-color: var(--warning);
            background: linear-gradient(135deg, rgba(207, 154, 62, 0.12), rgba(207, 154, 62, 0.06));
        }

        .toast.info {
            border-left-color: var(--accent);
            background: linear-gradient(135deg, rgba(169, 117, 75, 0.10), rgba(169, 117, 75, 0.05));
        }

        .toast.success {
            border-left-color: var(--success);
            background: linear-gradient(135deg, rgba(111, 154, 86, 0.12), rgba(111, 154, 86, 0.06));
        }

        .toast-content { flex: 1; }
        .toast-title { font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; color: var(--text-main); }
        .toast-message { color: var(--text-soft); font-size: 12px; line-height: 1.4; }
        .toast-actions { display: flex; gap: 8px; margin-top: 10px; }
        .toast-btn { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 700; transition: all 0.3s; }
        .toast-btn-ack { background: var(--accent); color: #fffdf8; }
        .toast-btn-ack:hover { background: var(--accent-2); }
        .toast-btn-close { background: rgba(140, 105, 65, 0.15); color: var(--text-main); }
        .toast-btn-close:hover { background: rgba(140, 105, 65, 0.25); }

        @keyframes slideInRight {
            from { transform: translateX(400px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        @keyframes slideOutRight {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(400px); opacity: 0; }
        }

        .toast.removing { animation: slideOutRight 0.3s ease-out forwards; }
        .toast-progress { position: absolute; bottom: 0; left: 0; height: 3px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); border-radius: 0 0 8px 0; }

        /* TABLE STYLES */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }

        th {
            background: linear-gradient(135deg, var(--accent), var(--accent-2));
            color: #fffdf8;
            padding: 15px;
            text-align: left;
            font-weight: 700;
            font-size: 12px;
            text-transform: uppercase;
        }

        td {
            padding: 12px 15px;
            border-bottom: 1px solid var(--border-soft);
            font-size: 13px;
            color: var(--text-main);
        }

        tr:hover { background: var(--accent-soft); }

        .badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }

        .badge-success { background: var(--success); color: #fffdf8; }
        .badge-warning { background: var(--warning); color: #3d3126; }
        .badge-danger { background: var(--danger); color: #fffdf8; }
        .badge-critical { background: var(--critical); color: #fffdf8; }
        .badge-info { background: var(--accent); color: #fffdf8; }

        /* FINANCIAL DASHBOARD */
        .financial-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }

        .financial-card {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 15px;
            padding: 25px;
            border-left: 5px solid var(--accent);
            box-shadow: 0 5px 18px rgba(140, 105, 65, 0.10);
            transition: all 0.3s ease;
        }

        .financial-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 15px 35px rgba(140, 105, 65, 0.18);
        }

        .financial-label {
            color: var(--text-soft);
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .financial-value {
            font-size: 32px;
            font-weight: 800;
            color: var(--accent-2);
            margin: 8px 0;
        }

        .financial-sub { color: var(--text-soft); font-size: 12px; }

        .kpi-table {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }

        .kpi-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }

        .kpi-item {
            background: var(--accent-soft);
            border-left: 3px solid var(--accent);
            padding: 15px;
            border-radius: 8px;
            transition: all 0.3s ease;
        }

        .kpi-item:hover {
            background: var(--accent-soft-2);
            transform: translateX(5px);
        }

        .kpi-name {
            color: var(--text-soft);
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 24px;
            font-weight: 800;
            color: var(--accent-2);
        }

        /* AI IMPACT PANEL */
        .ai-impact-panel {
            background: linear-gradient(135deg, #fffaf0, #f3e6cf);
            border: 2px solid var(--accent);
            border-radius: 15px;
            padding: 25px;
            margin-top: 20px;
        }

        .ai-impact-bars { margin-top: 18px; }

        .ai-bar-row { margin-bottom: 16px; }

        .ai-bar-label {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 6px;
            text-transform: uppercase;
        }

        .ai-bar-track {
            width: 100%;
            height: 22px;
            background: rgba(140, 105, 65, 0.12);
            border-radius: 11px;
            overflow: hidden;
        }

        .ai-bar-fill {
            height: 100%;
            border-radius: 11px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 10px;
            color: #fffdf8;
            font-size: 11px;
            font-weight: 700;
            transition: width 0.6s ease;
            white-space: nowrap;
        }

        .ai-bar-fill.baseline { background: linear-gradient(90deg, var(--text-faint), var(--text-soft)); }
        .ai-bar-fill.total { background: linear-gradient(90deg, var(--accent), var(--success)); }

        /* CONTAINER REVENUE LOOKUP */
        .container-lookup-panel {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 15px;
            padding: 25px;
            margin-top: 20px;
            border-left: 5px solid var(--accent);
        }

        .container-lookup-controls {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: center;
            margin-bottom: 20px;
        }

        #containerRevenueSelect { min-width: 280px; }

        .revenue-breakdown-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
        }

        .revenue-line {
            background: var(--accent-soft);
            border-radius: 10px;
            padding: 14px 16px;
            border-left: 3px solid var(--accent);
        }

        .revenue-line .rl-label { font-size: 11px; text-transform: uppercase; color: var(--text-soft); font-weight: 700; }
        .revenue-line .rl-value { font-size: 20px; font-weight: 800; color: var(--accent-2); margin-top: 4px; }

        /* WAREHOUSE MAP */
        .warehouse-map {
            width: 100%;
            border: 3px solid var(--accent);
            border-radius: 12px;
            background: #fffdf8;
            position: relative;
        }

        .warehouse-map svg {
            width: 100%;
            height: auto;
            display: block;
        }

        .warehouse-zone {
            opacity: 0.55;
            stroke: var(--accent);
            stroke-width: 2;
            transition: all 0.3s ease;
        }

        .warehouse-zone:hover {
            opacity: 0.85;
            stroke: var(--accent-2);
            filter: drop-shadow(0 0 8px rgba(169,117,75,0.5));
        }

        .container-box {
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .container-box:hover {
            filter: drop-shadow(0 0 12px rgba(61,49,38,0.5));
            stroke-width: 3;
        }

        .container-label {
            font-size: 10px;
            font-weight: bold;
            text-anchor: middle;
            pointer-events: none;
            fill: #fffdf8;
        }

        .tooltip {
            position: absolute;
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border: 2px solid var(--accent);
            border-radius: 10px;
            padding: 15px;
            color: var(--text-main);
            font-size: 12px;
            z-index: 1001;
            max-width: 300px;
            box-shadow: 0 10px 35px rgba(140,105,65,0.25);
            display: none;
        }

        .tooltip h4 {
            color: var(--accent-2);
            margin-bottom: 8px;
            font-size: 14px;
        }

        .tooltip-row {
            display: flex;
            justify-content: space-between;
            margin: 4px 0;
            padding: 4px 0;
            border-bottom: 1px solid var(--border-soft);
        }

        .tooltip-label { color: var(--text-soft); font-weight: 600; }
        .tooltip-value { color: var(--accent-2); font-weight: 700; }

        /* PROGRESS BAR */
        .progress-bar {
            width: 100%;
            height: 8px;
            background: rgba(140, 105, 65, 0.18);
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--accent-2));
            transition: width 0.3s ease;
        }

        /* CHATBOT */
        .chatbot-panel {
            background: rgba(169, 117, 75, 0.04);
            border-radius: 12px;
            border: 2px solid var(--accent);
            display: flex;
            flex-direction: column;
            max-width: 900px;
        }

        .chatbot-messages {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            max-height: 520px;
            min-height: 250px;
        }

        .message {
            margin-bottom: 12px;
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 13px;
            line-height: 1.5;
            max-width: 100%;
            word-wrap: break-word;
            white-space: pre-wrap;
        }

        .message.bot {
            background: var(--accent-soft);
            border-left: 3px solid var(--accent);
            color: var(--text-main);
        }

        .message.user {
            background: var(--accent-soft-2);
            text-align: right;
            color: var(--accent-2);
        }

        .chatbot-suggestions {
            padding: 10px 15px;
            border-top: 1px solid var(--border-soft);
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            min-height: 36px;
        }

        .suggestion-btn {
            background: var(--accent-soft-2);
            color: var(--accent-2);
            border: 1px solid var(--accent);
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 600;
            transition: all 0.3s;
        }

        .suggestion-btn:hover {
            background: var(--accent);
            color: #fffdf8;
        }

        .chatbot-input-area {
            padding: 12px;
            border-top: 1px solid var(--border-soft);
            display: flex;
            gap: 8px;
        }

        .chatbot-input {
            flex: 1;
            background: #fffdf8;
            border: 1px solid var(--accent);
            color: var(--text-main);
            padding: 10px;
            border-radius: 6px;
            font-size: 13px;
        }

        .chatbot-input::placeholder { color: var(--text-faint); }

        .chatbot-send {
            background: var(--accent);
            color: #fffdf8;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }

        .chatbot-send:hover { transform: scale(1.05); }

        /* QR SCANNER */
        .qr-video-wrap {
            position: relative;
            border-radius: 12px;
            overflow: hidden;
            border: 2px solid var(--accent);
            background: #2a221a;
        }

        .qr-video-wrap video {
            width: 100%;
            display: block;
        }

        .qr-scan-log-entry {
            padding: 10px;
            margin-bottom: 8px;
            background: var(--accent-soft);
            border-left: 3px solid var(--accent);
            border-radius: 6px;
            font-size: 12px;
        }

        .analytics-block {
            background: linear-gradient(135deg, var(--card-1), var(--card-2));
            border-radius: 12px;
            padding: 18px;
            border: 1px solid var(--border-soft);
            box-shadow: 0 4px 14px rgba(140,105,65,0.08);
        }

        .analytics-block h4 {
            color: var(--accent-2);
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            margin-bottom: 8px;
        }

        footer {
            background: linear-gradient(135deg, #f6ecd9, #efe0c4);
            color: var(--text-soft);
            padding: 40px 30px;
            margin-top: 60px;
            border-top: 3px solid var(--accent);
            text-align: center;
            font-size: 12px;
        }

        @media (max-width: 768px) {
            .navbar h1 { font-size: 18px; }
            .nav-btn { font-size: 11px; padding: 8px 12px; }
            .toast-container { right: 10px; left: 10px; max-width: none; }
        }
        /* ===== AGENT UI ===== */
        .agent-topbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:12px; max-width:900px; }
        .agent-topbar .agent-label { font-size:12px; color:var(--text-soft); font-weight:600; text-transform:uppercase; }
        .briefing-btn { background:var(--accent); color:#fffdf8; border:none; padding:8px 14px; border-radius:6px; cursor:pointer; font-weight:600; font-size:12px; }
        .briefing-btn:disabled, .chatbot-send:disabled { opacity:.5; cursor:wait; }
        .agent-insights { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; max-width:900px; }
        .insight { border-radius:8px; padding:8px 12px; font-size:12px; cursor:pointer; border-left:4px solid #8a7b64; background:rgba(169,117,75,.08); color:var(--text-main); }
        .insight.critical { border-left-color:#b3261e; background:rgba(179,38,30,.10); }
        .insight.warning { border-left-color:#c98a1b; background:rgba(201,138,27,.12); }
        .insight.info { border-left-color:#2b5c7a; background:rgba(43,92,122,.10); }
        .insight.ok { border-left-color:#3f7a68; background:rgba(63,122,104,.10); cursor:default; }
        .insight-ids { display:block; color:var(--text-soft); font-size:11px; margin-top:2px; word-break:break-all; }
        .agent-steps { margin-top:8px; font-size:11px; color:var(--text-soft); white-space:normal; }
        .action-card { margin-top:10px; padding:10px 12px; border:1px dashed var(--accent); border-radius:8px; background:#fffdf8; white-space:normal; }
        .action-title { font-weight:700; font-size:11px; text-transform:uppercase; color:var(--accent-2); margin-bottom:4px; }
        .action-btns { display:flex; gap:8px; margin-top:8px; }
        .act-approve, .act-reject { border:none; padding:6px 12px; border-radius:6px; cursor:pointer; font-weight:600; font-size:12px; }
        .act-approve { background:#3f7a68; color:#fff; }
        .act-reject { background:#e9dfc8; color:#4a3f2e; }
        .act-approve:disabled, .act-reject:disabled { opacity:.5; cursor:default; }
        .action-result { font-size:12px; font-weight:600; }
    </style>
</head>
<body>
    <!-- NAVBAR -->
    <div class="navbar">
        <h1>🏭 Warehouse AI v6.0 AGENT</h1>
        <div class="nav-buttons">
            <button class="nav-btn active" data-page="qrscan">📷 Scan QR</button>
            <button class="nav-btn" data-page="dashboard">📊 Dashboard</button>
            <button class="nav-btn" data-page="warehouse">🏢 Warehouse</button>
            <button class="nav-btn" data-page="financial">💰 Financial</button>
            <button class="nav-btn" data-page="analytics">📈 Analytics</button>
            <button class="nav-btn" data-page="chatbot">🤖 AI Assistant</button>
        </div>
        <div class="status-badge" id="status">🟢 ONLINE</div>
    </div>

    <div class="container">
        <!-- DASHBOARD -->
        <div id="dashboard" class="page">
            <div class="controls">
                <button id="clearBtn" class="danger">🗑️ Clear All Data</button>
            </div>
            <p class="subtext" style="margin: -10px 0 20px;">
                Containers only enter the system by scanning a QR code (see the 📷 Scan QR section) — there's no
                random/simulated data here.
            </p>

            <div class="grid">
                <div class="card clickable" data-target="database">
                    <h3>📦 Total</h3>
                    <div class="stat-value" id="statTotal">0</div>
                    <div class="stat-label">View full database</div>
                </div>
                <div class="card clickable" data-target="utilization">
                    <h3>✅ In Warehouse</h3>
                    <div class="stat-value" id="statIn">0</div>
                    <div class="stat-label">View space utilization</div>
                </div>
                <div class="card clickable" data-target="exits">
                    <h3>📤 Processed</h3>
                    <div class="stat-value" id="statOut">0</div>
                    <div class="stat-label">View exit schedule</div>
                </div>
                <div class="card clickable" data-target="alerts">
                    <h3>🚨 Alerts</h3>
                    <div class="stat-value" id="statAlerts">0</div>
                    <div class="stat-label">View active alerts</div>
                </div>
            </div>
        </div>

        <!-- WAREHOUSE MAP -->
        <div id="warehouse" class="page">
            <div class="section">
                <h2>🏢 Real Warehouse Layout (150m x 100m)</h2>
                <div class="warehouse-map">
                    <svg id="warehouseSvg" viewBox="0 0 750 500" preserveAspectRatio="xMidYMid meet">
                        <defs>
                            <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
                                <path d="M 50 0 L 0 0 0 50" fill="none" stroke="rgba(169,117,75,0.12)" stroke-width="1"/>
                            </pattern>
                        </defs>
                        <rect width="750" height="500" fill="#fffdf8"/>
                        <rect width="750" height="500" fill="url(#grid)"/>
                        <g id="zones"></g>
                        <g id="containers"></g>
                    </svg>
                </div>
                <div id="zoneInfo" style="margin-top: 20px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;"></div>
            </div>
            <div id="tooltip" class="tooltip"></div>
        </div>

        <!-- DATABASE -->
        <div id="database" class="page">
            <div class="section">
                <button class="back-to-dashboard-btn" data-back="dashboard">← Back to Dashboard</button>
                <h2>📦 Container Database</h2>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Container ID</th>
                            <th>Status</th>
                            <th>Contents</th>
                            <th>Weight</th>
                            <th>Risk</th>
                            <th>Zone</th>
                            <th>Value</th>
                            <th>Scans</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="dbTable">
                        <tr><td colspan="10" style="text-align:center;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- UTILIZATION -->
        <div id="utilization" class="page">
            <div class="section">
                <button class="back-to-dashboard-btn" data-back="dashboard">← Back to Dashboard</button>
                <h2>💾 Space Utilization</h2>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Container ID</th>
                            <th>Category</th>
                            <th>Utilization</th>
                            <th>Status</th>
                            <th>Weight</th>
                            <th>Temp</th>
                            <th>Humidity</th>
                        </tr>
                    </thead>
                    <tbody id="utilTable">
                        <tr><td colspan="8" style="text-align:center;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- EXIT SCHEDULE -->
        <div id="exits" class="page">
            <div class="section">
                <button class="back-to-dashboard-btn" data-back="dashboard">← Back to Dashboard</button>
                <h2>📤 Exit Schedule</h2>
                <div id="exitsContainer" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px;"></div>
            </div>
        </div>

        <!-- ALERTS -->
        <div id="alerts" class="page">
            <div class="section">
                <button class="back-to-dashboard-btn" data-back="dashboard">← Back to Dashboard</button>
                <h2>🚨 Active Alerts</h2>
                <div id="alertsContainer"></div>
            </div>
        </div>

        <!-- FINANCIAL -->
        <div id="financial" class="page">
            <div class="section">
                <h2>💰 Financial Dashboard</h2>

                <div class="financial-grid">
                    <div class="financial-card">
                        <div class="financial-label">Total Revenue (USD)</div>
                        <div class="financial-value" id="finRevenue">$0</div>
                    </div>
                    <div class="financial-card">
                        <div class="financial-label">Total Revenue (TND)</div>
                        <div class="financial-value" id="finRevenueAlt">د.ت 0</div>
                    </div>
                    <div class="financial-card">
                        <div class="financial-label">Total Costs (USD)</div>
                        <div class="financial-value" id="finCosts">$0</div>
                    </div>
                    <div class="financial-card">
                        <div class="financial-label">Net Profit (USD)</div>
                        <div class="financial-value" id="finProfit">$0</div>
                    </div>
                    <div class="financial-card">
                        <div class="financial-label">Profit Margin</div>
                        <div class="financial-value" id="finMargin">0%</div>
                    </div>
                </div>

                <div class="section" style="border-left: 4px solid var(--success);">
                    <h3 style="color: var(--success-2);">📊 Revenue Breakdown</h3>
                    <div class="financial-grid">
                        <div class="financial-card">
                            <div class="financial-label">Processing Fees</div>
                            <div class="financial-value" id="revProcessing">$0</div>
                            <div class="financial-sub">Flat fee earned on checked-out containers</div>
                        </div>
                        <div class="financial-card">
                            <div class="financial-label">Theft Prevention</div>
                            <div class="financial-value" id="revTheft">$0</div>
                            <div class="financial-sub">Value protected by continuous AI monitoring</div>
                        </div>
                        <div class="financial-card">
                            <div class="financial-label">Loss Prevention</div>
                            <div class="financial-value" id="revLoss">$0</div>
                            <div class="financial-sub">Misplacement/damage avoided via tracking</div>
                        </div>
                        <div class="financial-card">
                            <div class="financial-label">Insurance Savings</div>
                            <div class="financial-value" id="revInsurance">$0</div>
                            <div class="financial-sub">Lower premiums from verified real-time data</div>
                        </div>
                    </div>
                </div>

                <!-- AI IMPACT PANEL -->
                <div class="ai-impact-panel">
                    <h3 style="color: var(--accent-2); margin-bottom: 6px;">🤖 How Much Revenue Is the AI Agent Generating?</h3>
                    <p class="subtext">
                        "Baseline" is what this operation would earn with <strong>no AI system</strong> — just the flat
                        processing fee per container. Everything above that line (theft prevention, loss prevention,
                        insurance savings and risk premiums) only exists because the AI agent is scanning, tracking,
                        and monitoring every container in real time.
                    </p>
                    <div class="ai-impact-bars">
                        <div class="ai-bar-row">
                            <div class="ai-bar-label"><span>Baseline (no AI) — processing fees only</span><span id="aiBaselineLabel">$0</span></div>
                            <div class="ai-bar-track"><div class="ai-bar-fill baseline" id="aiBaselineBar" style="width:0%">$0</div></div>
                        </div>
                        <div class="ai-bar-row">
                            <div class="ai-bar-label"><span>With AI Agent — total revenue</span><span id="aiTotalLabel">$0</span></div>
                            <div class="ai-bar-track"><div class="ai-bar-fill total" id="aiTotalBar" style="width:0%">$0</div></div>
                        </div>
                    </div>
                    <div class="financial-grid" style="margin-top: 18px; margin-bottom: 0;">
                        <div class="financial-card" style="border-left-color: var(--success);">
                            <div class="financial-label">Extra Revenue From AI</div>
                            <div class="financial-value" id="aiGeneratedValue" style="color: var(--success-2);">$0</div>
                            <div class="financial-sub">Theft + loss prevention + insurance + risk premiums</div>
                        </div>
                        <div class="financial-card" style="border-left-color: var(--success);">
                            <div class="financial-label">Revenue Uplift vs. No-AI Baseline</div>
                            <div class="financial-value" id="aiUpliftValue" style="color: var(--success-2);">0%</div>
                            <div class="financial-sub">How much more revenue the AI agent adds on top</div>
                        </div>
                    </div>
                </div>

                <!-- PER-CONTAINER REVENUE LOOKUP -->
                <div class="container-lookup-panel">
                    <h3>🔎 Revenue by Container</h3>
                    <p class="subtext" style="margin-bottom: 14px;">Pick any container to see exactly how much revenue it has generated and how the AI agent contributed to that number.</p>
                    <div class="container-lookup-controls">
                        <select id="containerRevenueSelect"><option value="">— Select a container —</option></select>
                        <button id="refreshContainerRevenueBtn">🔄 Refresh</button>
                    </div>
                    <div id="containerRevenueResult">
                        <p class="subtext">No container selected yet.</p>
                    </div>
                </div>

                <div class="kpi-table">
                    <h3 style="color: var(--accent-2); margin-bottom: 20px;">🎯 Key Performance Indicators (KPIs)</h3>
                    <div class="kpi-row" id="kpiContainer"></div>
                </div>
            </div>
        </div>

        <!-- ANALYTICS -->
        <div id="analytics" class="page">
            <div class="section">
                <h2>📈 AI Performance Analytics</h2>
                <p class="subtext" style="margin-bottom: 18px;">
                    A closer look at what the AI agent is tracking across the whole warehouse: composition, risk
                    posture, financial contribution, and how efficiently space and value are being managed.
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px;">
                    <div class="analytics-block"><h4>📦 Contents Distribution</h4><div id="chartContents"></div></div>
                    <div class="analytics-block"><h4>⚠️ Risk Distribution</h4><div id="chartRisk"></div></div>
                    <div class="analytics-block"><h4>🚦 Container Status</h4><div id="chartStatus"></div></div>
                    <div class="analytics-block"><h4>💰 Revenue Sources</h4><div id="chartRevenue"></div></div>
                    <div class="analytics-block"><h4>📍 Containers per Zone</h4><div id="chartZones"></div></div>
                    <div class="analytics-block"><h4>🔥 Risk × Zone Heatmap</h4><div id="chartHeatmap"></div></div>
                    <div class="analytics-block"><h4>💵 Value vs. Weight</h4><div id="chartScatter"></div></div>
                    <div class="analytics-block"><h4>📊 Avg. Utilization Gauge</h4><div id="chartGauge"></div></div>
                    <div class="analytics-block" style="grid-column: 1 / -1;"><h4>🧭 Revenue Funnel: Baseline → AI-Boosted Total</h4><div id="chartFunnel"></div></div>
                </div>
            </div>
        </div>

        <!-- QR SCAN -->
        <div id="qrscan" class="page active">
            <div class="section">
                <h2>📷 Scan QR Code to Add / Check In a Container</h2>
                <p class="subtext" style="margin-bottom:15px;">
                    Point your PC's camera at a container QR code, or upload a QR code image (screenshot, photo, or
                    downloaded PNG). Each QR code carries every field needed to fully register the container — contents,
                    weight, risk level, zone, value, and more — so nothing has to be guessed. If the container isn't in
                    the system yet, it's added automatically with that data. If it already exists, its scan count and
                    last-scanned time are updated instead. You can also generate fully randomized containers directly,
                    without needing a QR code at all.
                </p>
                <div class="controls">
                    <button id="startCamBtn" class="success">▶ Start Camera</button>
                    <button id="stopCamBtn" class="danger" style="display:none;">⏹ Stop Camera</button>
                    <button id="uploadBtn">📁 Upload QR Image</button>
                    <input type="file" id="qrImageInput" accept="image/*" style="display:none;">
                    <button id="startGenBtn" class="success">🎲 Start Generating</button>
                    <button id="stopGenBtn" class="danger" style="display:none;">⏹ Stop Generating</button>
                </div>
                <div style="display:flex; gap:20px; flex-wrap: wrap;">
                    <div style="flex: 1 1 380px; min-width: 300px;">
                        <div class="qr-video-wrap">
                            <video id="qrVideo" playsinline muted></video>
                        </div>
                        <canvas id="qrCanvas" style="display:none;"></canvas>
                    </div>
                    <div style="flex: 1 1 380px; min-width: 300px;">
                        <div id="qrResult" style="background: var(--accent-soft); border-radius:12px; padding:15px; min-height:80px; margin-bottom:15px;">
                            Camera is off. Click "Start Camera" and point it at a container QR code.
                        </div>
                        <h3 style="color:var(--accent-2); font-size:14px; margin-bottom:10px;">Scan Log</h3>
                        <div id="qrScanLog"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- AI ASSISTANT -->
        <div id="chatbot" class="page">
            <div class="section">
                <h2>🤖 Warehouse Operations Agent</h2>
                <div class="agent-topbar">
                    <span class="agent-label">Live monitor</span>
                    <span class="agent-label" id="agentMode" style="margin-left:auto;"></span>
                    <button id="briefingBtn" class="briefing-btn" onclick="requestBriefing()">📋 Run briefing</button>
                </div>
                <div class="agent-insights" id="agentInsights"></div>
                <div class="chatbot-panel">
                    <div class="chatbot-messages" id="chatMessages"></div>
                    <div class="chatbot-suggestions" id="chatSuggestions"></div>
                    <div class="chatbot-input-area">
                        <input type="text" id="chatInput" class="chatbot-input" placeholder="Ask or instruct… e.g. 'which critical containers exit this week?' or 'check out CONT_123'">
                        <button onclick="sendMessage()" class="chatbot-send">Send →</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <footer>
        <p>🏭 <strong>Warehouse AI Logistics v6.0 AGENT</strong> | Professional Enterprise System</p>
        <p>© 2026 Warehouse AI Logistics Inc. | Tunis, Tunisia | Founder: Mustapha Mazigh</p>
    </footer>

    <script>
        let lastData = {};
        let displayedAlertIds = new Set();
        let chatHistory = [];
        let currentPage = 'qrscan';

        const PALETTE = {
            accent: '#a9754b',
            accent2: '#7c5636',
            success: '#6f9a56',
            success2: '#557a40',
            warning: '#cf9a3e',
            danger: '#c15b45',
            critical: '#ad3f2e',
            textMain: '#3d3126',
            textSoft: '#8c7a63',
            cardBg: '#fffdf8',
            gridLine: 'rgba(169,117,75,0.15)'
        };
        const PLOTLY_PALETTE = ['#a9754b', '#6f9a56', '#cf9a3e', '#c15b45', '#7c5636', '#8a9a6f', '#b98c5e', '#5b7a94'];
        const PLOTLY_LAYOUT_BASE = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: PALETTE.textMain, family: 'Segoe UI, Tahoma, Verdana, sans-serif' },
            margin: { t: 40, l: 45, r: 20, b: 40 }
        };

        // ========== NOTIFICATION MANAGER ==========
        class NotificationManager {
            constructor() {
                this.notifications = [];
                this.toastContainer = null;
                this.init();
            }

            init() {
                if (!document.getElementById('toastContainer')) {
                    this.toastContainer = document.createElement('div');
                    this.toastContainer.id = 'toastContainer';
                    this.toastContainer.className = 'toast-container';
                    document.body.appendChild(this.toastContainer);
                } else {
                    this.toastContainer = document.getElementById('toastContainer');
                }
            }

            show(title, message, type = 'info', duration = 5000, alertId = null) {
                const id = Date.now();
                const toastEl = document.createElement('div');
                toastEl.className = `toast ${type}`;
                toastEl.id = `toast-${id}`;

                const iconMap = {
                    critical: '🚨',
                    warning: '⚠️',
                    info: 'ℹ️',
                    success: '✅'
                };

                toastEl.innerHTML = `
                    <div class="toast-content">
                        <div class="toast-title">
                            <span>${iconMap[type]}</span>
                            ${title}
                        </div>
                        <div class="toast-message">${message}</div>
                        ${alertId ? `<div class="toast-actions">
                            <button class="toast-btn toast-btn-ack" onclick="acknowledgeAlert('${alertId}', 'toast-${id}')">✓ Acknowledge</button>
                            <button class="toast-btn toast-btn-close" onclick="notificationManager.remove('toast-${id}')">✕ Dismiss</button>
                        </div>` : ''}
                    </div>
                    <div class="toast-progress" style="animation: shrinkWidth ${duration}ms linear forwards;"></div>
                `;

                this.toastContainer.appendChild(toastEl);

                if (!alertId) {
                    setTimeout(() => this.remove(`toast-${id}`), duration);
                }

                return id;
            }

            remove(id) {
                const toastEl = document.getElementById(id);
                if (toastEl) {
                    toastEl.classList.add('removing');
                    setTimeout(() => toastEl.remove(), 300);
                }
            }

            critical(title, message, alertId = null, duration = 6000) {
                return this.show(title, message, 'critical', duration, alertId);
            }

            warning(title, message, alertId = null, duration = 5000) {
                return this.show(title, message, 'warning', duration, alertId);
            }

            success(title, message, alertId = null, duration = 4000) {
                return this.show(title, message, 'success', duration, alertId);
            }
        }

        const notificationManager = new NotificationManager();
        const style = document.createElement('style');
        style.textContent = '@keyframes shrinkWidth { from { width: 100%; } to { width: 0%; } }';
        document.head.appendChild(style);

        // ========== ACKNOWLEDGE ALERT ==========
        async function acknowledgeAlert(alertId, toastId) {
            try {
                await fetch(`/api/alert/${alertId}/acknowledge`, {method: 'POST'});
                displayedAlertIds.add(alertId);
                notificationManager.remove(toastId);
            } catch(e) {
                console.log('Error acknowledging alert:', e);
            }
        }

        // ========== NAVIGATION ==========
        // Some pages (database, utilization, exits, alerts) no longer have their own
        // nav-bar button — they're reached via the clickable Dashboard cards instead,
        // and a "Back to Dashboard" button on each of them returns to the dashboard.
        // This single function drives every way of switching pages so they all stay
        // in sync (camera/generator cleanup, active states, page content refresh).
        function navigateToPage(page) {
            const target = document.getElementById(page);
            if (!target) return;

            if (currentPage === 'qrscan' && page !== 'qrscan') {
                stopCamera();
                stopGeneration();
            }

            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            target.classList.add('active');

            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            const navBtn = document.querySelector(`.nav-btn[data-page="${page}"]`);
            if (navBtn) navBtn.classList.add('active');

            currentPage = page;
            updatePageContent(page);
        }

        document.querySelectorAll('[data-page]').forEach(btn => {
            btn.addEventListener('click', function() {
                navigateToPage(this.getAttribute('data-page'));
            });
        });

        document.querySelectorAll('.card.clickable[data-target]').forEach(card => {
            card.addEventListener('click', function() {
                navigateToPage(this.getAttribute('data-target'));
            });
        });

        document.querySelectorAll('[data-back]').forEach(btn => {
            btn.addEventListener('click', function() {
                navigateToPage(this.getAttribute('data-back'));
            });
        });

        // ========== CONTROLS ==========
        document.getElementById('clearBtn').addEventListener('click', clearAll);

        async function checkoutContainer(containerId) {
            try {
                const res = await fetch(`/api/checkout/${encodeURIComponent(containerId)}`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'checked_out') {
                    notificationManager.success('Container Checked Out', `${containerId} marked as exited`);
                    await updateData();
                } else {
                    notificationManager.warning('Check Out Failed', data.message || 'Unknown error');
                }
            } catch (e) {
                notificationManager.warning('Check Out Failed', e.message);
            }
        }

        async function clearAll() {
            if (confirm('⚠️ Clear ALL data?')) {
                await fetch('/api/clear', {method: 'POST'});
                location.reload();
            }
        }

        // ========== DATA UPDATE ==========
        async function updateData() {
            try {
                const res = await fetch('/api/data');
                lastData = await res.json();
                updateStats();

                const alerts = lastData.alerts || [];
                alerts.forEach(alert => {
                    if (!displayedAlertIds.has(alert.id)) {
                        displayedAlertIds.add(alert.id);
                        notificationManager[alert.severity](
                            `${alert.alert_type}`,
                            alert.alert_message,
                            alert.id
                        );
                    }
                });

                updatePageContent(document.querySelector('.page.active').id);
            } catch(e) {console.log(e);}
        }

        function updateStats() {
            document.getElementById('statTotal').textContent = lastData.total || 0;
            document.getElementById('statIn').textContent = lastData.checked_in || 0;
            document.getElementById('statOut').textContent = lastData.checked_out || 0;
            document.getElementById('statAlerts').textContent = (lastData.alerts || []).length;
        }

        function updatePageContent(pageId) {
            if (pageId === 'warehouse') updateWarehouseMap();
            else if (pageId === 'database') updateDatabase();
            else if (pageId === 'utilization') updateUtilization();
            else if (pageId === 'exits') updateExits();
            else if (pageId === 'alerts') updateAlerts();
            else if (pageId === 'financial') updateFinancial();
            else if (pageId === 'analytics') updateCharts();
        }

        function updateWarehouseMap() {
            const svg = document.getElementById('warehouseSvg');
            const zonesGroup = svg.querySelector('#zones');
            const containersGroup = svg.querySelector('#containers');
            const zones = lastData.zones || {};
            const containers = Object.values(lastData.containers || {});

            zonesGroup.innerHTML = '';
            Object.entries(zones).forEach(([zoneId, zone]) => {
                const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                rect.setAttribute('x', (zone.x * 5));
                rect.setAttribute('y', (zone.y * 5));
                rect.setAttribute('width', (zone.width * 5));
                rect.setAttribute('height', (zone.height * 5));
                rect.setAttribute('fill', zone.color);
                rect.setAttribute('class', 'warehouse-zone');
                rect.setAttribute('opacity', '0.28');

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', (zone.x * 5 + zone.width * 2.5));
                text.setAttribute('y', (zone.y * 5 + zone.height * 2.5 + 5));
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('fill', '#5b4a38');
                text.setAttribute('font-size', '14');
                text.setAttribute('font-weight', 'bold');
                text.textContent = `${zoneId}`;

                zonesGroup.appendChild(rect);
                zonesGroup.appendChild(text);
            });

            containersGroup.innerHTML = '';
            containers.forEach(c => {
                const color = c.risk_level === 'critical' ? '#ad3f2e' :
                              c.risk_level === 'high' ? '#c15b45' :
                              c.status === 'checked_out' ? '#cf9a3e' : '#6f9a56';

                const box = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                box.setAttribute('x', (c.location.x * 5 - 12));
                box.setAttribute('y', (c.location.y * 5 - 12));
                box.setAttribute('width', '24');
                box.setAttribute('height', '24');
                box.setAttribute('fill', color);
                box.setAttribute('class', 'container-box');

                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('x', (c.location.x * 5));
                label.setAttribute('y', (c.location.y * 5 + 4));
                label.setAttribute('class', 'container-label');
                label.textContent = `#${c.order_number}`;

                box.addEventListener('mouseover', (e) => showTooltip(e, c));
                box.addEventListener('mouseout', hideTooltip);

                containersGroup.appendChild(box);
                containersGroup.appendChild(label);
            });

            const zoneInfo = document.getElementById('zoneInfo');
            const zoneCounts = lastData.zone_dist || {};
            zoneInfo.innerHTML = Object.entries(zones).map(([zoneId, zone]) => `
                <div style="background: linear-gradient(135deg, var(--card-1), var(--card-2)); border-radius: 12px; padding: 15px; border-left: 4px solid ${zone.color};">
                    <div style="color: #5b4a38; font-weight: 700; margin-bottom: 8px;">Zone ${zoneId}</div>
                    <div style="color: var(--text-soft); font-size: 12px; margin-bottom: 8px;">${zone.name}</div>
                    <div style="font-size: 24px; font-weight: 800; color: var(--accent-2);">${zoneCounts[zoneId] || 0}</div>
                </div>
            `).join('');
        }

        function showTooltip(event, container) {
            const tooltip = document.getElementById('tooltip');
            const riskBadge = container.risk_level === 'critical' ? 'badge-critical' :
                             container.risk_level === 'high' ? 'badge-danger' : 'badge-success';
            const statusBadge = container.status === 'in_warehouse' ? 'badge-success' : 'badge-warning';

            tooltip.innerHTML = `
                <h4>#${container.order_number} - ${container.id}</h4>
                <div class="tooltip-row">
                    <span class="tooltip-label">Status:</span>
                    <span class="badge ${statusBadge}">${container.status}</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Contents:</span>
                    <span class="tooltip-value">${container.contents.toUpperCase()}</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Weight:</span>
                    <span class="tooltip-value">${container.weight} kg</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Risk:</span>
                    <span class="badge ${riskBadge}">${container.risk_level.toUpperCase()}</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Zone:</span>
                    <span class="tooltip-value">${container.location.zone}</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Value:</span>
                    <span class="tooltip-value">$${container.container_value.toLocaleString('en', {maximumFractionDigits: 0})}</span>
                </div>
                <div class="tooltip-row">
                    <span class="tooltip-label">Temp:</span>
                    <span class="tooltip-value">${container.temperature}°C | ${container.humidity}%</span>
                </div>
            `;

            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX + 10) + 'px';
            tooltip.style.top = (event.clientY + 10) + 'px';
        }

        function hideTooltip() {
            document.getElementById('tooltip').style.display = 'none';
        }

        function updateDatabase() {
            const tbody = document.getElementById('dbTable');
            const containers = Object.values(lastData.containers || {}).slice(-50).reverse();

            tbody.innerHTML = containers.map(c => {
                const riskBadge = c.risk_level === 'critical' ? 'badge-critical' :
                                 c.risk_level === 'high' ? 'badge-danger' :
                                 c.risk_level === 'medium' ? 'badge-warning' : 'badge-success';
                const statusBadge = c.status === 'in_warehouse' ? 'badge-success' : 'badge-info';

                const checkoutCell = c.status === 'in_warehouse'
                    ? `<button style="padding:6px 10px; font-size:11px;" onclick="checkoutContainer('${c.id}')">✅ Check Out</button>`
                    : `<span class="badge badge-info">Exited</span>`;

                return `<tr>
                    <td><strong>#${c.order_number}</strong></td>
                    <td>${c.id}</td>
                    <td><span class="badge ${statusBadge}">${c.status}</span></td>
                    <td>${c.contents.toUpperCase()}</td>
                    <td>${c.weight} kg</td>
                    <td><span class="badge ${riskBadge}">${c.risk_level.toUpperCase()}</span></td>
                    <td>${c.location.zone}</td>
                    <td>$${c.container_value.toLocaleString('en', {maximumFractionDigits: 0})}</td>
                    <td>${c.scan_count}</td>
                    <td>${checkoutCell}</td>
                </tr>`;
            }).join('');
        }

        function updateUtilization() {
            const tbody = document.getElementById('utilTable');
            const containers = Object.values(lastData.containers || {}).slice(-50).reverse();

            tbody.innerHTML = containers.map(c => {
                const statusBadge = c.utilization >= 80 ? 'badge-success' :
                                   c.utilization >= 60 ? 'badge-warning' : 'badge-danger';

                return `<tr>
                    <td><strong>#${c.order_number}</strong></td>
                    <td>${c.id}</td>
                    <td>${c.contents.toUpperCase()}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${c.utilization}%"></div>
                        </div>
                        ${c.utilization}%
                    </td>
                    <td><span class="badge ${statusBadge}">${c.status}</span></td>
                    <td>${c.weight} kg</td>
                    <td>${c.temperature}°C</td>
                    <td>${c.humidity}%</td>
                </tr>`;
            }).join('');
        }

        function updateExits() {
            const container = document.getElementById('exitsContainer');
            const upcoming = lastData.upcoming_exits || [];

            if (!upcoming.length) {
                container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-soft); padding: 40px;">No scheduled exits</div>';
                return;
            }

            container.innerHTML = upcoming.slice(0, 20).map(c => {
                const exitDate = new Date(c.scheduled_exit_date);
                const daysDiff = Math.ceil((exitDate - new Date()) / (1000 * 60 * 60 * 24));
                const riskBadge = c.risk_level === 'critical' ? 'badge-critical' :
                                 c.risk_level === 'high' ? 'badge-danger' : 'badge-success';

                return `
                    <div style="background: linear-gradient(135deg, var(--card-1), var(--card-2)); border-radius: 12px; padding: 18px; border-left: 4px solid var(--accent);">
                        <div style="color: var(--accent-2); font-weight: 700; margin-bottom: 10px;">#${c.order_number}</div>
                        <div style="color: var(--text-soft); font-size: 12px; margin-bottom: 10px;">
                            <span class="badge ${riskBadge}" style="margin-right: 8px;">${c.risk_level.toUpperCase()}</span>
                            <span class="badge badge-info">${daysDiff} days</span>
                        </div>
                        <div style="color: var(--text-soft); font-size: 12px;">
                            <div>Category: ${c.contents.toUpperCase()}</div>
                            <div>Value: $${c.container_value.toLocaleString('en', {maximumFractionDigits: 0})}</div>
                            <div>Exit: ${exitDate.toLocaleDateString()}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function updateAlerts() {
            const alertsContainer = document.getElementById('alertsContainer');
            const alerts = lastData.alerts || [];

            if (!alerts.length) {
                alertsContainer.innerHTML = '<p style="color: var(--success-2); text-align: center; padding: 40px;">✅ No active alerts</p>';
                return;
            }

            alertsContainer.innerHTML = alerts.map(a => {
                const severityBadge = a.severity === 'critical' ? 'badge-critical' :
                                     a.severity === 'warning' ? 'badge-warning' : 'badge-info';
                return `
                    <div style="background: linear-gradient(135deg, var(--card-1), var(--card-2)); border-radius: 12px; padding: 15px; margin-bottom: 12px; border-left: 4px solid var(--accent);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <strong>${a.alert_type}</strong>
                            <span class="badge ${severityBadge}">${a.severity.toUpperCase()}</span>
                        </div>
                        <div style="color: var(--text-soft); margin-bottom: 8px;">${a.alert_message}</div>
                        <small style="color: var(--text-faint);">Container: ${a.container_id}</small>
                    </div>
                `;
            }).join('');
        }

        // ========== FINANCIAL ==========
        let containerRevenueDropdownPopulated = false;

        function updateFinancial() {
            if (!lastData.financial) return;

            const f = lastData.financial;
            const k = f.kpis;
            const ai = f.ai_impact || {};

            document.getElementById('finRevenue').textContent = '$' + f.revenue.total_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('finRevenueAlt').textContent = 'د.ت ' + f.revenue.total_tnd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('finCosts').textContent = '$' + f.costs.total_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('finProfit').textContent = '$' + f.profit.net_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('finMargin').textContent = f.profit.margin.toFixed(2) + '%';

            document.getElementById('revProcessing').textContent = '$' + f.revenue.processing_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('revTheft').textContent = '$' + f.revenue.theft_prevention_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('revLoss').textContent = '$' + f.revenue.loss_prevention_usd.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('revInsurance').textContent = '$' + f.revenue.insurance_usd.toLocaleString('en', {maximumFractionDigits: 0});

            // AI impact bars
            const baseline = ai.baseline_revenue_usd || 0;
            const totalRev = f.revenue.total_usd || 0;
            const maxScale = Math.max(baseline, totalRev, 1);
            document.getElementById('aiBaselineLabel').textContent = '$' + baseline.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('aiTotalLabel').textContent = '$' + totalRev.toLocaleString('en', {maximumFractionDigits: 0});
            const baselinePct = Math.max((baseline / maxScale) * 100, baseline > 0 ? 4 : 0);
            const totalPct = Math.max((totalRev / maxScale) * 100, totalRev > 0 ? 4 : 0);
            document.getElementById('aiBaselineBar').style.width = baselinePct + '%';
            document.getElementById('aiBaselineBar').textContent = '$' + baseline.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('aiTotalBar').style.width = totalPct + '%';
            document.getElementById('aiTotalBar').textContent = '$' + totalRev.toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('aiGeneratedValue').textContent = '$' + (ai.ai_generated_usd || 0).toLocaleString('en', {maximumFractionDigits: 0});
            document.getElementById('aiUpliftValue').textContent = (ai.ai_uplift_pct !== null && ai.ai_uplift_pct !== undefined) ? ai.ai_uplift_pct.toFixed(1) + '%' : 'N/A (no exits yet)';

            const kpiContainer = document.getElementById('kpiContainer');
            kpiContainer.innerHTML = `
                <div class="kpi-item"><div class="kpi-name">Total Containers</div><div class="kpi-value">${k.total_containers}</div></div>
                <div class="kpi-item"><div class="kpi-name">In Warehouse</div><div class="kpi-value">${k.in_warehouse}</div></div>
                <div class="kpi-item"><div class="kpi-name">Containers/Day</div><div class="kpi-value">${k.containers_per_day.toFixed(1)}</div></div>
                <div class="kpi-item"><div class="kpi-name">Revenue/Container</div><div class="kpi-value">$${k.revenue_per_container_usd.toLocaleString('en', {maximumFractionDigits: 0})}</div></div>
                <div class="kpi-item"><div class="kpi-name">Avg Container Value</div><div class="kpi-value">$${k.avg_container_value.toLocaleString('en', {maximumFractionDigits: 0})}</div></div>
                <div class="kpi-item"><div class="kpi-name">Warehouse Utilization</div><div class="kpi-value">${k.warehouse_utilization.toFixed(1)}%</div></div>
                <div class="kpi-item"><div class="kpi-name">ROI</div><div class="kpi-value">${k.roi_percentage.toFixed(1)}%</div></div>
                <div class="kpi-item"><div class="kpi-name">High-Risk Items</div><div class="kpi-value">${k.high_risk_items}</div></div>
            `;

            populateContainerRevenueDropdown();
        }

        function populateContainerRevenueDropdown() {
            const select = document.getElementById('containerRevenueSelect');
            const containers = Object.values(lastData.containers || {}).sort((a, b) => b.order_number - a.order_number);
            const previousValue = select.value;

            select.innerHTML = '<option value="">— Select a container —</option>' + containers.map(c =>
                `<option value="${c.id}">#${c.order_number} — ${c.id} (${c.contents.toUpperCase()})</option>`
            ).join('');

            if (previousValue && containers.some(c => c.id === previousValue)) {
                select.value = previousValue;
            }
        }

        async function loadContainerRevenue(containerId) {
            const resultDiv = document.getElementById('containerRevenueResult');
            if (!containerId) {
                resultDiv.innerHTML = '<p class="subtext">No container selected yet.</p>';
                return;
            }
            resultDiv.innerHTML = '<p class="subtext">Loading...</p>';
            try {
                const res = await fetch(`/api/container_revenue/${encodeURIComponent(containerId)}`);
                const data = await res.json();
                if (data.status !== 'ok') {
                    resultDiv.innerHTML = `<p class="subtext">❌ ${data.message || 'Could not load revenue for this container'}</p>`;
                    return;
                }
                const r = data.revenue;
                const b = r.breakdown_usd;
                const upliftText = (r.ai_uplift_pct !== null && r.ai_uplift_pct !== undefined)
                    ? `${r.ai_uplift_pct}% above baseline` : 'Not checked out yet — baseline is $0';

                resultDiv.innerHTML = `
                    <div style="margin-bottom: 16px;">
                        <span class="badge badge-info">#${r.order_number}</span>
                        <strong style="margin-left:8px;">${r.id}</strong>
                        <span class="subtext" style="margin-left:10px;">${r.contents.toUpperCase()} · Zone ${r.zone} · ${r.risk_level.toUpperCase()} risk · Value $${r.container_value.toLocaleString('en',{maximumFractionDigits:0})}</span>
                    </div>
                    <div class="revenue-breakdown-grid">
                        <div class="revenue-line"><div class="rl-label">Processing Fee</div><div class="rl-value">$${b.processing.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                        <div class="revenue-line"><div class="rl-label">Theft Prevention (AI)</div><div class="rl-value">$${b.theft_prevention.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                        <div class="revenue-line"><div class="rl-label">Loss Prevention (AI)</div><div class="rl-value">$${b.loss_prevention.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                        <div class="revenue-line"><div class="rl-label">Insurance Savings (AI)</div><div class="rl-value">$${b.insurance_savings.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                        <div class="revenue-line"><div class="rl-label">High-Risk Premium (AI)</div><div class="rl-value">$${b.high_risk_premium.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                        <div class="revenue-line" style="border-left-color: var(--success);"><div class="rl-label">Total Revenue From This Container</div><div class="rl-value" style="color: var(--success-2);">$${r.total_usd.toLocaleString('en',{maximumFractionDigits:0})}</div></div>
                    </div>
                    <p class="subtext" style="margin-top: 14px;">
                        🤖 The AI agent contributed <strong>$${r.ai_generated_usd.toLocaleString('en',{maximumFractionDigits:0})}</strong>
                        of this container's revenue (${upliftText}). In TND that's د.ت ${r.ai_generated_tnd.toLocaleString('en',{maximumFractionDigits:0})}.
                    </p>
                `;
            } catch (e) {
                resultDiv.innerHTML = `<p class="subtext">❌ Error: ${e.message}</p>`;
            }
        }

        document.getElementById('containerRevenueSelect').addEventListener('change', (e) => {
            loadContainerRevenue(e.target.value);
        });
        document.getElementById('refreshContainerRevenueBtn').addEventListener('click', () => {
            const select = document.getElementById('containerRevenueSelect');
            if (select.value) loadContainerRevenue(select.value);
        });

        // ========== ANALYTICS / CHARTS ==========
        function updateCharts() {
            if (!lastData.contents_dist) return;

            const cLabels = Object.keys(lastData.contents_dist);
            const cVals = Object.values(lastData.contents_dist);
            Plotly.react('chartContents', [{
                labels: cLabels, values: cVals, type: 'pie', hole: 0.45,
                marker: { colors: PLOTLY_PALETTE }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, showlegend: true }, { responsive: true, displayModeBar: false });

            const riskVals = [lastData.risk_dist.high || 0, lastData.risk_dist.medium || 0, lastData.risk_dist.low || 0, lastData.risk_dist.critical || 0];
            Plotly.react('chartRisk', [{
                labels: ['High', 'Medium', 'Low', 'Critical'], values: riskVals, type: 'pie', hole: 0.45,
                marker: { colors: [PALETTE.danger, PALETTE.warning, PALETTE.success, PALETTE.critical] }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, showlegend: true }, { responsive: true, displayModeBar: false });

            Plotly.react('chartStatus', [{
                x: ['In Warehouse', 'Processed'], y: [lastData.checked_in, lastData.checked_out], type: 'bar',
                marker: { color: [PALETTE.success, PALETTE.warning] }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, yaxis: { title: 'Count', gridcolor: PALETTE.gridLine } }, { responsive: true, displayModeBar: false });

            if (lastData.financial) {
                const r = lastData.financial.revenue;
                Plotly.react('chartRevenue', [{
                    labels: ['Processing', 'Theft Prevention', 'Loss Prevention', 'Insurance', 'High-Risk Premium'],
                    values: [r.processing_usd, r.theft_prevention_usd, r.loss_prevention_usd, r.insurance_usd, r.high_risk_usd],
                    type: 'pie', hole: 0.45,
                    marker: { colors: PLOTLY_PALETTE }
                }], { ...PLOTLY_LAYOUT_BASE, height: 320, showlegend: true }, { responsive: true, displayModeBar: false });
            }

            // Containers per zone — bar
            const zoneLabels = Object.keys(lastData.zone_dist || {}).sort();
            const zoneVals = zoneLabels.map(z => lastData.zone_dist[z]);
            Plotly.react('chartZones', [{
                x: zoneLabels, y: zoneVals, type: 'bar', marker: { color: PALETTE.accent }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, xaxis: { title: 'Zone' }, yaxis: { title: 'Containers', gridcolor: PALETTE.gridLine } }, { responsive: true, displayModeBar: false });

            // Risk x Zone heatmap
            const containers = Object.values(lastData.containers || {});
            const risks = ['low', 'medium', 'high', 'critical'];
            const zones = ['A', 'B', 'C', 'D', 'E', 'F'];
            const heatZ = risks.map(r => zones.map(z => containers.filter(c => c.risk_level === r && c.location.zone === z).length));
            Plotly.react('chartHeatmap', [{
                z: heatZ, x: zones, y: risks.map(r => r.toUpperCase()), type: 'heatmap',
                colorscale: [[0, '#fbf4e6'], [0.5, '#cf9a3e'], [1, '#ad3f2e']],
                showscale: true
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, xaxis: { title: 'Zone' }, yaxis: { title: 'Risk' } }, { responsive: true, displayModeBar: false });

            // Value vs weight scatter, colored by risk
            const riskColorMap = { low: PALETTE.success, medium: PALETTE.warning, high: PALETTE.danger, critical: PALETTE.critical };
            Plotly.react('chartScatter', [{
                x: containers.map(c => c.weight),
                y: containers.map(c => c.container_value),
                text: containers.map(c => `#${c.order_number} ${c.id}`),
                mode: 'markers',
                type: 'scatter',
                marker: { size: 10, color: containers.map(c => riskColorMap[c.risk_level] || PALETTE.accent), opacity: 0.85 }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320, xaxis: { title: 'Weight (kg)', gridcolor: PALETTE.gridLine }, yaxis: { title: 'Value ($)', gridcolor: PALETTE.gridLine } }, { responsive: true, displayModeBar: false });

            // Avg utilization gauge
            const avgUtil = lastData.avg_utilization || 0;
            Plotly.react('chartGauge', [{
                type: 'indicator',
                mode: 'gauge+number',
                value: avgUtil,
                number: { suffix: '%' },
                gauge: {
                    axis: { range: [0, 100] },
                    bar: { color: PALETTE.accent },
                    steps: [
                        { range: [0, 50], color: '#f3e6cf' },
                        { range: [50, 80], color: '#e9d3ab' },
                        { range: [80, 100], color: '#d9b681' }
                    ],
                    threshold: { line: { color: PALETTE.success2, width: 4 }, thickness: 0.8, value: 80 }
                }
            }], { ...PLOTLY_LAYOUT_BASE, height: 320 }, { responsive: true, displayModeBar: false });

            // Revenue funnel: baseline -> +theft -> +loss -> +insurance -> +risk premium -> total
            if (lastData.financial) {
                const rv = lastData.financial.revenue;
                const stageLabels = ['Baseline (Processing only)', '+ Theft Prevention', '+ Loss Prevention', '+ Insurance Savings', '+ High-Risk Premium (Total)'];
                const stageVals = [
                    rv.processing_usd,
                    rv.processing_usd + rv.theft_prevention_usd,
                    rv.processing_usd + rv.theft_prevention_usd + rv.loss_prevention_usd,
                    rv.processing_usd + rv.theft_prevention_usd + rv.loss_prevention_usd + rv.insurance_usd,
                    rv.total_usd
                ];
                Plotly.react('chartFunnel', [{
                    type: 'funnel',
                    y: stageLabels,
                    x: stageVals,
                    marker: { color: PLOTLY_PALETTE }
                }], { ...PLOTLY_LAYOUT_BASE, height: 340 }, { responsive: true, displayModeBar: false });
            }
        }

        // ========== jsQR LIBRARY LOADER (with fallback CDNs) ==========
        const JSQR_CDN_URLS = [
            'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js',
            'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js',
            'https://unpkg.com/jsqr@1.4.0/dist/jsQR.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/jsQR/1.4.0/jsQR.js'
        ];
        let jsQRReady = false;

        function loadJsQR(index) {
            index = index || 0;
            if (typeof window.jsQR === 'function') {
                jsQRReady = true;
                return;
            }
            if (index >= JSQR_CDN_URLS.length) {
                const resultEl = document.getElementById('qrResult');
                if (resultEl) {
                    resultEl.innerHTML =
                        '<div style="color:var(--danger);">❌ Could not load the QR scanning library from any source. Check your internet connection, then reload the page.</div>';
                }
                return;
            }
            const script = document.createElement('script');
            script.src = JSQR_CDN_URLS[index];
            script.onload = function() {
                jsQRReady = (typeof window.jsQR === 'function');
                if (!jsQRReady) loadJsQR(index + 1);
            };
            script.onerror = function() {
                loadJsQR(index + 1);
            };
            document.head.appendChild(script);
        }

        function ensureJsQRReady() {
            if (typeof window.jsQR === 'function') {
                jsQRReady = true;
                return true;
            }
            jsQRReady = false;
            loadJsQR(0);
            return false;
        }

        loadJsQR(0);

        // ========== QR CAMERA SCANNER ==========
        let qrStream = null;
        let qrScanning = false;
        let lastQrValue = null;
        let lastQrTime = 0;

        async function startCamera() {
            if (!ensureJsQRReady()) {
                document.getElementById('qrResult').innerHTML =
                    '⏳ QR scanning library is still loading — click "Start Camera" again in a second.';
                return;
            }
            try {
                qrStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
                const video = document.getElementById('qrVideo');
                video.srcObject = qrStream;
                await video.play();
                qrScanning = true;
                document.getElementById('startCamBtn').style.display = 'none';
                document.getElementById('stopCamBtn').style.display = 'inline-block';
                document.getElementById('qrResult').innerHTML = '📡 Scanning for QR codes...';
                requestAnimationFrame(scanQRFrame);
            } catch (e) {
                document.getElementById('qrResult').innerHTML = `<span style="color:var(--danger);">❌ Camera access failed: ${e.message}</span>`;
            }
        }

        function stopCamera() {
            qrScanning = false;
            if (qrStream) {
                qrStream.getTracks().forEach(t => t.stop());
                qrStream = null;
            }
            document.getElementById('startCamBtn').style.display = 'inline-block';
            document.getElementById('stopCamBtn').style.display = 'none';
        }

        function scanQRFrame() {
            if (!qrScanning) return;
            const video = document.getElementById('qrVideo');
            const canvas = document.getElementById('qrCanvas');

            if (video.readyState === video.HAVE_ENOUGH_DATA && typeof window.jsQR === 'function') {
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const code = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'dontInvert' });

                if (code && code.data) {
                    const now = Date.now();
                    if (code.data !== lastQrValue || now - lastQrTime > 3000) {
                        lastQrValue = code.data;
                        lastQrTime = now;
                        handleQrDetected(code.data);
                    }
                }
            }
            requestAnimationFrame(scanQRFrame);
        }

        async function handleQrDetected(qrData) {
            document.getElementById('qrResult').innerHTML = `<div style="color:var(--accent-2);">🔍 Detected code: ${qrData}</div>`;
            try {
                const res = await fetch('/api/scan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ qr_data: qrData })
                });
                const data = await res.json();

                if (data.status === 'created') {
                    document.getElementById('qrResult').innerHTML =
                        `<div style="color:var(--success-2);">✅ New container registered: #${data.container.order_number} (${data.container.id})</div>`;
                    notificationManager.success('Container Added', `Container ${data.container.id} added via QR scan`);
                } else if (data.status === 'scanned') {
                    document.getElementById('qrResult').innerHTML =
                        `<div style="color:var(--accent-2);">📦 Container scanned: #${data.container.order_number} (${data.container.id}) — scan count: ${data.container.scan_count}</div>`;
                    notificationManager.show('Container Scanned', `Container ${data.container.id} scanned`, 'info');
                } else {
                    document.getElementById('qrResult').innerHTML = `<div style="color:var(--danger);">❌ ${data.message}</div>`;
                }
                addScanLogEntry(data);
            } catch (e) {
                document.getElementById('qrResult').innerHTML = `<div style="color:var(--danger);">❌ Error: ${e.message}</div>`;
            }
        }

        function addScanLogEntry(data) {
            const log = document.getElementById('qrScanLog');
            const entry = document.createElement('div');
            entry.className = 'qr-scan-log-entry';
            const time = new Date().toLocaleTimeString();
            if (data.container) {
                entry.innerHTML = `<strong>${time}</strong> — ${data.status.toUpperCase()}: ${data.container.id}`;
            } else {
                entry.innerHTML = `<strong>${time}</strong> — ERROR: ${data.message}`;
            }
            log.prepend(entry);
        }

        document.getElementById('startCamBtn').addEventListener('click', startCamera);
        document.getElementById('stopCamBtn').addEventListener('click', stopCamera);

        // ========== RANDOM CONTAINER GENERATOR ==========
        let generationInterval = null;

        async function generateRandomContainer() {
            try {
                const res = await fetch('/api/generate', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'created') {
                    document.getElementById('qrResult').innerHTML =
                        `<div style="color:var(--success-2);">🎲 Random container generated: #${data.container.order_number} (${data.container.id})</div>`;
                    notificationManager.success('Container Generated', `Container ${data.container.id} added`);
                    addScanLogEntry(data);
                } else {
                    document.getElementById('qrResult').innerHTML = `<div style="color:var(--danger);">❌ ${data.message}</div>`;
                }
            } catch (e) {
                document.getElementById('qrResult').innerHTML = `<div style="color:var(--danger);">❌ Error: ${e.message}</div>`;
            }
        }

        function startGeneration() {
            if (generationInterval) return;
            generateRandomContainer();
            generationInterval = setInterval(generateRandomContainer, 2000);
            document.getElementById('startGenBtn').style.display = 'none';
            document.getElementById('stopGenBtn').style.display = 'inline-block';
        }

        function stopGeneration() {
            if (generationInterval) {
                clearInterval(generationInterval);
                generationInterval = null;
            }
            document.getElementById('startGenBtn').style.display = 'inline-block';
            document.getElementById('stopGenBtn').style.display = 'none';
        }

        document.getElementById('startGenBtn').addEventListener('click', startGeneration);
        document.getElementById('stopGenBtn').addEventListener('click', stopGeneration);

        // ========== QR IMAGE UPLOAD ==========
        document.getElementById('uploadBtn').addEventListener('click', () => {
            document.getElementById('qrImageInput').click();
        });

        const QR_DECODE_SIZES = [700, 1400, 2200];

        function decodeImageProgressively(img, attemptIndex) {
            attemptIndex = attemptIndex || 0;

            if (!ensureJsQRReady()) {
                document.getElementById('qrResult').innerHTML =
                    '⏳ QR scanning library is still loading — please try uploading the image again in a second.';
                return;
            }

            if (attemptIndex >= QR_DECODE_SIZES.length) {
                document.getElementById('qrResult').innerHTML =
                    '<div style="color:var(--danger);">❌ No QR code detected in that image. Try a clearer, closer, uncropped photo of the code.</div>';
                return;
            }

            const maxDim = QR_DECODE_SIZES[attemptIndex];
            let width = img.width;
            let height = img.height;
            if (Math.max(width, height) > maxDim) {
                const scale = maxDim / Math.max(width, height);
                width = Math.max(1, Math.round(width * scale));
                height = Math.max(1, Math.round(height * scale));
            }

            const canvas = document.getElementById('qrCanvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);

            document.getElementById('qrResult').innerHTML = `🔎 Decoding (pass ${attemptIndex + 1}/${QR_DECODE_SIZES.length})...`;

            setTimeout(() => {
                try {
                    const imageData = ctx.getImageData(0, 0, width, height);
                    const code = jsQR(imageData.data, imageData.width, imageData.height, {
                        inversionAttempts: 'attemptBoth'
                    });

                    if (code && code.data) {
                        handleQrDetected(code.data);
                    } else {
                        decodeImageProgressively(img, attemptIndex + 1);
                    }
                } catch (err) {
                    document.getElementById('qrResult').innerHTML =
                        `<div style="color:var(--danger);">❌ Error decoding image: ${err.message}</div>`;
                }
            }, 20);
        }

        document.getElementById('qrImageInput').addEventListener('change', function(e) {
            const file = e.target.files[0];
            e.target.value = '';
            if (!file) return;

            document.getElementById('qrResult').innerHTML = '⏳ Reading image...';

            const reader = new FileReader();
            reader.onload = function(evt) {
                const img = new Image();
                img.onload = function() {
                    decodeImageProgressively(img, 0);
                };
                img.onerror = function() {
                    document.getElementById('qrResult').innerHTML =
                        '<div style="color:var(--danger);">❌ Could not load that image file.</div>';
                };
                img.src = evt.target.result;
            };
            reader.onerror = function() {
                document.getElementById('qrResult').innerHTML =
                    '<div style="color:var(--danger);">❌ Could not read that file.</div>';
            };
            reader.readAsDataURL(file);
        });

        // ========== WAREHOUSE OPERATIONS AGENT ==========
        const DEFAULT_SUGGESTIONS = ['📋 Give me a briefing', '⏰ What exits in the next 3 days?', '⚠️ Which containers are overdue?', '💰 Profit and ROI today', '🔥 Most valuable containers at risk'];
        let agentBusy = false;
        let currentInsights = [];

        function esc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
        }
        function fmt(text) {
            return esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        }

        function addMessage(text, isUser, steps, pending) {
            const messages = document.getElementById('chatMessages');
            const msg = document.createElement('div');
            msg.className = `message ${isUser ? 'user' : 'bot'}`;
            msg.innerHTML = fmt(text);
            if (!isUser && steps && steps.length) {
                const st = document.createElement('div');
                st.className = 'agent-steps';
                st.textContent = '🔧 ' + steps.map(s => s.tool).join(' → ');
                msg.appendChild(st);
            }
            if (!isUser && pending && pending.length) {
                pending.forEach(a => addActionCard(msg, a));
            }
            messages.appendChild(msg);
            messages.scrollTop = messages.scrollHeight;
            chatHistory.push({text, isUser});
            return msg;
        }

        function addActionCard(parent, a) {
            const card = document.createElement('div');
            card.className = 'action-card';
            card.id = 'act-' + a.id;
            card.innerHTML =
                `<div class="action-title">⚡ Proposed action — needs your approval</div>` +
                `<div>${esc(a.summary)}</div>` +
                (a.reason ? `<div class="subtext" style="margin-top:4px;">Why: ${esc(a.reason)}</div>` : '') +
                `<div class="action-btns">` +
                `<button class="act-approve" onclick="decideAction('${a.id}','approve')">✅ Approve</button>` +
                `<button class="act-reject" onclick="decideAction('${a.id}','reject')">✖ Reject</button></div>`;
            parent.appendChild(card);
        }

        function decideAction(id, decision) {
            const card = document.getElementById('act-' + id);
            if (!card) return;
            card.querySelectorAll('button').forEach(b => b.disabled = true);
            fetch(`/api/agent/actions/${id}/${decision}`, {method: 'POST'})
                .then(r => r.json())
                .then(d => {
                    const ok = decision === 'approve' && d.status !== 'failed' && d.status !== 'error';
                    card.querySelector('.action-btns').innerHTML =
                        `<div class="action-result">${ok ? '✅' : (decision === 'reject' ? '✖' : '⚠️')} ${esc(d.message)}</div>`;
                    if (decision === 'approve') { updateData(); loadInsights(); }
                })
                .catch(() => {
                    card.querySelector('.action-btns').innerHTML = '<div class="action-result">⚠️ Request failed.</div>';
                });
        }

        function updateSuggestions(suggestions) {
            const div = document.getElementById('chatSuggestions');
            const list = (suggestions && suggestions.length) ? suggestions : DEFAULT_SUGGESTIONS;
            div.innerHTML = '';
            list.forEach(s => {
                const b = document.createElement('button');
                b.className = 'suggestion-btn';
                b.textContent = s;
                b.addEventListener('click', () => chatbot_sendSuggestion(s));
                div.appendChild(b);
            });
        }

        function chatbot_sendSuggestion(text) {
            if (text.startsWith('📋')) { requestBriefing(); return; }
            text = text.replace(/^[▶✔]\s*/, '');
            document.getElementById('chatInput').value = text;
            sendMessage();
        }

        function setBusy(on) {
            agentBusy = on;
            document.querySelectorAll('.chatbot-send, #briefingBtn').forEach(b => b.disabled = on);
        }

        function handleAgentResponse(data, thinkingEl) {
            if (thinkingEl) thinkingEl.remove();
            addMessage(data.response, false, data.steps, data.pending);
            updateSuggestions(data.suggestions);
            setBusy(false);
            loadStatus();
        }

        function sendMessage() {
            if (agentBusy) return;
            const input = document.getElementById('chatInput').value.trim();
            if (!input) return;
            addMessage(input, true);
            document.getElementById('chatInput').value = '';
            setBusy(true);
            const thinking = addMessage('⏳ Working on it — checking the live data…', false);
            fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({query: input})
            })
            .then(r => r.json())
            .then(data => handleAgentResponse(data, thinking))
            .catch(() => handleAgentResponse({response: '⚠️ Could not reach the server.'}, thinking));
        }

        function requestBriefing() {
            if (agentBusy) return;
            addMessage('📋 Operations briefing, please.', true);
            setBusy(true);
            const thinking = addMessage('⏳ Reviewing alerts, exits, insights and finances…', false);
            fetch('/api/agent/briefing', {method: 'POST'})
                .then(r => r.json())
                .then(data => handleAgentResponse(data, thinking))
                .catch(() => handleAgentResponse({response: '⚠️ Could not reach the server.'}, thinking));
        }

        function askInsight(i) {
            const it = currentInsights[i];
            if (!it) return;
            document.getElementById('chatInput').value =
                `Look into this monitor finding and tell me what to do: ${it.title}` +
                (it.containers.length ? ` (${it.containers.join(', ')})` : '');
            sendMessage();
        }

        function loadStatus() {
            fetch('/api/agent/status').then(r => r.json()).then(d => {
                const el = document.getElementById('agentMode');
                if (!el) return;
                el.textContent = d.mode === 'llm' ? `🧠 AI model: ${d.provider} / ${d.model}` : '📴 Offline mode (rule-based)';
            }).catch(() => {});
        }

        function loadInsights() {
            fetch('/api/agent/insights').then(r => r.json()).then(d => {
                currentInsights = d.insights || [];
                const el = document.getElementById('agentInsights');
                if (!el) return;
                if (!currentInsights.length) {
                    el.innerHTML = '<div class="insight ok">✅ Monitor: nothing needs attention right now</div>';
                    return;
                }
                el.innerHTML = currentInsights.map((it, i) =>
                    `<div class="insight ${esc(it.severity)}" onclick="askInsight(${i})" title="Click to ask the agent about this">` +
                    `<strong>${it.severity === 'critical' ? '🚨' : (it.severity === 'warning' ? '⚠️' : 'ℹ️')} ${esc(it.title)}</strong>` +
                    (it.containers.length ? `<span class="insight-ids">${it.containers.map(esc).join(', ')}${it.more ? ' +' + it.more + ' more' : ''}</span>` : '') +
                    `</div>`).join('');
            }).catch(() => {});
        }

        document.getElementById('chatInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        // Initialize
        addMessage("👋 I'm your Warehouse Operations Agent. I read the live database with tools, chain several lookups when needed, watch the warehouse in the background, and can propose actions (check-out, reschedule, resolve alerts) that only run after you approve. Try a briefing!", false);
        updateSuggestions(DEFAULT_SUGGESTIONS);
        loadInsights();
        loadStatus();
        setInterval(loadInsights, 15000);

        updateData();
        setInterval(() => { if (!document.hidden) updateData(); }, 5000);
    </script>
</body>
</html>

"""

# ===================== ROUTES =====================

@app.route('/')
def index():
    return render_template_string(BASE_HTML)

@app.route('/api/data')
def get_data():
    stats = warehouse.get_stats()
    for cd in list(stats["containers"].values()) + list(stats["upcoming_exits"]):
        cd.pop("qr_code", None)     # base64 PNGs made each poll ~290 KB for 66 containers
    return jsonify(stats)

_RATE = {}
AGENT_RATE_PER_MIN = int(os.environ.get('AGENT_RATE_PER_MIN', '20'))

def _rate_ok(sid):
    """Per-browser limit so a public link can't burn through a free LLM quota."""
    now = _t0.time()
    q = _RATE.setdefault(sid, _deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= AGENT_RATE_PER_MIN:
        return False
    q.append(now)
    return True

_TOO_FAST = {"response": "⏳ You're sending requests very quickly — wait a few seconds and try again.", "steps": [], "pending": []}

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"response": "Ask me about a container, a zone, alerts, exits or money.", "steps": [], "pending": []})
    sid = _sid()
    if not _rate_ok(sid):
        return jsonify(_TOO_FAST), 429
    answer, steps, pending = run_agent(query, sid)
    if not answer.startswith("⚠️"):
        h = _history(sid)
        h.append({"role": "user", "content": query})
        h.append({"role": "assistant", "content": answer})
    return jsonify({"response": answer, "steps": steps, "pending": pending, "suggestions": SUGGESTIONS.pop(sid, [])})

BRIEFING_PROMPT = ("Give me an operations briefing for right now. Use get_insights, get_warehouse_summary, get_alerts and "
                   "get_exit_schedule (next 2 days) to find what needs attention. Lead with the top 3 priorities, each with the "
                   "container ids involved and a recommended next step. Propose write actions only for clear, high-value cases.")

@app.route('/api/agent/briefing', methods=['POST'])
def agent_briefing():
    sid = _sid()
    if not _rate_ok(sid):
        return jsonify(_TOO_FAST), 429
    answer, steps, pending = run_agent(BRIEFING_PROMPT, sid)
    if not answer.startswith("⚠️"):
        h = _history(sid)
        h.append({"role": "user", "content": "Operations briefing, please."})
        h.append({"role": "assistant", "content": answer})
    return jsonify({"response": answer, "steps": steps, "pending": pending, "suggestions": SUGGESTIONS.pop(sid, [])})

@app.route('/api/agent/actions/<aid>/<decision>', methods=['POST'])
def agent_decide(aid, decision):
    if decision not in ('approve', 'reject'):
        abort(404)
    sid = _sid()
    act, msg = decide_action(aid, sid, decision == 'approve')
    if act is None:
        return jsonify({"status": "error", "message": msg}), 404
    _history(sid).append({"role": "user", "content":
        f"(System note: the user {decision}d the proposed action \"{act['summary']}\". Result: {msg})"})
    return jsonify({"status": act['status'], "message": msg})

@app.route('/api/agent/selftest')
def agent_selftest():
    """Open this URL in a browser to see exactly why the AI is (not) working. Never shows the key."""
    import time as _tm
    info = {"provider": LLM_PROVIDER, "enabled": LLM_ENABLED, "api_key_set": bool(LLM_API_KEY),
            "pinned_model": LLM_MODEL_PINNED, "url": LLM_URL}
    if not LLM_ENABLED:
        info["problem"] = LLM_PROBLEM or "No provider configured (offline mode)."
        return jsonify(info)
    t = _tm.time()
    with _LLM_LOCK:
        if _MODELS["candidates"] is None:
            found = _discover_models()
            _MODELS["candidates"] = found or None
        info["models_found"] = (_MODELS["candidates"] or [])[:12]
    info["discovery_seconds"] = round(_tm.time() - t, 1)
    info["auth_error"] = bool(_MODELS.get("auth_error"))
    info["cooling_down_seconds"] = {m: int(t - _tm.time()) for m, t in _COOL.items() if t > _tm.time()}
    t = _tm.time()
    msg, err = _llm_chat([{"role": "user", "content": "Reply with the single word OK."}])
    info.update(chat_seconds=round(_tm.time() - t, 1), model_used=current_model(),
                reply=((msg or {}).get("content") or "")[:80], error=err, ok=bool(msg and not err))
    return jsonify(info)

@app.route('/api/agent/status')
def agent_status():
    return jsonify(llm_status())

@app.route('/api/agent/insights')
def agent_insights():
    run_monitor_if_stale()
    return jsonify(MONITOR_STATE)

@app.route('/api/agent/log')
def agent_log_view():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute('SELECT * FROM agent_log ORDER BY id DESC LIMIT 50').fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/scan', methods=['POST'])
def scan_qr():
    """Handle a QR code decoded by the browser, whether from the live camera or an
    uploaded image file. Expected payload: {"qr_data": "<decoded QR text>"}
    The QR text is normally a full-info JSON payload (see build_qr_payload), but the
    legacy "WAREHOUSE_AI|<id>|<timestamp>" format is also accepted.
    - If the container_id doesn't exist yet, it's created using every field the QR
      code carried (missing fields, if any, are filled in automatically).
    - If it already exists, it's treated as a scan (scan_count incremented)."""
    payload = request.json or {}
    qr_data = payload.get('qr_data', '')
    parsed = parse_qr_payload(qr_data)

    if not parsed:
        return jsonify({"status": "error", "message": "Unrecognized QR code format"}), 400

    container_id = parsed.get('id')

    if container_id in warehouse.containers:
        result = warehouse.scan_container(container_id)
        return jsonify({"status": "scanned", "container": result})

    container = warehouse.add_container_from_qr(parsed)
    if container is None:
        return jsonify({"status": "error", "message": "Could not register container"}), 400
    return jsonify({"status": "created", "container": container.to_dict()})

@app.route('/api/generate', methods=['POST'])
def generate_random():
    container = warehouse.generate_random_container()
    if container is None:
        return jsonify({"status": "error", "message": "Could not generate container"}), 400
    return jsonify({"status": "created", "container": container.to_dict()})

@app.route('/api/alert/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE alerts SET is_resolved = 1 WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "acknowledged"})

@app.route('/api/checkout/<container_id>', methods=['POST'])
def checkout(container_id):
    """Manually mark a container as checked out / exited the warehouse."""
    ok = warehouse.checkout_container(container_id)
    if not ok:
        return jsonify({"status": "error", "message": "Container not found"}), 404
    return jsonify({"status": "checked_out", "container": warehouse.containers[container_id].to_dict()})

@app.route('/api/container_revenue/<container_id>')
def container_revenue(container_id):
    """Revenue/value breakdown for a single container, used by the Financial page's
    container picker to show exactly how much this container has generated."""
    result = warehouse.get_container_revenue(container_id)
    if result is None:
        return jsonify({"status": "error", "message": "Container not found"}), 404
    return jsonify({"status": "ok", "revenue": result})

@app.route('/api/clear', methods=['POST'])
def clear():
    if PUBLIC_MODE:
        return jsonify({"status": "disabled", "message": "Clearing is disabled in PUBLIC_MODE"}), 403
    global warehouse
    warehouse.containers = {}
    warehouse.total_processed = 0
    warehouse.start_time = datetime.now()
    warehouse.alert_system.acknowledged_alerts.clear()
    Container.counter = 0
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_database()
    AGENT_SESSIONS.clear()
    OFFLINE_CTX.clear()
    PENDING_ACTIONS.clear()
    _init_agent_tables()
    MONITOR_STATE.update({'last_run': None, 'insights': []})
    return jsonify({"status": "cleared"})

# ===================== MAIN =====================

if __name__ == '__main__':
    print("\n" + "="*150)
    print("  🏭 WAREHOUSE AI LOGISTICS v6.0 AGENT - COMPLETE ENTERPRISE SYSTEM")
    print("="*150)
    print("\n  🔐 ACCESS LINK (share only this with your team):")
    print(f"     http://localhost:5000/access/{ACCESS_TOKEN}")
    print("     Anyone without that exact link gets a 404.")
    if not os.environ.get('WAREHOUSE_ACCESS_TOKEN'):
        print("     NOTE: no WAREHOUSE_ACCESS_TOKEN env var was set, so this token is")
        print("     random and will change next time you start the site.")
    print("\n  ✨ ALL FEATURES INCLUDED:")
    print("     ✅ QR Code Generation & LIVE Camera Scanning (add/check-in containers)")
    print("     ✅ Real Warehouse SVG Map (150m x 100m with 6 Zones)")
    print("     ✅ Container Details on Hover")
    print("     ✅ Complete Database Page")
    print("     ✅ Utilization Analytics with Progress Bars")
    print("     ✅ Exit Schedule Management")
    print("     ✅ Active Alert System with Toast Notifications")
    print("     ✅ Professional Financial Dashboard")
    print("     ✅ 8 Comprehensive KPIs")
    print("     ✅ USD/TND Currency Support")
    print("     ✅ Operations AGENT: tool-calling loop, approval-gated actions, background monitor")
    print("     ✅ Real-Time Database Integration")
    print("     ✅ Analytics & Charts")
    print("\n  🤖 AI ASSISTANT SECTION:")
    print("     • Lives in its own page (nav bar), like every other section")
    print("     • Ask it anything in natural language — it retrieves the relevant")
    print("       containers/zones/alerts/financials, then asks Groq to answer from them")
    if LLM_PROBLEM:
        print(f"     ⚠️  {LLM_PROBLEM}")
    elif not LLM_ENABLED:
        print("     ℹ️  No AI provider set: using the built-in offline agent. See .env options in the file header.")
    print("\n  📷 QR CAMERA SCANNING:")
    print("     • Open the 'Scan QR' section and click Start Camera")
    print("     • Point at a container QR code (format: WAREHOUSE_AI|<id>|<timestamp>)")
    print("     • Unknown IDs are auto-registered as new containers")
    print("     • Known IDs get their scan count updated")
    print("\n  📊 9 PAGES:")
    print("     1. Dashboard - Quick Stats")
    print("     2. Warehouse - Interactive Map with Zones")
    print("     3. Database - 50 Recent Containers")
    print("     4. Utilization - Space Usage Analytics")
    print("     5. Exit Schedule - Upcoming Exits")
    print("     6. Alerts - Active Notifications")
    print("     7. Financial - Revenue & KPIs")
    print("     8. Analytics - Charts & Diagrams")
    print("     9. Scan QR - Live camera QR scanning")
    print("    10. AI Assistant - Dedicated chatbot section")
    print("\n  🌐 URL: http://localhost:5000")
    print("="*150 + "\n")

    print("⚠️  REQUIRED: pip install flask flask-cors qrcode pillow requests scikit-learn python-dotenv\n")

    start_monitor()
    print(f"  🤖 Agent: {'LLM ' + LLM_PROVIDER + ' / ' + (LLM_MODEL_PINNED or 'auto-discovered model') if LLM_ENABLED else 'OFFLINE mode (no AI provider configured)'} | autonomy={AGENT_AUTONOMY} | monitor every {AGENT_MONITOR_SECONDS}s | "
          f"{LOADED_ON_START} container(s) loaded from DB\n")
    app.run(debug=False, port=int(os.environ.get('PORT', 5000)), host=os.environ.get('HOST', '127.0.0.1'))
