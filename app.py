import os
import requests
import certifi
from flask import Flask, request, send_file, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv

os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "changeme")
app.config["SESSION_COOKIE_SECURE"] = True
app.wsgi_app = ProxyFix(app.wsgi_app)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
STOCKY_API_KEY = os.getenv("STOCKY_API_KEY")
VENDOR_OPTIONS = ["Warehouse", "Store 1"]

# Dummy location mapping; replace with live API mapping if available
LOCATION_NAMES = {
    "78527987890": "TEST - WAREHOUSE",
    "78528086194": "TEST - IN-STORE",
    # Add more as needed
}

def get_location_name(location_id):
    return LOCATION_NAMES.get(str(location_id), str(location_id))

def get_stocky_transfers():
    transfers = []
    if STOCKY_API_KEY and SHOPIFY_STORE:
        url = "https://stocky.shopifyapps.com/api/v2/stock_transfers.json"
        headers = {
            "Authorization": f"API KEY={STOCKY_API_KEY}",
            "Store-Name": SHOPIFY_STORE,
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers)
            if response.ok:
                data = response.json()
                for transfer in data.get("stock_transfers", []):
                    # Show only "draft" and "in transit" (not archived, not received)
                    status = (
                        "Draft" if transfer.get("status") == "draft"
                        else "In Transit" if transfer.get("status") == "sent"
                        else "Received" if transfer.get("status") == "received"
                        else transfer.get("status", "").capitalize()
                    )
                    if not transfer.get("archived", False) and status != "Received":
                        transfers.append({
                            "id": transfer.get("id"),
                            "sequential_id": transfer.get("sequential_id", transfer.get("id")),
                            "created_at": transfer.get("created_at", "")[:10],
                            "origin_id": transfer.get("from_location_id", ""),
                            "origin_name": get_location_name(transfer.get("from_location_id", "")),
                            "destination_id": transfer.get("to_location_id", ""),
                            "destination_name": get_location_name(transfer.get("to_location_id", "")),
                            "status": status,
                            "note": transfer.get("note", ""),
                            "csv_url": f"https://stocky.shopifyapps.com/stock_transfers/{transfer.get('id')}/download.csv"
                        })
        except Exception as e:
            print("Error fetching Stocky transfers:", e)
    return transfers

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["csv"]
        vendor = request.form.get("vendor")
        clerk = request.form.get("clerk")
        if not file or not vendor or not clerk:
            return "Missing required fields", 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        # PDF logic here (omitted for brevity, as before)
        return "Upload received!"
    transfers = get_stocky_transfers()
    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        transfers=transfers,
        today_date=datetime.today().strftime("%Y-%m-%d")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
