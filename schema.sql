CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('Admin','Organizer','Attendee'))
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  organizer_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  description TEXT,
  sales_cutoff TEXT,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE ticket_tiers (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id),
  name TEXT NOT NULL,
  price REAL NOT NULL,
  quantity INTEGER NOT NULL,
  sold INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE orders (
  id TEXT PRIMARY KEY,
  attendee_id INTEGER NOT NULL REFERENCES users(id),
  tier_id INTEGER NOT NULL REFERENCES ticket_tiers(id),
  quantity INTEGER NOT NULL,
  status TEXT NOT NULL,
  hold_expires INTEGER NOT NULL,
  total REAL NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE payment_transactions (
  id INTEGER PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(id),
  status TEXT NOT NULL,
  amount REAL NOT NULL,
  created_at INTEGER NOT NULL
);
