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
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_SCOPES = os.getenv("SHOPIFY_SCOPES", "read_inventory,read_locations")
REDIRECT_URI = os.getenv("REDIRECT_URI")
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

    token = session.get("shopify_access_token")
    active_transfers = []
    if token:
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-04/transfers.json"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers, verify=certifi.where())
        if response.ok:
            data = response.json()
            for transfer in data.get("transfers", []):
                if transfer.get("status") == "open":
                    active_transfers.append({
                        "id": transfer.get("id"),
                        "name": transfer.get("name", ""),
                        "created_at": transfer.get("created_at", "")[:10],
                        "origin": transfer.get("origin_location", {}).get("name", ""),
                        "destination": transfer.get("destination_location", {}).get("name", ""),
                        "status": transfer.get("status", "")
                    })

return render_template(
    "index.html",
    vendor_options=VENDOR_OPTIONS,
    active_transfers=active_transfers,
    shopify_store=SHOPIFY_STORE.split(".")[0],
    today_date=datetime.today().strftime("%m/%d/%Y")
)

@app.route("/auth/start")
def auth_start():
    auth_url = (
        f"https://{SHOPIFY_STORE}/admin/oauth/authorize"
        f"?client_id={SHOPIFY_API_KEY}"
        f"&scope={urllib.parse.quote(SHOPIFY_SCOPES)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    token_url = f"https://{SHOPIFY_STORE}/admin/oauth/access_token"
    payload = {
        "client_id": SHOPIFY_API_KEY,
        "client_secret": SHOPIFY_API_SECRET,
        "code": code
    }

    print("Using certifi bundle:", certifi.where())  # Debug log

    response = requests.post(token_url, json=payload, verify=certifi.where())
    if response.status_code == 200:
        session["shopify_access_token"] = response.json().get("access_token")
        return "✅ Token received. You can now call the Shopify API. Visit /transfers"
    else:
        return f"❌ Error getting token: {response.text}", 400

@app.route("/transfers")
def fetch_transfers():
    token = session.get("shopify_access_token")
    if not token:
        return redirect("/auth/start")

    url = f"https://{SHOPIFY_STORE}/admin/api/2024-04/transfers.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers, verify=certifi.where())
    return response.json()

@app.route("/test-ssl")
def test_ssl():
    try:
        r = requests.get("https://www.google.com", verify=certifi.where())
        return f"✅ SSL OK! Status: {r.status_code}"
    except requests.exceptions.SSLError as e:
        return f"❌ SSL Error: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
