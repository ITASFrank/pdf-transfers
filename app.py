import os
import requests
import urllib.parse
import pandas as pd
import certifi
from flask import Flask, request, redirect, session, send_file, render_template
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

    def transfer_table(self, data):
        self.set_font("Arial", "B", 12)
        col_widths = [15, 100, 25, 25, 25]
        headers = ["QTY", "Item (SKU + Description)", "Bin", "Price", ""]

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()

        self.set_font("Arial", "", 10)
        line_height = 5

        for _, row in data.iterrows():
            qty = str(row.get("Quantity", ""))
            sku = str(row.get("SKU", ""))
            product = str(row.get("Product", ""))
            item = f"{sku} - {product}"
            bin_loc = str(row.get("Transfer Bin Location", ""))
            price = f"${row.get('Retail Price', 0):.2f}"
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
            self.multi_cell(col_widths[3], row_height, price, border=1, align="R")
            self.set_y(y_start + row_height)

@app.route("/", methods=["GET", "POST"])
def upload_csv():
    if request.method == "POST":
        file = request.files["csv"]
        vendor = request.form.get("vendor")
        clerk = request.form.get("clerk")

        if not file or not vendor or not clerk:
            return "Missing required fields", 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        df = pd.read_csv(filepath)
        stock_transfer_title = df["Stock Transfer"].iloc[0]
        pdf = TransferSheetPDF(stock_transfer_title, vendor, clerk)
        pdf.add_page()
        pdf.transfer_table(df)

        output_path = os.path.join("outputs", f"{stock_transfer_title.strip().replace(' ', '_')}.pdf")
        os.makedirs("outputs", exist_ok=True)
        pdf.output(output_path)

        return send_file(output_path, as_attachment=True)

    # --------- STOCKY TRANSFERS API ---------
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
                # Show all transfers with status open or sent (not archived)
                if transfer.get("status") in ["open", "sent"] and not transfer.get("archived", False):
                    active_transfers.append({
                        "id": transfer.get("id"),
                        "name": transfer.get("sequential_id", transfer.get("id")),
                        "created_at": transfer.get("created_at", "")[:10],
                        "origin": transfer.get("from_location_id", ""),
                        "destination": transfer.get("to_location_id", ""),
                        "status": transfer.get("status", "")
                    })
    except Exception as e:
        print("Error fetching Stocky transfers:", e)

    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        active_transfers=active_transfers,
        shopify_store=SHOPIFY_STORE.split(".")[0],
        today_date=datetime.today().strftime("%m/%d/%Y")
    )

@app.route("/test-ssl")
def test_ssl():
    try:
        r = requests.get("https://www.google.com", verify=certifi.where())
        return f"✅ SSL OK! Status: {r.status_code}"
    except requests.exceptions.SSLError as e:
        return f"❌ SSL Error: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
