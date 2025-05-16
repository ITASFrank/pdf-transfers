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

    def transfer_table(self, items):
        # 4 columns: QTY, SKU, Title, Bin Location
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
        file = request.files.get("csv")
        vendor = request.form.get("vendor")
        clerk = request.form.get("clerk")
        if not file or not vendor or not clerk:
            return "Missing required fields", 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Accepts either "QTY" or "Quantity" and "BIN LOCATION" or "Transfer Bin Location"
        df = pd.read_csv(filepath)
        items = []
        for _, row in df.iterrows():
            items.append({
                "quantity": row.get("QTY", row.get("Quantity", "")),
                "sku": row.get("SKU", ""),
                "title": row.get("Title", row.get("Product", "")),
                "bin_location": row.get("Bin Location", row.get("Transfer Bin Location", ""))
            })

        # Use the Stock Transfer # from the first row if it exists
        stock_transfer_title = str(df.get("Stock Transfer", [filename])[0]) if "Stock Transfer" in df else filename

        pdf = TransferSheetPDF(stock_transfer_title, vendor, clerk)
        pdf.add_page()
        pdf.transfer_table(items)

        output_path = os.path.join("outputs", f"transfer_{stock_transfer_title.replace(' ', '_')}.pdf")
        pdf.output(output_path)

        return send_file(output_path, as_attachment=True)

    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        today_date=datetime.today().strftime("%Y-%m-%d")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
