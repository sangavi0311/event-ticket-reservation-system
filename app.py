from flask import Flask, request, jsonify, render_template
import sqlite3, time, uuid
from datetime import datetime, timezone

app = Flask(__name__)
DB = "events.db"
HOLD_SECONDS = 10 * 60

def connect():
    con = sqlite3.connect(DB, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Admin','Organizer','Attendee'))
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organizer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        sales_cutoff TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(organizer_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS ticket_tiers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL CHECK(price >= 0),
        quantity INTEGER NOT NULL CHECK(quantity >= 0),
        sold INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(event_id) REFERENCES events(id)
    );
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        attendee_id INTEGER NOT NULL,
        tier_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        status TEXT NOT NULL CHECK(status IN ('HELD','PAID','EXPIRED','REJECTED')),
        hold_expires INTEGER NOT NULL,
        total REAL NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(attendee_id) REFERENCES users(id),
        FOREIGN KEY(tier_id) REFERENCES ticket_tiers(id)
    );
    CREATE TABLE IF NOT EXISTS payment_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        status TEXT NOT NULL,
        amount REAL NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id)
    );
    """)
    # Demo users and event, added only when database is empty.
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        con.execute("INSERT INTO users(name,email,role) VALUES(?,?,?)",
                    ("Demo Organizer","organizer@example.com","Organizer"))
        con.execute("INSERT INTO users(name,email,role) VALUES(?,?,?)",
                    ("Demo Attendee","attendee@example.com","Attendee"))
        con.execute("INSERT INTO users(name,email,role) VALUES(?,?,?)",
                    ("Demo Admin","admin@example.com","Admin"))
        con.execute("INSERT INTO events(organizer_id,title,description,sales_cutoff) VALUES(1,?,?,?)",
                    ("Campus Tech Fest","A demo event for testing ticket reservations",
                     "2099-12-31T23:59:00"))
        con.execute("INSERT INTO ticket_tiers(event_id,name,price,quantity) VALUES(1,?,?,?)",
                    ("General Admission",199,100))
        con.execute("INSERT INTO ticket_tiers(event_id,name,price,quantity) VALUES(1,?,?,?)",
                    ("VIP",499,20))
    con.close()

def expire_holds(con):
    now = int(time.time())
    # Release held quantities by marking orders expired; sold counts are incremented only after payment.
    con.execute("UPDATE orders SET status='EXPIRED' WHERE status='HELD' AND hold_expires <= ?", (now,))

def user_by_id(con, user_id):
    return con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

@app.route("/")
def home():
    return render_template("index.html")

@app.get("/api/users")
def list_users():
    con = connect()
    rows = con.execute("SELECT id,name,email,role FROM users ORDER BY id").fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/events")
def list_events():
    con = connect()
    expire_holds(con)
    rows = con.execute("""
        SELECT e.id,e.title,e.description,e.sales_cutoff,
               t.id AS tier_id,t.name AS tier_name,t.price,t.quantity,t.sold,
               (t.quantity-t.sold-COALESCE((
                 SELECT SUM(o.quantity) FROM orders o
                 WHERE o.tier_id=t.id AND o.status='HELD' AND o.hold_expires>?
               ),0)) AS available
        FROM events e JOIN ticket_tiers t ON t.event_id=e.id
        WHERE e.active=1 ORDER BY e.id,t.id
    """, (int(time.time()),)).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/events")
def create_event():
    data = request.get_json(silent=True) or {}
    try:
        organizer_id = int(data["organizer_id"])
        title = data["title"].strip()
        tier_name = data["tier_name"].strip()
        price = float(data["price"])
        quantity = int(data["quantity"])
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Required: organizer_id, title, tier_name, price, quantity"), 400
    if not title or not tier_name or price < 0 or quantity < 1:
        return jsonify(error="Enter a title, tier name, non-negative price, and quantity > 0"), 400
    con = connect()
    user = user_by_id(con, organizer_id)
    if not user or user["role"] not in ("Organizer", "Admin"):
        con.close()
        return jsonify(error="Only an Organizer or Admin can create events"), 403
    con.execute("BEGIN IMMEDIATE")
    cur = con.execute("INSERT INTO events(organizer_id,title,description,sales_cutoff) VALUES(?,?,?,?)",
                      (organizer_id,title,data.get("description",""),data.get("sales_cutoff")))
    event_id = cur.lastrowid
    con.execute("INSERT INTO ticket_tiers(event_id,name,price,quantity) VALUES(?,?,?,?)",
                (event_id,tier_name,price,quantity))
    con.commit()
    con.close()
    return jsonify(message="Event created", event_id=event_id), 201

@app.post("/api/holds")
def create_hold():
    data = request.get_json(silent=True) or {}
    try:
        attendee_id = int(data["attendee_id"])
        tier_id = int(data["tier_id"])
        quantity = int(data["quantity"])
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Required: attendee_id, tier_id, quantity"), 400
    if quantity < 1:
        return jsonify(error="quantity must be at least 1"), 400

    con = connect()
    # BEGIN IMMEDIATE serializes SQLite writers, helping prevent concurrent overbooking in this demo.
    con.execute("BEGIN IMMEDIATE")
    expire_holds(con)
    user = user_by_id(con, attendee_id)
    tier = con.execute("""
        SELECT t.*,e.active,e.sales_cutoff FROM ticket_tiers t
        JOIN events e ON e.id=t.event_id WHERE t.id=?
    """, (tier_id,)).fetchone()
    if not user or user["role"] != "Attendee":
        con.rollback(); con.close()
        return jsonify(error="Only an Attendee can reserve tickets"), 403
    if not tier or not tier["active"]:
        con.rollback(); con.close()
        return jsonify(error="Event/ticket tier not found or inactive"), 404
    if tier["sales_cutoff"]:
        try:
            cutoff = datetime.fromisoformat(tier["sales_cutoff"])
            if datetime.now() >= cutoff:
                con.rollback(); con.close()
                return jsonify(error="Ticket sales have closed"), 409
        except ValueError:
            pass
    now = int(time.time())
    held = con.execute("SELECT COALESCE(SUM(quantity),0) FROM orders WHERE tier_id=? AND status='HELD' AND hold_expires>?",
                       (tier_id,now)).fetchone()[0]
    available = tier["quantity"] - tier["sold"] - held
    if quantity > available:
        con.rollback(); con.close()
        return jsonify(error=f"Not enough tickets. Available: {available}"), 409
    order_id = str(uuid.uuid4())
    expires = now + HOLD_SECONDS
    total = tier["price"] * quantity
    con.execute("INSERT INTO orders(id,attendee_id,tier_id,quantity,status,hold_expires,total,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (order_id,attendee_id,tier_id,quantity,"HELD",expires,total,now))
    con.commit()
    con.close()
    return jsonify(order_id=order_id, status="HELD", quantity=quantity, total=total,
                   expires_at=datetime.fromtimestamp(expires).isoformat(),
                   message="Ticket held for 10 minutes. Complete mock payment before expiry."), 201

@app.post("/api/payments/mock")
def mock_payment():
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    approve = bool(data.get("approve", True))
    if not order_id:
        return jsonify(error="Required: order_id, approve (true/false)"), 400
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    expire_holds(con)
    order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        con.rollback(); con.close()
        return jsonify(error="Order not found"), 404
    if order["status"] != "HELD" or order["hold_expires"] <= int(time.time()):
        con.rollback(); con.close()
        return jsonify(error="Hold expired or order is no longer payable"), 409
    status = "PAID" if approve else "REJECTED"
    con.execute("INSERT INTO payment_transactions(order_id,status,amount,created_at) VALUES(?,?,?,?)",
                (order_id,status,order["total"],int(time.time())))
    con.execute("UPDATE orders SET status=? WHERE id=?", (status,order_id))
    if approve:
        con.execute("UPDATE ticket_tiers SET sold=sold+? WHERE id=?", (order["quantity"],order["tier_id"]))
    con.commit()
    con.close()
    return jsonify(order_id=order_id, payment_status=status,
                   message="Mock payment completed. No real money was charged."), 200

@app.get("/api/orders/<order_id>")
def get_order(order_id):
    con = connect()
    expire_holds(con)
    row = con.execute("""
      SELECT o.id,o.status,o.quantity,o.total,o.hold_expires,u.name AS attendee,
             e.title AS event,t.name AS tier
      FROM orders o JOIN users u ON u.id=o.attendee_id
      JOIN ticket_tiers t ON t.id=o.tier_id JOIN events e ON e.id=t.event_id
      WHERE o.id=?
    """,(order_id,)).fetchone()
    con.close()
    if not row:
        return jsonify(error="Order not found"), 404
    return jsonify(dict(row))

@app.get("/api/analytics/<int:organizer_id>")
def analytics(organizer_id):
    con = connect()
    user = user_by_id(con, organizer_id)
    if not user or user["role"] not in ("Organizer","Admin"):
        con.close()
        return jsonify(error="Only an Organizer or Admin can view analytics"), 403
    rows = con.execute("""
      SELECT e.id,e.title,
        COALESCE(SUM(CASE WHEN o.status='PAID' THEN o.total ELSE 0 END),0) AS revenue,
        COALESCE(SUM(CASE WHEN o.status='PAID' THEN o.quantity ELSE 0 END),0) AS tickets_sold,
        COALESCE(SUM(CASE WHEN o.status IN ('PAID','REJECTED','EXPIRED') THEN 1 ELSE 0 END),0) AS completed_or_failed_orders,
        COALESCE(SUM(CASE WHEN o.status='HELD' THEN 1 ELSE 0 END),0) AS active_holds
      FROM events e LEFT JOIN ticket_tiers t ON t.event_id=e.id
      LEFT JOIN orders o ON o.tier_id=t.id
      WHERE e.organizer_id=? GROUP BY e.id,e.title
    """,(organizer_id,)).fetchall()
    result=[]
    for r in rows:
        d=dict(r)
        denominator=d["completed_or_failed_orders"] + d["active_holds"]
        d["conversion_rate_percent"]=round((d["tickets_sold"]/max(1, denominator))*100,2)
        result.append(d)
    con.close()
    return jsonify(result)

@app.post("/api/jobs/expire-holds")
def run_expiry_job():
    # Demo endpoint for a scheduled worker/cron to call.
    con = connect()
    before = con.execute("SELECT COUNT(*) FROM orders WHERE status='HELD' AND hold_expires<=?",(int(time.time()),)).fetchone()[0]
    expire_holds(con)
    con.close()
    return jsonify(expired_orders=before)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
