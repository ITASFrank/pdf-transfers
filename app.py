import os
import requests
import certifi
from flask import Flask, request, send_file, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

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
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASS = os.getenv("SHOPIFY_API_PASS") # Needs Admin API access, get from Shopify App settings
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

    def transfer_table(self, data):
        self.set_font("Arial", "B", 12)
        col_widths = [15, 90, 40, 30, 25]
        headers = ["QTY", "Item", "Bin Location", "SKU", ""]

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()

        self.set_font("Arial", "", 10)
        line_height = 5

        for _, row in data.iterrows():
            qty = str(row.get("Quantity", ""))
            item = str(row.get("Product", ""))
            bin_loc = str(row.get("Bin Location", ""))
            sku = str(row.get("SKU", ""))
            item_lines = self.get_string_width(item) / col_widths[1]
            num_lines = int(item_lines) + 1
            row_height = line_height * num_lines
            x_start = self.get_x()
            y_start = self.get_y()
            self.multi_cell(col_widths[0], row_height, qty, border=1, align="C")
            self.set_xy(x_start + col_widths[0], y_start)
            self.multi_cell(col_widths[1], line_height, item, border=1)
            self.set_xy(x_start + col_widths[0] + col_widths[1], y_start)
            self.multi_cell(col_widths[2], row_height, bin_loc, border=1, align="C")
            self.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start)
            self.multi_cell(col_widths[3], row_height, sku, border=1, align="C")
            self.set_y(y_start + row_height)

@app.route("/")
def home():
    # List all (non-archived) Stocky transfers
    transfers = []
    if STOCKY_API_KEY and SHOPIFY_STORE:
        url = "https://stocky.shopifyapps.com/api/v2/stock_transfers.json"
        headers = {
            "Authorization": f"API KEY={STOCKY_API_KEY}",
            "Store-Name": SHOPIFY_STORE,
            "Content-Type": "application/json"
        }
        resp = requests.get(url, headers=headers)
        if resp.ok:
            for t in resp.json().get("stock_transfers", []):
                if not t.get("archived", False):
                    transfers.append({
                        "id": t["id"],
                        "title": t.get("sequential_id") or t.get("id"),
                        "created_at": t.get("created_at", "")[:10],
                        "origin": t.get("from_location_id", ""),
                        "destination": t.get("to_location_id", ""),
                        "item_count": len(t.get("stock_transfer_items", []))
                    })
    return render_template("index.html",
        vendor_options=VENDOR_OPTIONS,
        active_transfers=transfers,
        today_date=datetime.today().strftime("%m/%d/%Y")
    )

@app.route("/transfer/<int:transfer_id>/pdf")
def transfer_pdf(transfer_id):
    # Fetch Stocky transfer
    transfer = None
    url = f"https://stocky.shopifyapps.com/api/v2/stock_transfers/{transfer_id}.json"
    headers = {
        "Authorization": f"API KEY={STOCKY_API_KEY}",
        "Store-Name": SHOPIFY_STORE,
        "Content-Type": "application/json"
    }
    resp = requests.get(url, headers=headers)
    if not resp.ok:
        return f"Error fetching Stocky transfer: {resp.text}", 500
    transfer = resp.json().get("stock_transfer", {})
    items = transfer.get("stock_transfer_items", [])

    # For each item, lookup bin location (by SKU) via Shopify API/metafield
    rows = []
    for item in items:
        sku = item.get("sku", "")
        # 1. Try Shopify API (inventory_item_id)
        bin_location = ""
        try:
            shopify_url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASS}@{SHOPIFY_STORE}/admin/api/2024-04/inventory_items/{item['inventory_item_id']}.json"
            shopify_resp = requests.get(shopify_url)
            if shopify_resp.ok:
                meta = shopify_resp.json().get("inventory_item", {}).get("metafields", [])
                for m in meta:
                    if m.get("namespace") == "stocky" and m.get("key") == "bin_location":
                        bin_location = m.get("value")
                        break
        except Exception as ex:
            bin_location = ""

        rows.append({
            "Quantity": item.get("quantity", ""),
            "Product": item.get("product_title", ""),
            "Bin Location": bin_location,
            "SKU": sku
        })

    df = pd.DataFrame(rows)
    # Generate PDF
    pdf = TransferSheetPDF(str(transfer.get("sequential_id") or transfer.get("id")), "Warehouse", "Clerk")
    pdf.add_page()
    pdf.transfer_table(df)
    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", f"transfer_{transfer_id}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

@app.route("/test-ssl")
def test_ssl():
    try:
        r = requests.get("https://www.google.com", verify=certifi.where())
        return f"✅ SSL OK! Status: {r.status_code}"
    except requests.exceptions.SSLError as e:
        return f"❌ SSL Error: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
