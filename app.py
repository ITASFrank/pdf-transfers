import os
import requests
import certifi
import pandas as pd
from flask import Flask, request, send_file, render_template
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
os.makedirs("outputs", exist_ok=True)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
STOCKY_API_KEY = os.getenv("STOCKY_API_KEY")
VENDOR_OPTIONS = ["Warehouse", "Store 1"]

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
                            "origin_name": get_location_name(transfer.get("from_location_id", "")),
                            "destination_name": get_location_name(transfer.get("to_location_id", "")),
                            "status": status,
                            "note": transfer.get("note", ""),
                            "csv_url": f"https://stocky.shopifyapps.com/stock_transfers/{transfer.get('id')}/download.csv",
                            "stocky_url": f"https://stocky.shopifyapps.com/stock_transfers/{transfer.get('id')}"
                        })
        except Exception as e:
            print("Error fetching Stocky transfers:", e)
    return transfers

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

    def transfer_table(self, items):
        self.set_font("Arial", "B", 12)
        col_widths = [15, 35, 100, 30]
        headers = ["QTY", "SKU", "Title", "Bin Location"]
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()
        self.set_font("Arial", "", 10)
        line_height = 6
        for item in items:
            qty = str(item.get("quantity", ""))
            sku = str(item.get("sku", ""))
            title = str(item.get("title", ""))
            bin_loc = str(item.get("bin_location", ""))
            self.cell(col_widths[0], line_height, qty, border=1, align='C')
            self.cell(col_widths[1], line_height, sku, border=1)
            self.cell(col_widths[2], line_height, title, border=1)
            self.cell(col_widths[3], line_height, bin_loc, border=1, align='C')
            self.ln()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            file = request.files.get("csv")
            vendor = request.form.get("vendor")
            clerk = request.form.get("clerk")
            if not file or not vendor or not clerk:
                return "Missing required fields", 400
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            df = pd.read_csv(filepath)
            items = []
            for _, row in df.iterrows():
                items.append({
                    "quantity": row.get("QTY", row.get("Quantity", "")),
                    "sku": row.get("SKU", ""),
                    "title": row.get("Title", row.get("Product", "")),
                    "bin_location": row.get("Bin Location", row.get("Transfer Bin Location", ""))
                })

            stock_transfer_title = str(df["Stock Transfer"].iloc[0]) if "Stock Transfer" in df and not df.empty else filename

            pdf = TransferSheetPDF(stock_transfer_title, vendor, clerk)
            pdf.add_page()
            pdf.transfer_table(items)

            output_path = os.path.join("outputs", f"transfer_{stock_transfer_title.replace(' ', '_')}.pdf")
            pdf.output(output_path)
            return send_file(output_path, as_attachment=True)
        except Exception as e:
            # Instead of generic 500, show the error in the browser for now
            return f"PDF generation failed:<br><pre>{str(e)}</pre>", 500

    # GET logic as before
    transfers = get_stocky_transfers()
    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        transfers=transfers,
        today_date=datetime.today().strftime("%Y-%m-%d")
    )
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
