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
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASS = os.getenv("SHOPIFY_API_PASS")
STOCKY_API_KEY = os.getenv("STOCKY_API_KEY")
VENDOR_OPTIONS = ["Warehouse", "Store 1"]

class TransferSheetPDF(FPDF):
    def __init__(self, stock_transfer_title, vendor, clerk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_transfer_title = stock_transfer_title
        self.vendor = vendor
        self.clerk = clerk

    def header(self):
        try:
            self.image("static/logo.png", x=10, y=8, w=30)
        except:
            pass
        self.set_font("Arial", "", 10)
        self.set_xy(10, 35)
        self.cell(0, 5, "Harbour Chandler", ln=True)
        self.set_x(10)
        self.cell(0, 5, "52 Esplanade", ln=True)
        self.set_x(10)
        self.cell(0, 5, "Nanaimo, BC", ln=True)
        self.set_xy(150, 10)
        self.cell(0, 5, f"Vendor: {self.vendor}", ln=True)
        self.set_x(150)
        self.cell(0, 5, f"Clerk: {self.clerk}", ln=True)
        self.set_x(150)
        self.cell(0, 5, f"Date: {datetime.today().strftime('%m/%d/%Y')}", ln=True)
        self.set_x(150)
        self.cell(0, 5, f"Page: {self.page_no()}", ln=True)
        self.set_y(50)
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, f"Transfer # {self.stock_transfer_title}", ln=True, align="C")
        self.set_line_width(0.5)
        self.line(10, 63, 200, 63)
        self.ln(5)

    def footer(self):
        self.set_line_width(0.5)
        self.line(10, 63, 200, 63)
        self.ln(5)

    def transfer_table(self, items):
        self.set_font("Arial", "B", 12)
        col_widths = [15, 80, 40, 25, 25]
        headers = ["QTY", "Item (Title + Variant)", "Bin Location", "Price", ""]
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()
        self.set_font("Arial", "", 10)
        line_height = 5
        for item in items:
            qty = str(item.get("quantity", ""))
            title = f"{item.get('product_title', '')} ({item.get('variant_title', '')})"
            bin_loc = item.get("bin_location", "N/A")
            price = item.get("retail_price", "")
            row = [qty, title, bin_loc, price, ""]
            for i, value in enumerate(row):
                self.cell(col_widths[i], line_height * 2, str(value), border=1)
            self.ln()

def get_stocky_transfers():
    active_transfers = []
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
                    if not transfer.get("archived", False):
                        active_transfers.append({
                            "id": transfer.get("id"),
                            "sequential_id": transfer.get("sequential_id", transfer.get("id")),
                            "created_at": transfer.get("created_at", "")[:10],
                            "origin": transfer.get("from_location_id", ""),
                            "destination": transfer.get("to_location_id", ""),
                            "status": transfer.get("status", ""),
                            "note": transfer.get("note", ""),
                            "items": transfer.get("stock_transfer_items", [])
                        })
        except Exception as e:
            print("Error fetching Stocky transfers:", e)
    return active_transfers

def fetch_bin_location(inventory_item_id):
    url = (
        f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASS}@"
        f"{SHOPIFY_STORE}/admin/api/2024-04/inventory_items/{inventory_item_id}/metafields.json"
    )
    try:
        response = requests.get(url, verify=certifi.where())
        if response.ok:
            for m in response.json().get("metafields", []):
                if m.get("namespace") == "stocky" and m.get("key") == "bin_location":
                    return m.get("value")
    except Exception as e:
        print(f"Bin location fetch failed for {inventory_item_id}: {e}")
    return "N/A"

@app.route("/", methods=["GET"])
def index():
    active_transfers = get_stocky_transfers()
    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        active_transfers=active_transfers,
        today_date=datetime.today().strftime("%m/%d/%Y"),
    )

@app.route("/generate_pdf/<int:transfer_id>", methods=["GET", "POST"])
def generate_pdf(transfer_id):
    vendor = request.args.get("vendor", "Warehouse")
    clerk = request.args.get("clerk", "Auto")
    active_transfers = get_stocky_transfers()
    transfer = next((t for t in active_transfers if t["id"] == transfer_id), None)
    if not transfer:
        return "Transfer not found", 404
    items = []
    for item in transfer["items"]:
        bin_location = fetch_bin_location(item.get("inventory_item_id"))
        items.append({
            "quantity": item.get("quantity"),
            "product_title": item.get("product_title"),
            "variant_title": item.get("variant_title"),
            "bin_location": bin_location,
            "retail_price": "",  # You can fetch price if needed
        })
    pdf = TransferSheetPDF(str(transfer["sequential_id"]), vendor, clerk)
    pdf.add_page()
    pdf.transfer_table(items)
    output_path = os.path.join("outputs", f"transfer_{transfer['sequential_id']}.pdf")
    os.makedirs("outputs", exist_ok=True)
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
