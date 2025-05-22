import os
import requests
import certifi
import pandas as pd
from flask import Flask, request, send_file, render_template, Response, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps

# Load environment variables and configure Flask app
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "changeme")  # Secret key for session management
app.config["SESSION_COOKIE_SECURE"] = True
app.wsgi_app = ProxyFix(app.wsgi_app)  # Middleware for handling proxy headers
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# Shopify and Stocky API configuration
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
STOCKY_API_KEY = os.getenv("STOCKY_API_KEY")
VENDOR_OPTIONS = ["Warehouse", "Store 1"]

# Mapping location IDs to human-readable names
LOCATION_NAMES = {
    "78527987890": "TEST - WAREHOUSE",
    "78528086194": "TEST - IN-STORE",
    "75578179762": "Nanaimo Store",
    "72534458546": "Warehouse",
    "76564201650": "BRS Endless Aisle",
    # Add more as needed
}

def get_location_name(location_id):
    """Get the human-readable name for a location ID."""
    return LOCATION_NAMES.get(str(location_id), str(location_id))

def get_stocky_transfers():
    """Fetch inventory transfers from the Stocky API."""
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
                    # Filter transfers to show only "draft" and "in transit"
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

@app.route("/transfer_items/<int:transfer_id>")
def transfer_items(transfer_id):
    """Fetch items for a specific transfer from the Stocky API."""
    url = f"https://stocky.shopifyapps.com/api/v2/stock_transfers/{transfer_id}.json"
    headers = {
        "Authorization": f"API KEY={STOCKY_API_KEY}",
        "Store-Name": SHOPIFY_STORE,
        "Content-Type": "application/json"
    }
    resp = requests.get(url, headers=headers)
    if resp.ok:
        transfer = resp.json().get("stock_transfer", {})
        items = transfer.get("stock_transfer_items", [])
        item_data = []
        for item in items:
            item_data.append({
                "id": item.get("id"),
                "inventory_item_id": item.get("inventory_item_id"),
                "product_title": item.get("product_title", ""),
                "variant_title": item.get("variant_title", ""),
                "quantity": item.get("quantity", ""),
                "status": item.get("status", ""),
                # No bin_location available
            })
        return {"items": item_data}
    return {"items": []}, 404

class TransferSheetPDF(FPDF):
    """Custom PDF class for generating transfer sheets."""
    def __init__(self, stock_transfer_title, vendor, clerk, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_transfer_title = stock_transfer_title
        self.vendor = vendor
        self.clerk = clerk

    def header(self):
        """Define the header for the PDF."""
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
        """Generate a table of transfer items."""
        self.set_font("Arial", "B", 12)
        col_widths = [15, 140, 35]  # Adjust as needed for your page size
        headers = ["QTY", "Title", "Bin Location"]
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, border=1, align='C')
        self.ln()
        self.set_font("Arial", "", 10)
        line_height = 6
        for item in items:
            self.cell(col_widths[0], line_height, str(item.get("qty", "")), border=1, align='C')
            self.cell(col_widths[1], line_height, str(item.get("title", "")), border=1)
            self.cell(col_widths[2], line_height, str(item.get("bin_location", "")), border=1, align='C')
            self.ln()

# Authentication decorator to protect routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You need to log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == '37' and password == '1234':  # Example credentials
            session['user_id'] = username
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Handle user logout."""
    session.pop('user_id', None)
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Main route for uploading CSVs and generating PDFs."""
    if request.method == "POST":
        # Handle form submission
        csv_file = request.files.get("csv")
        vendor = request.form.get("vendor")
        clerk = request.form.get("clerk")

        if not csv_file or not vendor or not clerk:
            flash("All fields are required.", "danger")
            return redirect(url_for("index"))

        # Save the uploaded CSV file
        csv_filename = secure_filename(csv_file.filename)
        csv_path = os.path.join(UPLOAD_FOLDER, csv_filename)
        csv_file.save(csv_path)

        # Generate the PDF
        pdf_filename = f"{csv_filename.rsplit('.', 1)[0]}.pdf"
        pdf_path = os.path.join("outputs", pdf_filename)

        try:
            # Read CSV and generate PDF
            df = pd.read_csv(csv_path)
            items = []
            for _, row in df.iterrows():
                qty = str(row.get("Quantity", ""))
                product_title = str(row.get("Product", ""))
                variant_title = row.get("Title", "")
                if variant_title and variant_title != "Default Title":
                    full_title = f"{product_title} ({variant_title})"
                else:
                    full_title = product_title
                bin_location = str(row.get("Transfer Bin Location", ""))
                items.append({
                    "qty": qty,
                    "title": full_title,
                    "bin_location": bin_location,
                })

            pdf = TransferSheetPDF(stock_transfer_title="Inventory Transfer", vendor=vendor, clerk=clerk)
            pdf.add_page()
            pdf.transfer_table(items)
            pdf.output(pdf_path)

            # Send the generated PDF to the user
            return send_file(pdf_path, as_attachment=True)
        except Exception as e:
            print("Error generating PDF:", e)
            flash("An error occurred while generating the PDF.", "danger")
            return redirect(url_for("index"))

    # Render the main page with transfers and vendor options
    transfers = get_stocky_transfers()
    return render_template(
        "index.html",
        vendor_options=VENDOR_OPTIONS,
        transfers=transfers,
        today_date=datetime.today().strftime("%Y-%m-%d")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
