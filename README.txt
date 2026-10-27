MULTI-TENANT EVENT & TICKET RESERVATION SYSTEM (STARTER)

WHAT IS INCLUDED
- Flask web app and JSON API
- Admin / Organizer / Attendee role checks (demo IDs, not secure login)
- Events and ticket tiers
- 10-minute ticket holds
- Mock approve/reject payment endpoint
- Analytics API
- Expired-hold cleanup endpoint
- SQLite transactions (BEGIN IMMEDIATE) to serialize writes in this local demo
- Postman collection and ER diagram

EASIEST WAY TO TRY WITHOUT VS CODE
Option A: Replit (runs in your browser)
1. Create/login to a Replit account.
2. Create a new Python project.
3. Upload/extract these files into the project (or upload the ZIP and extract it in Replit).
4. Open the Shell/Console and run:
       pip install -r requirements.txt
       python app.py
5. Open the web preview. Try /api/users and /api/events.
   Note: If the platform has a web-terminal, commands are typed there, not in VS Code.

Option B: Run on your computer without VS Code
1. Install Python 3 from python.org and make sure "Add Python to PATH" is selected.
2. Extract this ZIP.
3. Open the extracted folder in File Explorer.
4. Click the address bar, type cmd, and press Enter.
5. Run:
       pip install -r requirements.txt
       python app.py
6. Open http://127.0.0.1:5000 in your browser.

DEMO USER IDS
1 = Demo Organizer (organizer@example.com)
2 = Demo Attendee (attendee@example.com)
3 = Demo Admin (admin@example.com)

POSTMAN TEST EXAMPLE
POST http://127.0.0.1:5000/api/holds
Body -> raw -> JSON:
{
  "attendee_id": 2,
  "tier_id": 1,
  "quantity": 2
}
Copy the order_id from the response.

POST http://127.0.0.1:5000/api/payments/mock
Body -> raw -> JSON:
{
  "order_id": "PASTE_ORDER_ID_HERE",
  "approve": true
}
Use approve:false to simulate a rejected payment.

GITHUB
To get your own GitHub repository link without VS Code:
1. Sign in to github.com in your browser.
2. Click + (top right) -> New repository.
3. Name it event-ticket-reservation and create it.
4. On the repository page choose "uploading an existing file".
5. Upload the extracted project files (you can drag the files/folders into the browser).
6. Commit changes. Your repository URL will look like:
   https://github.com/YOUR-USERNAME/event-ticket-reservation

IMPORTANT LIMITATIONS
This is a starter/demo, not production ready. It does NOT yet include Redis caching, a real background queue, a proper asynchronous payment provider, real login/password security, seat maps, or production PostgreSQL. It includes a manual expiry endpoint and SQLite transaction handling so you can understand the core flow. Do not use real customer data or real payments.
