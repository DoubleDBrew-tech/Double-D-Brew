"""
Simple Inventory System (Flask + SQLite)
Features:
 - Product listing (create / read / update / delete)
 - Stock monitoring (adjust stock, low-stock view using reorder_threshold)
 - Inventory reporting (download CSV, summary counts & values)

How to run:
1. Create virtualenv (optional)
   python -m venv venv
   source venv/bin/activate   # Mac/Linux
   venv\Scripts\activate      # Windows

2. Install requirements:
   pip install flask sqlalchemy pandas

3. Run:
   python app.py

Open http://127.0.0.1:5000/ in your browser.
"""
from flask import Flask, render_template_string, request, redirect, url_for, send_file, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from io import StringIO
from flask import Response
import csv
import os
import datetime
from flask import send_file
from flask import render_template_string


app = Flask(__name__)
app.secret_key = "dev-secret-key"
# SQLite DB in same folder
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------------
# Database models
# ----------------------
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True, nullable=False)  # Stock Keeping Unit
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    price = db.Column(db.Float, nullable=False, default=0.0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    reorder_threshold = db.Column(db.Integer, nullable=False, default=5)

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "stock": self.stock,
            "reorder_threshold": self.reorder_threshold
        }

# ----------------------
# DB init + sample data
# ----------------------
def init_db():
    db.create_all()
    if Product.query.count() == 0:
        sample = [
            Product(sku="DBR-001", name="Espresso Beans 250g", description="Dark roast", price=250.0, stock=20, reorder_threshold=5),
            Product(sku="DBR-002", name="Milk (1L)", description="Fresh milk", price=80.0, stock=10, reorder_threshold=3),
            Product(sku="DBR-003", name="Cup (12oz)", description="Disposable cup", price=2.5, stock=200, reorder_threshold=50),
        ]
        db.session.bulk_save_objects(sample)
        db.session.commit()

with app.app_context():
    init_db()

# ----------------------
# Templates
# ----------------------
BASE_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Inventory System</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('index') }}">Inventory</a>
        <div class="collapse navbar-collapse">
          <ul class="navbar-nav me-auto">
            <li class="nav-item"><a class="nav-link" href="{{ url_for('index') }}">Dashboard</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('list_products') }}">Products</a></li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('low_stock') }}">Low Stock</a></li>
          </ul>
          <a class="btn btn-outline-light" href="{{ url_for('export_csv') }}">Export CSV</a>
        </div>
      </div>
    </nav>
    <div class="container py-4">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          {% for m in messages %}
            <div class="alert alert-info">{{ m }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {{ body|safe }}
    </div>
  </body>
</html>
"""

# ----------------------
# Routes
# ----------------------
@app.route('/')
def index():
    products = Product.query.all()
    total_items = sum(p.stock for p in products)
    total_value = sum(p.stock * p.price for p in products)
    low_count = Product.query.filter(Product.stock <= Product.reorder_threshold).count()
    body = f"""
    <div class="row mb-4">
      <div class="col-md-4"><div class="card p-3"><h5>Total product types</h5><h2>{len(products)}</h2></div></div>
      <div class="col-md-4"><div class="card p-3"><h5>Total items</h5><h2>{total_items}</h2></div></div>
      <div class="col-md-4"><div class="card p-3"><h5>Inventory value</h5><h2>₱{total_value:,.2f}</h2></div></div>
    </div>
    <div class="mb-3 d-flex justify-content-between align-items-center">
      <h4>Recent products</h4>
      <a class="btn btn-primary" href="{url_for('add_product')}">Add product</a>
    </div>
    <table class="table table-striped">
      <thead><tr><th>SKU</th><th>Name</th><th>Stock</th><th>Price</th><th>Threshold</th><th>Actions</th></tr></thead>
      <tbody>
        {''.join(['''<tr><td>{sku}</td><td>{name}</td><td>{stock}</td><td>₱{price:,.2f}</td><td>{th}</td>
        <td><a class="btn btn-sm btn-outline-secondary" href="{edit}">Edit</a>
        <a class="btn btn-sm btn-outline-danger" href="{delete}">Delete</a>
        <a class="btn btn-sm btn-outline-success" href="{adjust}">Adjust Stock</a></td></tr>'''.format(
            sku=p.sku, name=p.name, stock=p.stock, price=p.price, th=p.reorder_threshold,
            edit=url_for('edit_product', product_id=p.id),
            delete=url_for('delete_product', product_id=p.id),
            adjust=url_for('adjust_stock', product_id=p.id)) for p in products])}
      </tbody>
    </table>
    <div class="mt-4">
      <a href="{url_for('low_stock')}" class="btn btn-warning">View low-stock items ({low_count})</a>
      <a href="{url_for('export_csv')}" class="btn btn-outline-primary">Export CSV</a>
    </div>
    """
    return render_template_string(BASE_HTML, body=body)

# ----------------------
# Product CRUD
# ----------------------
@app.route('/products')
def list_products():
    products = Product.query.order_by(Product.name).all()
    rows = "".join([f"""
        <tr>
            <td>{p.sku}</td>
            <td>{p.name}</td>
            <td>{p.description or ''}</td>
            <td>{p.stock}</td>
            <td>₱{p.price:,.2f}</td>
            <td>{p.reorder_threshold}</td>
            <td>
              <a class="btn btn-sm btn-secondary" href="{url_for('edit_product', product_id=p.id)}">Edit</a>
              <a class="btn btn-sm btn-danger" href="{url_for('delete_product', product_id=p.id)}">Delete</a>
              <a class="btn btn-sm btn-success" href="{url_for('adjust_stock', product_id=p.id)}">Adjust Stock</a>
            </td>
        </tr>
        """ for p in products])
    body = f"""
    <div class="d-flex justify-content-between mb-3">
      <h3>Products</h3>
      <div>
        <a class="btn btn-primary" href="{url_for('add_product')}">Add product</a>
        <a class="btn btn-outline-secondary" href="{url_for('index')}">Back</a>
      </div>
    </div>
    <table class="table table-hover">
      <thead><tr><th>SKU</th><th>Name</th><th>Description</th><th>Stock</th><th>Price</th><th>Threshold</th><th>Actions</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """
    return render_template_string(BASE_HTML, body=body)

@app.route('/products/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        sku = request.form.get('sku').strip()
        name = request.form.get('name').strip()
        desc = request.form.get('description').strip()
        price = float(request.form.get('price') or 0)
        stock = int(request.form.get('stock') or 0)
        thresh = int(request.form.get('reorder_threshold') or 5)
        prod = Product(sku=sku, name=name, description=desc, price=price, stock=stock, reorder_threshold=thresh)
        try:
            db.session.add(prod)
            db.session.commit()
            flash("Product added.")
            return redirect(url_for('list_products'))
        except IntegrityError:
            db.session.rollback()
            flash("SKU must be unique. Choose a different SKU.")
            return redirect(url_for('add_product'))
    body = f"""
    <h3>Add Product</h3>
    <form method="post">
      <div class="mb-3"><label class="form-label">SKU</label><input class="form-control" name="sku" required></div>
      <div class="mb-3"><label class="form-label">Name</label><input class="form-control" name="name" required></div>
      <div class="mb-3"><label class="form-label">Description</label><textarea class="form-control" name="description"></textarea></div>
      <div class="row">
        <div class="col"><label class="form-label">Price</label><input class="form-control" name="price" type="number" step="0.01" value="0.00" required></div>
        <div class="col"><label class="form-label">Stock</label><input class="form-control" name="stock" type="number" value="0" required></div>
        <div class="col"><label class="form-label">Reorder threshold</label><input class="form-control" name="reorder_threshold" type="number" value="5" required></div>
      </div>
      <div class="mt-3"><button class="btn btn-success" type="submit">Save</button><a class="btn btn-secondary" href="{url_for('list_products')}">Cancel</a></div>
    </form>
    """
    return render_template_string(BASE_HTML, body=body)

@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(product_id):
    p = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        p.sku = request.form.get('sku').strip()
        p.name = request.form.get('name').strip()
        p.description = request.form.get('description').strip()
        p.price = float(request.form.get('price') or 0)
        p.stock = int(request.form.get('stock') or 0)
        p.reorder_threshold = int(request.form.get('reorder_threshold') or 5)
        try:
            db.session.commit()
            flash("Product updated.")
            return redirect(url_for('list_products'))
        except IntegrityError:
            db.session.rollback()
            flash("SKU must be unique.")
            return redirect(url_for('edit_product', product_id=product_id))
    body = f"""
    <h3>Edit Product</h3>
    <form method="post">
      <div class="mb-3"><label class="form-label">SKU</label><input class="form-control" name="sku" value="{p.sku}" required></div>
      <div class="mb-3"><label class="form-label">Name</label><input class="form-control" name="name" value="{p.name}" required></div>
      <div class="mb-3"><label class="form-label">Description</label><textarea class="form-control" name="description">{p.description or ''}</textarea></div>
      <div class="row">
        <div class="col"><label class="form-label">Price</label><input class="form-control" name="price" type="number" step="0.01" value="{p.price}" required></div>
        <div class="col"><label class="form-label">Stock</label><input class="form-control" name="stock" type="number" value="{p.stock}" required></div>
        <div class="col"><label class="form-label">Reorder threshold</label><input class="form-control" name="reorder_threshold" type="number" value="{p.reorder_threshold}" required></div>
      </div>
      <div class="mt-3"><button class="btn btn-success" type="submit">Save</button><a class="btn btn-secondary" href="{url_for('list_products')}">Cancel</a></div>
    </form>
    """
    return render_template_string(BASE_HTML, body=body)

@app.route('/products/<int:product_id>/delete')
def delete_product(product_id):
    p = Product.query.get_or_404(product_id)
    db.session.delete(p)
    db.session.commit()
    flash("Product deleted.")
    return redirect(url_for('list_products'))

@app.route('/products/<int:product_id>/adjust', methods=['GET', 'POST'])
def adjust_stock(product_id):
    p = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        adj = int(request.form.get('adjust') or 0)
        reason = request.form.get('reason') or ''
        p.stock = max(0, p.stock + adj)
        db.session.commit()
        flash(f"Stock adjusted by {adj}. Reason: {reason}")
        return redirect(url_for('list_products'))
    body = f"""
    <h3>Adjust Stock for {p.name} ({p.sku})</h3>
    <form method="post">
      <div class="mb-3"><label class="form-label">Current stock: <strong>{p.stock}</strong></label></div>
      <div class="mb-3"><label class="form-label">Adjust by (negative to subtract)</label><input class="form-control" name="adjust" type="number" value="0" required></div>
      <div class="mb-3"><label class="form-label">Reason</label><input class="form-control" name="reason"></div>
      <div><button class="btn btn-success" type="submit">Apply</button><a class="btn btn-secondary" href="{url_for('list_products')}">Cancel</a></div>
    </form>
    """
    return render_template_string(BASE_HTML, body=body)

@app.route('/low-stock')
def low_stock():
    items = Product.query.filter(Product.stock <= Product.reorder_threshold).order_by(Product.stock.asc()).all()
    rows = "".join([f"""
        <tr>
          <td>{p.sku}</td>
          <td>{p.name}</td>
          <td>{p.stock}</td>
          <td>{p.reorder_threshold}</td>
          <td>
            <a class="btn btn-sm btn-success" href="{url_for('adjust_stock', product_id=p.id)}">Adjust</a>
            <a class="btn btn-sm btn-secondary" href="{url_for('edit_product', product_id=p.id)}">Edit</a>
          </td>
        </tr>
        """ for p in items]) or "<tr><td colspan='5'>No low-stock items</td></tr>"
    body = f"""
    <div class="d-flex justify-content-between mb-3">
      <h3>Low-stock items</h3><a class="btn btn-outline-primary" href="{url_for('index')}">Back</a>
    </div>
    <table class="table table-bordered">
      <thead><tr><th>SKU</th><th>Name</th><th>Stock</th><th>Threshold</th><th>Actions</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """
    return render_template_string(BASE_HTML, body=body)

# ----------------------
# CSV Export with Comparison
# ----------------------
LAST_CSV_PATH = "last_inventory.csv"


@app.route("/export_csv")
def export_csv():
    """Generate a new CSV safely and compare with last export."""
    products = Product.query.all()
    csv_filename = "inventory.csv"
    temp_filename = "inventory_temp.csv"

    # ✅ Write to a temporary file first
    with open(temp_filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["SKU", "Name", "Stock", "Price"])
        for p in products:
            writer.writerow([p.sku, p.name, p.stock, p.price])

    # ✅ Replace old file safely, handle if open in Excel
    try:
        os.replace(temp_filename, csv_filename)
    except PermissionError:
        os.remove(temp_filename)  # clean temp file
        return """
        <h3>⚠️ Cannot update CSV</h3>
        <p>The file might be open in Excel or another program.<br>
        Please close it and try again.</p>
        <a class="btn btn-secondary" href="/">🔙 Back</a>
        """

    # ✅ Compare with last export
    comparison_result = ""
    if os.path.exists(LAST_CSV_PATH):
        with open(LAST_CSV_PATH, "r") as old_file:
            old_csv = old_file.read()
        with open(csv_filename, "r") as new_file:
            new_csv = new_file.read()

        if new_csv == old_csv:
            comparison_result = "✅ No changes since last export."
        else:
            comparison_result = "🔄 Changes detected! (CSV updated)"
    else:
        comparison_result = "✅ First CSV export created!"

    # ✅ Save as reference for next time
    with open(LAST_CSV_PATH, "w") as last_file:
        last_file.write(open(csv_filename).read())

    return f"""
    <h3>CSV Exported Successfully!</h3>
    <p>{comparison_result}</p>
    <a class="btn btn-primary" href="/download_latest_csv">📥 Download CSV</a>
    <a class="btn btn-secondary" href="/">🏠 Back to Dashboard</a>
    """

# =======================
# DOWNLOAD LATEST CSV
# =======================

@app.route("/download_latest_csv")
def download_latest_csv():
    export_dir = os.path.join(os.getcwd(), "exports")
    os.makedirs(export_dir, exist_ok=True)

    csv_files = sorted(
        [f for f in os.listdir(export_dir) if f.endswith(".csv")],
        reverse=True
    )

    current_data = []
    previous_data = []

    if len(csv_files) > 0:
        with open(os.path.join(export_dir, csv_files[0]), newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            current_data = list(reader)

    if len(csv_files) > 1:
        with open(os.path.join(export_dir, csv_files[1]), newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            previous_data = list(reader)

    # Build comparison CSV in memory
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Previous SKU", "Previous Name", "Previous Stock", "Previous Price",
        "Current SKU", "Current Name", "Current Stock", "Current Price",
        "Status"
    ])

    max_rows = max(len(previous_data), len(current_data))
    for i in range(max_rows):
        prev_row = previous_data[i] if i < len(previous_data) else ["", "", "", ""]
        curr_row = current_data[i] if i < len(current_data) else ["", "", "", ""]

        status = ""
        if prev_row and curr_row and len(prev_row) >= 4 and len(curr_row) >= 4:
            if prev_row != curr_row:
                if prev_row[2] != curr_row[2] or prev_row[3] != curr_row[3]:
                    status = "CHANGED"
                else:
                    status = "UPDATED"
            else:
                status = "UNCHANGED"
        elif any(curr_row):
            status = "NEW"
        elif any(prev_row):
            status = "REMOVED"

        writer.writerow(prev_row + curr_row + [status])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=compare_inventory.csv"
    return response

@app.route("/compare_csv")
def compare_csv():
    # Get the last two exported CSVs from "exports" folder
    export_dir = os.path.join(os.getcwd(), "exports")
    os.makedirs(export_dir, exist_ok=True)

    csv_files = sorted(
        [f for f in os.listdir(export_dir) if f.endswith(".csv")],
        reverse=True
    )

    # Load latest (current) CSV
    current_data = []
    if len(csv_files) > 0:
        with open(os.path.join(export_dir, csv_files[0]), newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            current_data = list(reader)

    # Load previous CSV if available
    previous_data = []
    if len(csv_files) > 1:
        with open(os.path.join(export_dir, csv_files[1]), newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            previous_data = list(reader)

    # HTML template for side-by-side tables
    html = """
    <html>
    <head>
        <title>CSV Comparison</title>
        <style>
            body { display: flex; gap: 20px; font-family: Arial, sans-serif; }
            table, th, td { border: 1px solid black; border-collapse: collapse; padding: 5px; }
            th { background-color: #f2f2f2; }
            .container { flex: 1; }
            h2 { text-align: center; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Previous CSV</h2>
            <table>
                {% for row in previous %}
                    <tr>{% for col in row %}<td>{{ col }}</td>{% endfor %}</tr>
                {% endfor %}
            </table>
        </div>
        <div class="container">
            <h2>Current CSV</h2>
            <table>
                {% for row in current %}
                    <tr>{% for col in row %}<td>{{ col }}</td>{% endfor %}</tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    """

    return render_template_string(html, previous=previous_data, current=current_data)


# =======================
# RUN APP
# =======================
if __name__ == "__main__":
    app.run(debug=True)