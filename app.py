from flask import Flask, request, send_file, render_template
from werkzeug.utils import secure_filename
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import os

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ✅ Allow Shopify to embed app in iframe
@app.after_request
def add_headers(response):
    response.headers['Content-Security-Policy'] = "frame-ancestors https://admin.shopify.com https://*.myshopify.com"
    response.headers['X-Frame-Options'] = "ALLOWALL"
    return response

class TransferSheetPDF(FPDF):
    def __init__(self, stock_transfer_title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_transfer_title = stock_transfer_title

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
        self.cell(0, 5, "Vendor: STORE1", ln=True)
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
        col_widths = [15, 30, 70, 30, 25]
        headers = ["QTY", "SKU", "Product", "Bin Location", "Price"]
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()

        self.set_font("Arial", "", 12)
        line_height = 8
        for _, row in data.iterrows():
            self.cell(col_widths[0], line_height * 2, str(row.get("Quantity", "")), border=1)
            self.cell(col_widths[1], line_height * 2, str(row.get("SKU", "")), border=1)
            x = self.get_x()
            y = self.get_y()
            self.multi_cell(col_widths[2], line_height, str(row.get("Product", "")), border=1)
            self.set_xy(x + col_widths[2], y)
            self.cell(col_widths[3], line_height * 2, str(row.get("Transfer Bin Location", "")), border=1)
            self.cell(col_widths[4], line_height * 2, str(row.get("Retail Price", "")), border=1)
            self.ln()

@app.route("/", methods=["GET", "POST"])
def upload_csv():
    if request.method == "POST":
        file = request.files["csv"]
        if not file:
            return "No file uploaded", 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        df = pd.read_csv(filepath)
        stock_transfer_title = df["Stock Transfer"].iloc[0]
        pdf = TransferSheetPDF(stock_transfer_title)
        pdf.add_page()
        pdf.transfer_table(df)

        title_str = str(stock_transfer_title).strip().replace(' ', '_')
        output_path = os.path.join("outputs", f"{title_str}.pdf")
        os.makedirs("outputs", exist_ok=True)
        pdf.output(output_path)

        return send_file(output_path, as_attachment=True)

    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
