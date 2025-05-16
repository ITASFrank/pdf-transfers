import os
import requests
import certifi
from flask import Flask, request, send_file, render_template, redirect, url_for, flash
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
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
STOCKY_API_KEY = os.getenv("STOCKY_API_KEY")
VENDOR_OPTIONS = ["Warehouse", "Store 1"]

LOCATION_NAMES = {
    "78527987890": "TEST - WAREHOUSE",
    "78528086194": "TEST - IN-STORE",
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
                            "csv_url": f"https://stocky.shopifyapps.com/stock_transfers/{transfer.get('id')}/download.csv",
                            "transfer_url": f"https://stocky.shopifyapps.com/stock_transfers/{transfer.get('id')}",
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
            row_values = [qty, item, bin_loc, price, ""]
            for i, value in enumerate(row_values):
                self.cell(col_widths[i], line_height * 2, str(value), border=1)
            self.ln()

@app.route("/", methods=["GET", "POST"])
def index():
    download_pdf_url = None
    if request.method == "POST":
        file = request.files["csv"]
        vendor = request.form.get("vendor")
        clerk = request.form.get("clerk")
        if not file or not vendor or not clerk:
            flash("Missing required fields", "danger")
        else:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            df = pd.read_csv(filepath)
            stock_transfer_title = str(df["Stock Transfer"].iloc[0]) if "Stock Transfer" in df.columns else filename.split(".")[0]
            pdf = TransferSheetPDF(stock_transfer_title, vendor, clerk)
            pdf.add_page()
            pdf.transfer_table(df)
            output_pdf = os.path.join(OUTPUT_FOLDER, f"transfer_{stock_transfer_title.replace(' ', '_')}.pdf")
            pdf.output(output_pdf)
            download_pdf_url = url_for("download_pdf", filename=f"transfer_{stock_transfer_title.replace(' ', '_')}.pdf")
            flash("PDF created! Click below to download.", "success")
    transfers = get_stocky_transfers()
    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        transfers=transfers,
        today_date=datetime.today().strftime("%Y-%m-%d"),
        download_pdf_url=download_pdf_url,
    )

@app.route("/outputs/<filename>")
def download_pdf(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
