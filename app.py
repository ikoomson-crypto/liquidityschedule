from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pandas as pd
import os
import json
from werkzeug.utils import secure_filename
import uuid
from pathlib import Path
import tempfile

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'


# ============ DATABASE FIX FOR ONEDRIVE ============
# Create database in a local path to avoid OneDrive syncing issues
def get_database_path():
    """Get a reliable database path that works with OneDrive"""
    try:
        # Try to use a local AppData path first
        user_profile = os.environ.get('USERPROFILE', 'C:\\Users\\Default')
        local_path = Path(user_profile) / 'AppData' / 'Local' / 'PaymentScheduler'
        local_path.mkdir(parents=True, exist_ok=True)
        db_file = local_path / 'payment_system.db'

        # Test if we can write to this location
        db_file.touch(exist_ok=True)
        return str(db_file.absolute())
    except (PermissionError, OSError):
        # Fallback to temp directory
        temp_dir = Path(tempfile.gettempdir()) / 'PaymentScheduler'
        temp_dir.mkdir(parents=True, exist_ok=True)
        db_file = temp_dir / 'payment_system.db'
        return str(db_file.absolute())


# Use the reliable database path
database_path = get_database_path()
print(f"Database location: {database_path}")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ============ FOLDER CONFIGURATION ============
# Use local paths for uploads and exports
base_dir = Path(os.path.dirname(os.path.abspath(__file__)))

# Create folders in the project directory
app.config['UPLOAD_FOLDER'] = str(base_dir / 'uploads')
app.config['EXPORT_FOLDER'] = str(base_dir / 'exports')

# Create directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)


# ============ MODELS ============
class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    telephone = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    account_name = db.Column(db.String(100))
    swift_code = db.Column(db.String(20))
    bank_address = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    currency = db.Column(db.String(10), default='GHS')


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    telephone = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    account_name = db.Column(db.String(100))
    swift_code = db.Column(db.String(20))
    bank_address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    telephone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SupplierPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    payment_description = db.Column(db.String(200))
    invoice_ref = db.Column(db.String(50))
    amount = db.Column(db.Float)
    type = db.Column(db.String(20))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20))
    invoice_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship('Supplier', backref='payments')


class CustomerPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    service_description = db.Column(db.String(200))
    invoice_ref = db.Column(db.String(50))
    amount = db.Column(db.Float)
    type = db.Column(db.String(20))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20))
    invoice_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('Customer', backref='payments')


class MonthlyLiquidity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.String(20))
    year = db.Column(db.Integer)
    opening_balance = db.Column(db.Float, default=0)
    total_inflows = db.Column(db.Float, default=0)
    total_outflows = db.Column(db.Float, default=0)
    closing_balance = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============ CREATE TABLES ============
with app.app_context():
    db.create_all()

    # Create default companies if none exist
    if Company.query.count() == 0:
        company_a = Company(
            name='Company A',
            address='123 Main Street, Accra, Ghana',
            telephone='+233 20 123 4567',
            bank_name='Ghana Commercial Bank',
            account_number='1234567890',
            account_name='Company A Ltd',
            swift_code='GCBKGHAX',
            bank_address='Accra, Ghana',
            is_active=True,
            currency='GHS'
        )
        company_b = Company(
            name='Company B',
            address='456 Independence Ave, Accra, Ghana',
            telephone='+233 24 987 6543',
            bank_name='Stanbic Bank',
            account_number='0987654321',
            account_name='Company B Ltd',
            swift_code='SBICGHAX',
            bank_address='Accra, Ghana',
            is_active=False,
            currency='GHS'
        )
        db.session.add(company_a)
        db.session.add(company_b)
        db.session.commit()
        print("Default companies created successfully!")


# ============ ROUTES ============
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/companies')
def get_companies():
    companies = Company.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'address': c.address,
        'telephone': c.telephone,
        'bank_name': c.bank_name,
        'account_number': c.account_number,
        'account_name': c.account_name,
        'swift_code': c.swift_code,
        'bank_address': c.bank_address,
        'is_active': c.is_active,
        'currency': c.currency
    } for c in companies])


@app.route('/api/companies/<int:company_id>', methods=['PUT'])
def update_company(company_id):
    data = request.json
    company = Company.query.get_or_404(company_id)

    # If setting this company as active, deactivate others
    if data.get('is_active'):
        Company.query.update({Company.is_active: False})

    company.name = data.get('name', company.name)
    company.address = data.get('address', company.address)
    company.telephone = data.get('telephone', company.telephone)
    company.bank_name = data.get('bank_name', company.bank_name)
    company.account_number = data.get('account_number', company.account_number)
    company.account_name = data.get('account_name', company.account_name)
    company.swift_code = data.get('swift_code', company.swift_code)
    company.bank_address = data.get('bank_address', company.bank_address)
    company.is_active = data.get('is_active', company.is_active)
    company.currency = data.get('currency', company.currency)

    db.session.commit()
    return jsonify({'message': 'Company updated successfully'})


@app.route('/api/active-company')
def get_active_company():
    company = Company.query.filter_by(is_active=True).first()
    if company:
        return jsonify({
            'id': company.id,
            'name': company.name,
            'address': company.address,
            'telephone': company.telephone,
            'bank_name': company.bank_name,
            'account_number': company.account_number,
            'account_name': company.account_name,
            'swift_code': company.swift_code,
            'bank_address': company.bank_address,
            'currency': company.currency
        })
    return jsonify({'error': 'No active company found'}), 404


# ============ SUPPLIER ROUTES ============
@app.route('/api/suppliers', methods=['GET', 'POST'])
def handle_suppliers():
    if request.method == 'GET':
        suppliers = Supplier.query.all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'address': s.address,
            'telephone': s.telephone,
            'bank_name': s.bank_name,
            'account_number': s.account_number,
            'account_name': s.account_name,
            'swift_code': s.swift_code,
            'bank_address': s.bank_address
        } for s in suppliers])

    elif request.method == 'POST':
        data = request.json
        supplier = Supplier(
            name=data['name'],
            address=data.get('address', ''),
            telephone=data.get('telephone', ''),
            bank_name=data.get('bank_name', ''),
            account_number=data.get('account_number', ''),
            account_name=data.get('account_name', ''),
            swift_code=data.get('swift_code', ''),
            bank_address=data.get('bank_address', '')
        )
        db.session.add(supplier)
        db.session.commit()
        return jsonify({'id': supplier.id, 'message': 'Supplier added successfully'})


@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT', 'DELETE'])
def handle_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == 'PUT':
        data = request.json
        supplier.name = data.get('name', supplier.name)
        supplier.address = data.get('address', supplier.address)
        supplier.telephone = data.get('telephone', supplier.telephone)
        supplier.bank_name = data.get('bank_name', supplier.bank_name)
        supplier.account_number = data.get('account_number', supplier.account_number)
        supplier.account_name = data.get('account_name', supplier.account_name)
        supplier.swift_code = data.get('swift_code', supplier.swift_code)
        supplier.bank_address = data.get('bank_address', supplier.bank_address)
        db.session.commit()
        return jsonify({'message': 'Supplier updated successfully'})

    elif request.method == 'DELETE':
        db.session.delete(supplier)
        db.session.commit()
        return jsonify({'message': 'Supplier deleted successfully'})


# ============ CUSTOMER ROUTES ============
@app.route('/api/customers', methods=['GET', 'POST'])
def handle_customers():
    if request.method == 'GET':
        customers = Customer.query.all()
        return jsonify([{
            'id': c.id,
            'name': c.name,
            'address': c.address,
            'telephone': c.telephone
        } for c in customers])

    elif request.method == 'POST':
        data = request.json
        customer = Customer(
            name=data['name'],
            address=data.get('address', ''),
            telephone=data.get('telephone', '')
        )
        db.session.add(customer)
        db.session.commit()
        return jsonify({'id': customer.id, 'message': 'Customer added successfully'})


@app.route('/api/customers/<int:customer_id>', methods=['PUT', 'DELETE'])
def handle_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == 'PUT':
        data = request.json
        customer.name = data.get('name', customer.name)
        customer.address = data.get('address', customer.address)
        customer.telephone = data.get('telephone', customer.telephone)
        db.session.commit()
        return jsonify({'message': 'Customer updated successfully'})

    elif request.method == 'DELETE':
        db.session.delete(customer)
        db.session.commit()
        return jsonify({'message': 'Customer deleted successfully'})


# ============ SUPPLIER PAYMENT ROUTES ============
@app.route('/api/supplier-payments', methods=['GET', 'POST'])
def handle_supplier_payments():
    if request.method == 'GET':
        payments = SupplierPayment.query.all()
        return jsonify([{
            'id': p.id,
            'supplier_id': p.supplier_id,
            'supplier_name': p.supplier.name if p.supplier else '',
            'payment_description': p.payment_description,
            'invoice_ref': p.invoice_ref,
            'amount': p.amount,
            'type': p.type,
            'due_date': p.due_date.isoformat() if p.due_date else None,
            'status': p.status,
            'invoice_date': p.invoice_date.isoformat() if p.invoice_date else None
        } for p in payments])

    elif request.method == 'POST':
        data = request.json
        payment = SupplierPayment(
            supplier_id=data['supplier_id'],
            payment_description=data.get('payment_description', ''),
            invoice_ref=data.get('invoice_ref', ''),
            amount=data['amount'],
            type=data.get('type', ''),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            status=data.get('status', 'Pending'),
            invoice_date=datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
                'invoice_date') else None
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({'id': payment.id, 'message': 'Payment added successfully'})


@app.route('/api/supplier-payments/<int:payment_id>', methods=['PUT', 'DELETE'])
def handle_supplier_payment(payment_id):
    payment = SupplierPayment.query.get_or_404(payment_id)

    if request.method == 'PUT':
        data = request.json
        payment.supplier_id = data.get('supplier_id', payment.supplier_id)
        payment.payment_description = data.get('payment_description', payment.payment_description)
        payment.invoice_ref = data.get('invoice_ref', payment.invoice_ref)
        payment.amount = data.get('amount', payment.amount)
        payment.type = data.get('type', payment.type)
        payment.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get(
            'due_date') else payment.due_date
        payment.status = data.get('status', payment.status)
        payment.invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
            'invoice_date') else payment.invoice_date
        db.session.commit()
        return jsonify({'message': 'Payment updated successfully'})

    elif request.method == 'DELETE':
        db.session.delete(payment)
        db.session.commit()
        return jsonify({'message': 'Payment deleted successfully'})


# ============ CUSTOMER PAYMENT ROUTES ============
@app.route('/api/customer-payments', methods=['GET', 'POST'])
def handle_customer_payments():
    if request.method == 'GET':
        payments = CustomerPayment.query.all()
        return jsonify([{
            'id': p.id,
            'customer_id': p.customer_id,
            'customer_name': p.customer.name if p.customer else '',
            'service_description': p.service_description,
            'invoice_ref': p.invoice_ref,
            'amount': p.amount,
            'type': p.type,
            'due_date': p.due_date.isoformat() if p.due_date else None,
            'status': p.status,
            'invoice_date': p.invoice_date.isoformat() if p.invoice_date else None
        } for p in payments])

    elif request.method == 'POST':
        data = request.json
        payment = CustomerPayment(
            customer_id=data['customer_id'],
            service_description=data.get('service_description', ''),
            invoice_ref=data.get('invoice_ref', ''),
            amount=data['amount'],
            type=data.get('type', ''),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            status=data.get('status', 'Pending'),
            invoice_date=datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
                'invoice_date') else None
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({'id': payment.id, 'message': 'Payment added successfully'})


@app.route('/api/customer-payments/<int:payment_id>', methods=['PUT', 'DELETE'])
def handle_customer_payment(payment_id):
    payment = CustomerPayment.query.get_or_404(payment_id)

    if request.method == 'PUT':
        data = request.json
        payment.customer_id = data.get('customer_id', payment.customer_id)
        payment.service_description = data.get('service_description', payment.service_description)
        payment.invoice_ref = data.get('invoice_ref', payment.invoice_ref)
        payment.amount = data.get('amount', payment.amount)
        payment.type = data.get('type', payment.type)
        payment.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get(
            'due_date') else payment.due_date
        payment.status = data.get('status', payment.status)
        payment.invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
            'invoice_date') else payment.invoice_date
        db.session.commit()
        return jsonify({'message': 'Payment updated successfully'})

    elif request.method == 'DELETE':
        db.session.delete(payment)
        db.session.commit()
        return jsonify({'message': 'Payment deleted successfully'})


# ============ IMPORT/EXPORT ROUTES ============
@app.route('/api/import/<entity>', methods=['POST'])
def import_data(entity):
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        df = pd.read_excel(file)

        if entity == 'suppliers':
            for _, row in df.iterrows():
                supplier = Supplier(
                    name=row['Name'],
                    address=row.get('Address', ''),
                    telephone=row.get('Telephone', ''),
                    bank_name=row.get('Bank Name', ''),
                    account_number=row.get('Account Number', ''),
                    account_name=row.get('Account Name', ''),
                    swift_code=row.get('SWIFT Code', ''),
                    bank_address=row.get('Bank Address', '')
                )
                db.session.add(supplier)

        elif entity == 'customers':
            for _, row in df.iterrows():
                customer = Customer(
                    name=row['Name'],
                    address=row.get('Address', ''),
                    telephone=row.get('Telephone', '')
                )
                db.session.add(customer)

        elif entity == 'supplier-payments':
            for _, row in df.iterrows():
                supplier = Supplier.query.filter_by(name=row['Supplier']).first()
                if supplier:
                    payment = SupplierPayment(
                        supplier_id=supplier.id,
                        payment_description=row.get('Payment Description', ''),
                        invoice_ref=row.get('Invoice Ref', ''),
                        amount=row['Amount'],
                        type=row.get('Type', ''),
                        due_date=datetime.strptime(row['Due Date'], '%Y-%m-%d').date() if pd.notna(
                            row.get('Due Date')) else None,
                        status=row.get('Status', 'Pending'),
                        invoice_date=datetime.strptime(row['Invoice Date'], '%Y-%m-%d').date() if pd.notna(
                            row.get('Invoice Date')) else None
                    )
                    db.session.add(payment)

        elif entity == 'customer-payments':
            for _, row in df.iterrows():
                customer = Customer.query.filter_by(name=row['Customer']).first()
                if customer:
                    payment = CustomerPayment(
                        customer_id=customer.id,
                        service_description=row.get('Service Description', ''),
                        invoice_ref=row.get('Invoice Ref', ''),
                        amount=row['Amount'],
                        type=row.get('Type', ''),
                        due_date=datetime.strptime(row['Due Date'], '%Y-%m-%d').date() if pd.notna(
                            row.get('Due Date')) else None,
                        status=row.get('Status', 'Pending'),
                        invoice_date=datetime.strptime(row['Invoice Date'], '%Y-%m-%d').date() if pd.notna(
                            row.get('Invoice Date')) else None
                    )
                    db.session.add(payment)

        db.session.commit()
        return jsonify({'message': f'{entity} imported successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/export/<entity>')
def export_data(entity):
    try:
        filename = f'{entity}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)

        if entity == 'suppliers':
            suppliers = Supplier.query.all()
            data = [{
                'Name': s.name,
                'Address': s.address,
                'Telephone': s.telephone,
                'Bank Name': s.bank_name,
                'Account Number': s.account_number,
                'Account Name': s.account_name,
                'SWIFT Code': s.swift_code,
                'Bank Address': s.bank_address
            } for s in suppliers]
            df = pd.DataFrame(data)

        elif entity == 'customers':
            customers = Customer.query.all()
            data = [{
                'Name': c.name,
                'Address': c.address,
                'Telephone': c.telephone
            } for c in customers]
            df = pd.DataFrame(data)

        elif entity == 'supplier-payments':
            payments = SupplierPayment.query.all()
            data = [{
                'Supplier': p.supplier.name if p.supplier else '',
                'Payment Description': p.payment_description,
                'Invoice Ref': p.invoice_ref,
                'Amount': p.amount,
                'Type': p.type,
                'Due Date': p.due_date.isoformat() if p.due_date else '',
                'Status': p.status,
                'Invoice Date': p.invoice_date.isoformat() if p.invoice_date else ''
            } for p in payments]
            df = pd.DataFrame(data)

        elif entity == 'customer-payments':
            payments = CustomerPayment.query.all()
            data = [{
                'Customer': p.customer.name if p.customer else '',
                'Service Description': p.service_description,
                'Invoice Ref': p.invoice_ref,
                'Amount': p.amount,
                'Type': p.type,
                'Due Date': p.due_date.isoformat() if p.due_date else '',
                'Status': p.status,
                'Invoice Date': p.invoice_date.isoformat() if p.invoice_date else ''
            } for p in payments]
            df = pd.DataFrame(data)

        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/download-template/<entity>')
def download_template(entity):
    try:
        filename = f'{entity}_template.xlsx'
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)

        if entity == 'suppliers':
            columns = ['Name', 'Address', 'Telephone', 'Bank Name', 'Account Number', 'Account Name', 'SWIFT Code',
                       'Bank Address']
        elif entity == 'customers':
            columns = ['Name', 'Address', 'Telephone']
        elif entity == 'supplier-payments':
            columns = ['Supplier', 'Payment Description', 'Invoice Ref', 'Amount', 'Type', 'Due Date', 'Status',
                       'Invoice Date']
        elif entity == 'customer-payments':
            columns = ['Customer', 'Service Description', 'Invoice Ref', 'Amount', 'Type', 'Due Date', 'Status',
                       'Invoice Date']
        else:
            return jsonify({'error': 'Invalid entity'}), 400

        df = pd.DataFrame(columns=columns)
        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ============ REPORT ROUTES ============
@app.route('/api/reports/liquidity', methods=['GET'])
def get_liquidity_report():
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month')

        # Convert year to int
        try:
            year = int(year)
        except ValueError:
            year = datetime.now().year

        # Get all supplier payments for the year
        supplier_payments = SupplierPayment.query.filter(
            db.extract('year', SupplierPayment.due_date) == year
        ).all()

        # Get all customer payments for the year
        customer_payments = CustomerPayment.query.filter(
            db.extract('year', CustomerPayment.due_date) == year
        ).all()

        # Calculate monthly totals
        monthly_data = {}
        for m in range(1, 13):
            month_name = datetime(year, m, 1).strftime('%B')
            monthly_data[month_name] = {
                'month': month_name,
                'inflows': 0,
                'outflows': 0,
                'balance': 0
            }

        # Process supplier payments (outflows)
        for payment in supplier_payments:
            if payment.due_date:
                month_name = payment.due_date.strftime('%B')
                if month_name in monthly_data:
                    monthly_data[month_name]['outflows'] += payment.amount

        # Process customer payments (inflows)
        for payment in customer_payments:
            if payment.due_date:
                month_name = payment.due_date.strftime('%B')
                if month_name in monthly_data:
                    monthly_data[month_name]['inflows'] += payment.amount

        # Calculate running balance
        running_balance = 0
        for month in ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']:
            if month in monthly_data:
                running_balance += monthly_data[month]['inflows'] - monthly_data[month]['outflows']
                monthly_data[month]['balance'] = running_balance

        result = list(monthly_data.values())

        # Filter by month if specified
        if month:
            result = [r for r in result if r['month'] == month]

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ============ DATABASE INFO ROUTE (for debugging) ============
@app.route('/api/db-info')
def db_info():
    """Get database location info for debugging"""
    return jsonify({
        'database_path': database_path,
        'database_exists': os.path.exists(database_path),
        'upload_folder': app.config['UPLOAD_FOLDER'],
        'export_folder': app.config['EXPORT_FOLDER']
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print(f"PAYMENT SCHEDULE SYSTEM")
    print("=" * 60)
    print(f"Database Location: {database_path}")
    print(f"Upload Folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Export Folder: {app.config['EXPORT_FOLDER']}")
    print("=" * 60)
    print("Server running at: http://localhost:5000")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5000)