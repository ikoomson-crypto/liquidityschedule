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
import re
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'


# ============ DATABASE FIX FOR ONEDRIVE ============
def get_database_path():
    """Get a reliable database path that works with OneDrive"""
    try:
        user_profile = os.environ.get('USERPROFILE', 'C:\\Users\\Default')
        local_path = Path(user_profile) / 'AppData' / 'Local' / 'PaymentScheduler'
        local_path.mkdir(parents=True, exist_ok=True)
        db_file = local_path / 'payment_system.db'
        db_file.touch(exist_ok=True)
        return str(db_file.absolute())
    except (PermissionError, OSError):
        temp_dir = Path(tempfile.gettempdir()) / 'PaymentScheduler'
        temp_dir.mkdir(parents=True, exist_ok=True)
        db_file = temp_dir / 'payment_system.db'
        return str(db_file.absolute())


database_path = get_database_path()
print(f"Database location: {database_path}")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ============ FOLDER CONFIGURATION ============
base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
app.config['UPLOAD_FOLDER'] = str(base_dir / 'uploads')
app.config['EXPORT_FOLDER'] = str(base_dir / 'exports')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)


# ============ HELPER FUNCTIONS ============
def format_currency(amount):
    """Format amount with comma separators"""
    if amount is None:
        return '0.00'
    return f"{amount:,.2f}"


def parse_currency(amount_str):
    """Parse currency string with commas back to float"""
    if not amount_str:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', str(amount_str))
    return float(cleaned) if cleaned else 0.0


def parse_date(date_value):
    """Parse date from various formats"""
    if pd.isna(date_value) or date_value is None:
        return None

    if isinstance(date_value, (datetime, pd.Timestamp)):
        return date_value.date() if hasattr(date_value, 'date') else date_value

    if isinstance(date_value, str):
        date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%b %d, %Y', '%B %d, %Y']
        for fmt in date_formats:
            try:
                return datetime.strptime(date_value.strip(), fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromordinal(int(float(date_value)) - 693594).date()
        except:
            pass

    return None


def get_active_company_id():
    """Get the ID of the currently active company"""
    company = Company.query.filter_by(is_active=True).first()
    return company.id if company else None


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
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    telephone = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    account_name = db.Column(db.String(100))
    swift_code = db.Column(db.String(20))
    bank_address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref='suppliers')


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    telephone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref='customers')


class SupplierPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
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
    company = db.relationship('Company', backref='supplier_payments')


class CustomerPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
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
    company = db.relationship('Company', backref='customer_payments')


class MonthlyLiquidity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    month = db.Column(db.String(20))
    year = db.Column(db.Integer)
    opening_balance = db.Column(db.Float, default=0)
    total_inflows = db.Column(db.Float, default=0)
    total_outflows = db.Column(db.Float, default=0)
    closing_balance = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship('Company', backref='liquidity')


# ============ CREATE TABLES ============
with app.app_context():
    db.create_all()

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


# ============ COMPANY ROUTES ============
@app.route('/api/companies', methods=['GET'])
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


@app.route('/api/companies', methods=['POST'])
def create_company():
    data = request.json

    existing = Company.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': 'Company with this name already exists'}), 400

    company = Company(
        name=data['name'],
        address=data.get('address', ''),
        telephone=data.get('telephone', ''),
        bank_name=data.get('bank_name', ''),
        account_number=data.get('account_number', ''),
        account_name=data.get('account_name', ''),
        swift_code=data.get('swift_code', ''),
        bank_address=data.get('bank_address', ''),
        is_active=data.get('is_active', False),
        currency=data.get('currency', 'GHS')
    )

    db.session.add(company)
    db.session.commit()

    return jsonify({
        'id': company.id,
        'message': 'Company created successfully'
    })


@app.route('/api/companies/<int:company_id>', methods=['GET'])
def get_company(company_id):
    company = Company.query.get_or_404(company_id)
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
        'is_active': company.is_active,
        'currency': company.currency
    })


@app.route('/api/companies/<int:company_id>', methods=['PUT'])
def update_company(company_id):
    data = request.json
    company = Company.query.get_or_404(company_id)

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


@app.route('/api/companies/<int:company_id>', methods=['DELETE'])
def delete_company(company_id):
    company = Company.query.get_or_404(company_id)

    if Company.query.count() <= 1:
        return jsonify({'error': 'Cannot delete the only company'}), 400

    if company.is_active:
        return jsonify({'error': 'Cannot delete the active company. Please switch to another company first.'}), 400

    db.session.delete(company)
    db.session.commit()

    return jsonify({'message': 'Company deleted successfully'})


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
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    if request.method == 'GET':
        suppliers = Supplier.query.filter_by(company_id=company_id).all()
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
            company_id=company_id,
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


@app.route('/api/suppliers/<int:supplier_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_supplier(supplier_id):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()

    if request.method == 'GET':
        return jsonify({
            'id': supplier.id,
            'name': supplier.name,
            'address': supplier.address,
            'telephone': supplier.telephone,
            'bank_name': supplier.bank_name,
            'account_number': supplier.account_number,
            'account_name': supplier.account_name,
            'swift_code': supplier.swift_code,
            'bank_address': supplier.bank_address
        })

    elif request.method == 'PUT':
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


# ============ MULTIPLE DELETE FOR SUPPLIERS ============
@app.route('/api/suppliers/delete-multiple', methods=['POST'])
def delete_multiple_suppliers():
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    data = request.json
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400

    try:
        deleted_count = Supplier.query.filter(Supplier.id.in_(ids), Supplier.company_id == company_id).delete(
            synchronize_session=False)
        db.session.commit()
        return jsonify({
            'message': f'Successfully deleted {deleted_count} supplier(s)',
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


# ============ CUSTOMER ROUTES ============
@app.route('/api/customers', methods=['GET', 'POST'])
def handle_customers():
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    if request.method == 'GET':
        customers = Customer.query.filter_by(company_id=company_id).all()
        return jsonify([{
            'id': c.id,
            'name': c.name,
            'address': c.address,
            'telephone': c.telephone
        } for c in customers])

    elif request.method == 'POST':
        data = request.json
        customer = Customer(
            company_id=company_id,
            name=data['name'],
            address=data.get('address', ''),
            telephone=data.get('telephone', '')
        )
        db.session.add(customer)
        db.session.commit()
        return jsonify({'id': customer.id, 'message': 'Customer added successfully'})


@app.route('/api/customers/<int:customer_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_customer(customer_id):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    customer = Customer.query.filter_by(id=customer_id, company_id=company_id).first_or_404()

    if request.method == 'GET':
        return jsonify({
            'id': customer.id,
            'name': customer.name,
            'address': customer.address,
            'telephone': customer.telephone
        })

    elif request.method == 'PUT':
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
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    if request.method == 'GET':
        payments = SupplierPayment.query.filter_by(company_id=company_id).all()
        return jsonify([{
            'id': p.id,
            'supplier_id': p.supplier_id,
            'supplier_name': p.supplier.name if p.supplier else '',
            'payment_description': p.payment_description,
            'invoice_ref': p.invoice_ref,
            'amount': p.amount,
            'amount_formatted': format_currency(p.amount),
            'type': p.type,
            'due_date': p.due_date.isoformat() if p.due_date else None,
            'status': p.status,
            'invoice_date': p.invoice_date.isoformat() if p.invoice_date else None
        } for p in payments])

    elif request.method == 'POST':
        data = request.json
        amount = parse_currency(data.get('amount', 0))

        payment = SupplierPayment(
            company_id=company_id,
            supplier_id=data['supplier_id'],
            payment_description=data.get('payment_description', ''),
            invoice_ref=data.get('invoice_ref', ''),
            amount=amount,
            type=data.get('type', ''),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            status=data.get('status', 'Pending'),
            invoice_date=datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
                'invoice_date') else None
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({'id': payment.id, 'message': 'Payment added successfully'})


@app.route('/api/supplier-payments/<int:payment_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_supplier_payment(payment_id):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    payment = SupplierPayment.query.filter_by(id=payment_id, company_id=company_id).first_or_404()

    if request.method == 'GET':
        return jsonify({
            'id': payment.id,
            'supplier_id': payment.supplier_id,
            'supplier_name': payment.supplier.name if payment.supplier else '',
            'payment_description': payment.payment_description,
            'invoice_ref': payment.invoice_ref,
            'amount': payment.amount,
            'type': payment.type,
            'due_date': payment.due_date.isoformat() if payment.due_date else None,
            'status': payment.status,
            'invoice_date': payment.invoice_date.isoformat() if payment.invoice_date else None
        })

    elif request.method == 'PUT':
        data = request.json
        payment.supplier_id = data.get('supplier_id', payment.supplier_id)
        payment.payment_description = data.get('payment_description', payment.payment_description)
        payment.invoice_ref = data.get('invoice_ref', payment.invoice_ref)
        payment.amount = parse_currency(data.get('amount', payment.amount))
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


# ============ MULTIPLE DELETE FOR SUPPLIER PAYMENTS ============
@app.route('/api/supplier-payments/delete-multiple', methods=['POST'])
def delete_multiple_supplier_payments():
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    data = request.json
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400

    try:
        deleted_count = SupplierPayment.query.filter(
            SupplierPayment.id.in_(ids),
            SupplierPayment.company_id == company_id
        ).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({
            'message': f'Successfully deleted {deleted_count} supplier payment(s)',
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


# ============ CUSTOMER PAYMENT ROUTES ============
@app.route('/api/customer-payments', methods=['GET', 'POST'])
def handle_customer_payments():
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    if request.method == 'GET':
        payments = CustomerPayment.query.filter_by(company_id=company_id).all()
        return jsonify([{
            'id': p.id,
            'customer_id': p.customer_id,
            'customer_name': p.customer.name if p.customer else '',
            'service_description': p.service_description,
            'invoice_ref': p.invoice_ref,
            'amount': p.amount,
            'amount_formatted': format_currency(p.amount),
            'type': p.type,
            'due_date': p.due_date.isoformat() if p.due_date else None,
            'status': p.status,
            'invoice_date': p.invoice_date.isoformat() if p.invoice_date else None
        } for p in payments])

    elif request.method == 'POST':
        data = request.json
        amount = parse_currency(data.get('amount', 0))

        payment = CustomerPayment(
            company_id=company_id,
            customer_id=data['customer_id'],
            service_description=data.get('service_description', ''),
            invoice_ref=data.get('invoice_ref', ''),
            amount=amount,
            type=data.get('type', ''),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            status=data.get('status', 'Pending'),
            invoice_date=datetime.strptime(data['invoice_date'], '%Y-%m-%d').date() if data.get(
                'invoice_date') else None
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify({'id': payment.id, 'message': 'Payment added successfully'})


@app.route('/api/customer-payments/<int:payment_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_customer_payment(payment_id):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    payment = CustomerPayment.query.filter_by(id=payment_id, company_id=company_id).first_or_404()

    if request.method == 'GET':
        return jsonify({
            'id': payment.id,
            'customer_id': payment.customer_id,
            'customer_name': payment.customer.name if payment.customer else '',
            'service_description': payment.service_description,
            'invoice_ref': payment.invoice_ref,
            'amount': payment.amount,
            'type': payment.type,
            'due_date': payment.due_date.isoformat() if payment.due_date else None,
            'status': payment.status,
            'invoice_date': payment.invoice_date.isoformat() if payment.invoice_date else None
        })

    elif request.method == 'PUT':
        data = request.json
        payment.customer_id = data.get('customer_id', payment.customer_id)
        payment.service_description = data.get('service_description', payment.service_description)
        payment.invoice_ref = data.get('invoice_ref', payment.invoice_ref)
        payment.amount = parse_currency(data.get('amount', payment.amount))
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


# ============ MULTIPLE DELETE FOR CUSTOMER PAYMENTS ============
@app.route('/api/customer-payments/delete-multiple', methods=['POST'])
def delete_multiple_customer_payments():
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    data = request.json
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400

    try:
        deleted_count = CustomerPayment.query.filter(
            CustomerPayment.id.in_(ids),
            CustomerPayment.company_id == company_id
        ).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({
            'message': f'Successfully deleted {deleted_count} customer payment(s)',
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


# ============ IMPORT ROUTES ============
@app.route('/api/import/<entity>', methods=['POST'])
def import_data(entity):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        df = pd.read_excel(file)
        print(f"Importing {entity} - Found {len(df)} rows")

        if entity == 'suppliers':
            for _, row in df.iterrows():
                supplier = Supplier(
                    company_id=company_id,
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
            db.session.commit()
            return jsonify({'message': f'{len(df)} suppliers imported successfully'})

        elif entity == 'customers':
            for _, row in df.iterrows():
                customer = Customer(
                    company_id=company_id,
                    name=row['Name'],
                    address=row.get('Address', ''),
                    telephone=row.get('Telephone', '')
                )
                db.session.add(customer)
            db.session.commit()
            return jsonify({'message': f'{len(df)} customers imported successfully'})

        elif entity == 'supplier-payments':
            imported_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    supplier_name = row.get('Supplier', '')
                    if pd.isna(supplier_name) or not supplier_name:
                        errors.append(f"Row {index + 2}: Missing supplier name")
                        continue

                    supplier = Supplier.query.filter_by(name=str(supplier_name).strip(), company_id=company_id).first()
                    if not supplier:
                        errors.append(f"Row {index + 2}: Supplier '{supplier_name}' not found")
                        continue

                    amount = parse_currency(row.get('Amount', 0))
                    due_date = parse_date(row.get('Due Date'))
                    invoice_date = parse_date(row.get('Invoice Date'))

                    if not due_date and not invoice_date:
                        today = datetime.now().date()
                        due_date = today
                        invoice_date = today
                        print(f"Row {index + 2}: No dates provided, using today's date")

                    payment = SupplierPayment(
                        company_id=company_id,
                        supplier_id=supplier.id,
                        payment_description=str(row.get('Payment Description', '')) if pd.notna(
                            row.get('Payment Description')) else '',
                        invoice_ref=str(row.get('Invoice Ref', '')) if pd.notna(row.get('Invoice Ref')) else '',
                        amount=amount,
                        type=str(row.get('Type', 'Cash')) if pd.notna(row.get('Type')) else 'Cash',
                        due_date=due_date,
                        status=str(row.get('Status', 'Pending')) if pd.notna(row.get('Status')) else 'Pending',
                        invoice_date=invoice_date
                    )
                    db.session.add(payment)
                    imported_count += 1
                    print(f"Row {index + 2}: Imported payment for {supplier_name} - Amount: {amount}, Due: {due_date}")

                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")
                    print(f"Error in row {index + 2}: {str(e)}")

            db.session.commit()

            result_message = f'Successfully imported {imported_count} supplier payment(s)'
            if errors:
                result_message += f'\nErrors: {len(errors)} rows failed'
                print(f"Import errors: {errors}")

            return jsonify({
                'message': result_message,
                'imported': imported_count,
                'errors': errors
            })

        elif entity == 'customer-payments':
            imported_count = 0
            errors = []

            for index, row in df.iterrows():
                try:
                    customer_name = row.get('Customer', '')
                    if pd.isna(customer_name) or not customer_name:
                        errors.append(f"Row {index + 2}: Missing customer name")
                        continue

                    customer = Customer.query.filter_by(name=str(customer_name).strip(), company_id=company_id).first()
                    if not customer:
                        errors.append(f"Row {index + 2}: Customer '{customer_name}' not found")
                        continue

                    amount = parse_currency(row.get('Amount', 0))
                    due_date = parse_date(row.get('Due Date'))
                    invoice_date = parse_date(row.get('Invoice Date'))

                    if not due_date and not invoice_date:
                        today = datetime.now().date()
                        due_date = today
                        invoice_date = today
                        print(f"Row {index + 2}: No dates provided, using today's date")

                    payment = CustomerPayment(
                        company_id=company_id,
                        customer_id=customer.id,
                        service_description=str(row.get('Service Description', '')) if pd.notna(
                            row.get('Service Description')) else '',
                        invoice_ref=str(row.get('Invoice Ref', '')) if pd.notna(row.get('Invoice Ref')) else '',
                        amount=amount,
                        type=str(row.get('Type', 'Cash')) if pd.notna(row.get('Type')) else 'Cash',
                        due_date=due_date,
                        status=str(row.get('Status', 'Pending')) if pd.notna(row.get('Status')) else 'Pending',
                        invoice_date=invoice_date
                    )
                    db.session.add(payment)
                    imported_count += 1
                    print(f"Row {index + 2}: Imported payment for {customer_name} - Amount: {amount}, Due: {due_date}")

                except Exception as e:
                    errors.append(f"Row {index + 2}: {str(e)}")
                    print(f"Error in row {index + 2}: {str(e)}")

            db.session.commit()

            result_message = f'Successfully imported {imported_count} customer payment(s)'
            if errors:
                result_message += f'\nErrors: {len(errors)} rows failed'
                print(f"Import errors: {errors}")

            return jsonify({
                'message': result_message,
                'imported': imported_count,
                'errors': errors
            })

        return jsonify({'message': f'{entity} imported successfully'})

    except Exception as e:
        db.session.rollback()
        print(f"Import error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


# ============ EXPORT ROUTES ============
@app.route('/api/export/<entity>')
def export_data(entity):
    company_id = get_active_company_id()
    if not company_id:
        return jsonify({'error': 'No active company'}), 400

    try:
        filename = f'{entity}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        filepath = os.path.join(app.config['EXPORT_FOLDER'], filename)

        if entity == 'suppliers':
            suppliers = Supplier.query.filter_by(company_id=company_id).all()
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
            customers = Customer.query.filter_by(company_id=company_id).all()
            data = [{
                'Name': c.name,
                'Address': c.address,
                'Telephone': c.telephone
            } for c in customers]
            df = pd.DataFrame(data)

        elif entity == 'supplier-payments':
            payments = SupplierPayment.query.filter_by(company_id=company_id).all()
            data = [{
                'Supplier': p.supplier.name if p.supplier else '',
                'Payment Description': p.payment_description,
                'Invoice Ref': p.invoice_ref,
                'Amount': format_currency(p.amount),
                'Type': p.type,
                'Due Date': p.due_date.isoformat() if p.due_date else '',
                'Status': p.status,
                'Invoice Date': p.invoice_date.isoformat() if p.invoice_date else ''
            } for p in payments]
            df = pd.DataFrame(data)

        elif entity == 'customer-payments':
            payments = CustomerPayment.query.filter_by(company_id=company_id).all()
            data = [{
                'Customer': p.customer.name if p.customer else '',
                'Service Description': p.service_description,
                'Invoice Ref': p.invoice_ref,
                'Amount': format_currency(p.amount),
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


# ============ CASHFLOW REPORT ROUTE ============
@app.route('/api/reports/cashflow', methods=['GET'])
def get_cashflow_report():
    try:
        company_id = get_active_company_id()
        if not company_id:
            return jsonify({'error': 'No active company'}), 400

        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        opening_balance = float(request.args.get('opening_balance', 0))

        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = datetime(datetime.now().year, 1, 1).date()

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = datetime.now().date()

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        print(f"\n{'=' * 60}")
        print(f"CASHFLOW REPORT - {start_date} to {end_date}")
        print(f"{'=' * 60}")
        print(f"Opening Balance: {opening_balance}")

        supplier_payments = SupplierPayment.query.filter(
            SupplierPayment.company_id == company_id,
            db.or_(
                db.and_(
                    SupplierPayment.due_date >= start_date,
                    SupplierPayment.due_date <= end_date
                ),
                db.and_(
                    SupplierPayment.invoice_date >= start_date,
                    SupplierPayment.invoice_date <= end_date
                )
            )
        ).all()

        customer_payments = CustomerPayment.query.filter(
            CustomerPayment.company_id == company_id,
            db.or_(
                db.and_(
                    CustomerPayment.due_date >= start_date,
                    CustomerPayment.due_date <= end_date
                ),
                db.and_(
                    CustomerPayment.invoice_date >= start_date,
                    CustomerPayment.invoice_date <= end_date
                )
            )
        ).all()

        print(f"Supplier Payments found: {len(supplier_payments)}")
        print(f"Customer Payments found: {len(customer_payments)}")

        month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        year = start_date.year

        monthly_data = {}
        for month_key in month_order:
            month_num = month_order.index(month_key) + 1
            monthly_data[month_key] = {
                'month': month_key,
                'full_month': datetime(year, month_num, 1).strftime('%B'),
                'year': year,
                'month_index': month_num,
                'opening_balance': 0,
                'inflows': 0,
                'outflows': 0,
                'net': 0,
                'closing_balance': 0,
                'inflow_items': [],
                'outflow_items': []
            }

        for payment in supplier_payments:
            date_to_use = payment.due_date if payment.due_date else payment.invoice_date
            if date_to_use:
                month_key = date_to_use.strftime('%b')
                if month_key in monthly_data:
                    monthly_data[month_key]['outflows'] += payment.amount
                    description = payment.payment_description or 'Supplier Payment'
                    monthly_data[month_key]['outflow_items'].append({
                        'description': description,
                        'supplier': payment.supplier.name if payment.supplier else 'Unknown',
                        'amount': payment.amount,
                        'date': date_to_use.isoformat(),
                        'status': payment.status or 'Pending'
                    })
                    print(
                        f"  OUTFLOW: {description} - {payment.amount} on {date_to_use.strftime('%Y-%m-%d')} -> {month_key}")

        for payment in customer_payments:
            date_to_use = payment.due_date if payment.due_date else payment.invoice_date
            if date_to_use:
                month_key = date_to_use.strftime('%b')
                if month_key in monthly_data:
                    monthly_data[month_key]['inflows'] += payment.amount
                    description = payment.service_description or 'Customer Payment'
                    monthly_data[month_key]['inflow_items'].append({
                        'description': description,
                        'customer': payment.customer.name if payment.customer else 'Unknown',
                        'amount': payment.amount,
                        'date': date_to_use.isoformat(),
                        'status': payment.status or 'Pending'
                    })
                    print(
                        f"  INFLOW: {description} - {payment.amount} on {date_to_use.strftime('%Y-%m-%d')} -> {month_key}")

        running_balance = opening_balance
        chronological_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        active_months = []
        for month_key in chronological_months:
            month_num = chronological_months.index(month_key) + 1
            month_date = datetime(year, month_num, 1).date()
            if month_date >= start_date.replace(day=1) and month_date <= end_date:
                active_months.append(month_key)

        for month_key in active_months:
            monthly_data[month_key]['opening_balance'] = running_balance
            monthly_data[month_key]['net'] = monthly_data[month_key]['inflows'] - monthly_data[month_key]['outflows']
            running_balance += monthly_data[month_key]['net']
            monthly_data[month_key]['closing_balance'] = running_balance

        result = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
            'total_inflows': sum(m['inflows'] for m in monthly_data.values()),
            'total_outflows': sum(m['outflows'] for m in monthly_data.values()),
            'total_net': sum(m['net'] for m in monthly_data.values()),
            'months': active_months,
            'monthly_data': monthly_data,
            'row_data': {
                'opening_balances': [monthly_data[m]['opening_balance'] for m in active_months],
                'inflows': [monthly_data[m]['inflows'] for m in active_months],
                'outflows': [monthly_data[m]['outflows'] for m in active_months],
                'net': [monthly_data[m]['net'] for m in active_months],
                'closing_balances': [monthly_data[m]['closing_balance'] for m in active_months]
            }
        }

        print(f"\n{'=' * 60}")
        print("CASHFLOW SUMMARY:")
        print(f"{'=' * 60}")
        print(f"Opening Balance: {opening_balance}")
        print(f"Total Inflows: {result['total_inflows']}")
        print(f"Total Outflows: {result['total_outflows']}")
        print(f"Total Net: {result['total_net']}")
        print(f"Closing Balance: {result['closing_balance']}")
        print(f"Months in report: {active_months}")
        print(f"{'=' * 60}\n")

        return jsonify(result)

    except Exception as e:
        print(f"Error in cashflow report: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


# ============ SUPPLIER PAYMENT REPORT ROUTE ============
@app.route('/api/reports/supplier-payments', methods=['GET'])
def get_supplier_payment_report():
    try:
        company_id = get_active_company_id()
        if not company_id:
            return jsonify({'error': 'No active company'}), 400

        # Get filter parameters
        supplier_id = request.args.get('supplier_id')
        status = request.args.get('status')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Build query
        query = SupplierPayment.query.filter_by(company_id=company_id)

        # Filter by supplier
        if supplier_id and supplier_id != 'all':
            query = query.filter(SupplierPayment.supplier_id == int(supplier_id))

        # Filter by status
        if status and status != 'all':
            query = query.filter(SupplierPayment.status == status)

        # Filter by date range
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(
                db.or_(
                    SupplierPayment.due_date >= start_date,
                    SupplierPayment.invoice_date >= start_date
                )
            )

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(
                db.or_(
                    SupplierPayment.due_date <= end_date,
                    SupplierPayment.invoice_date <= end_date
                )
            )

        # Get results
        payments = query.all()

        # Get all suppliers for dropdown (only for active company)
        suppliers = Supplier.query.filter_by(company_id=company_id).all()

        # Format response
        result = {
            'suppliers': [{'id': s.id, 'name': s.name} for s in suppliers],
            'payments': [{
                'id': p.id,
                'supplier_name': p.supplier.name if p.supplier else '',
                'payment_description': p.payment_description,
                'invoice_ref': p.invoice_ref,
                'amount': p.amount,
                'amount_formatted': format_currency(p.amount),
                'type': p.type,
                'due_date': p.due_date.isoformat() if p.due_date else None,
                'status': p.status,
                'invoice_date': p.invoice_date.isoformat() if p.invoice_date else None
            } for p in payments],
            'filters': {
                'supplier_id': supplier_id,
                'status': status,
                'start_date': start_date_str,
                'end_date': end_date_str
            }
        }

        print(f"Supplier Payment Report - Found {len(payments)} payments")
        return jsonify(result)

    except Exception as e:
        print(f"Error in supplier payment report: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400


# ============ DATABASE INFO ROUTE ============
@app.route('/api/db-info')
def db_info():
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