import matplotlib
matplotlib.use('Agg')

from asyncio import exceptions
import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf import FlaskForm
from sklearn.cluster import KMeans
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length
import firebase_admin
from firebase_admin import credentials, firestore, auth
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import csv
from io import StringIO, BytesIO
import base64
from datetime import datetime
import numpy as np
from collections import Counter
import random
from flask import jsonify

app = Flask(__name__)
app.secret_key = '031dbad5b2e5d0b4fa08ffc112e98621'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# Firebase setup
cred = credentials.Certificate('firebase-adminsdk.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Define User class
class User(UserMixin):
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    users_ref = db.collection('users').document(user_id)
    user_doc = users_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return User(user_id=user_data['user_id'], email=user_data['email'])
    return None

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(message='Invalid email'), Length(max=100)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, message='Password must be at least 6 characters long')])
    submit = SubmitField('Login')

@app.route('/')
def index():
    if 'user' in session and 'email' in session:
        if session['email'] == 'jolynpeh03@gmail.com':
            return redirect(url_for('admin_home'))
        elif session['email'] == 'jolynpeh03@yahoo.com':
            return redirect(url_for('owner_home'))
        else:
            return redirect(url_for('staff_home'))
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/login', methods=['POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        try:
            # Check if user exists in Firestore
            user_ref = db.collection('users').where('email', '==', email).limit(1)
            user_docs = user_ref.get()

            if not user_docs:
                flash('Login failed. User does not exist.', 'danger')
                return redirect(url_for('index'))

            user_doc = user_docs[0]
            user_data = user_doc.to_dict()
            
            if user_data.get('password') == password:
                # Log the user into session
                session['user'] = user_doc.id
                session['email'] = email

                user_obj = User(user_id=user_doc.id, email=email)
                login_user(user_obj)

                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                if email == 'jolynpeh03@gmail.com':
                    return redirect(url_for('admin_home'))
                elif email == 'jolynpeh03@yahoo.com':
                    return redirect(url_for('owner_home'))
                else:
                    return redirect(url_for('staff_home'))
            else:
                flash('Login failed. Invalid password.', 'danger')
                return redirect(url_for('index'))

        except Exception as e:
            flash('Login failed. Please check your email and password.', 'danger')
            return redirect(url_for('index'))

    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error in {field}: {error}", 'danger')
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_home():
    return render_template('admin_homepage.html')

@app.route('/owner')
@login_required
def owner_home():
    return render_template('owner_homepage.html')

@app.route('/staff')
@login_required
def staff_home():
    return render_template('staff_homepage.html')
    
def get_all_categories():
    categories_ref = db.collection('categories')
    categories = [doc.id for doc in categories_ref.stream()]
    return categories

@app.route('/categories', methods=['GET'])
def categories():
    try:
        categories = get_all_categories()

        
        return jsonify(categories)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_products_by_category(category):
    products_ref = db.collection('products').where('category', '==', category)
    products = []
    for product in products_ref.stream():
        product_data = product.to_dict()
        products.append({
            'id': product.id,
            'name': product_data['name'],
            'price': product_data['price']
        })
    return products

def get_products_grouped_by_category():
    products_ref = db.collection('products')
    products_by_category = {}
    for product in products_ref.stream():
        product_data = product.to_dict()
        category = product_data.get('category', 'Uncategorized')
        if category not in products_by_category:
            products_by_category[category] = []
        products_by_category[category].append({
            'id': product_data['id'],
            'name': product_data['name'],
            'price': product_data['price'],
            'quantity': product_data['quantity']
        })
    return products_by_category

@app.route('/admin/categories')
@login_required
def admin_categories():
    categories = get_all_categories()
    return render_template('admin_categories.html', categories=categories)

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    data = request.json
    category_name = data.get('name')
    if category_name:
        category_ref = db.collection('categories').document(category_name)
        if category_ref.get().exists:
            return jsonify({'success': False, 'message': 'Category already exists'})
        category_ref.set({'name': category_name})
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid category name'})

@app.route('/edit_category/<category_id>', methods=['PUT'])
@login_required
def edit_category(category_id):
    data = request.json
    new_name = data.get('new_name')
    if new_name:
        category_ref = db.collection('categories').document(category_id)
        if category_ref.get().exists:
            # Get the current category data
            category_data = category_ref.get().to_dict()

            # Create a new document with the updated name and the same data
            new_category_ref = db.collection('categories').document(new_name)
            new_category_ref.set({
                'name': new_name,
                # Preserve other data in the document
                **category_data
            })

            category_ref.delete()

            # Update all products associated with this category
            products_ref = db.collection('products').where('category', '==', category_id)
            for product in products_ref.stream():
                product.reference.update({'category': new_name})

            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Category not found'})
    return jsonify({'success': False, 'message': 'Invalid category name'})

@app.route('/delete_category/<category_id>', methods=['DELETE'])
@login_required
def delete_category(category_id):
    products_ref = db.collection('products').where('category', '==', category_id)
    products = products_ref.stream()
    
    for product in products:
        product.reference.delete()
    
    category_ref = db.collection('categories').document(category_id)
    category_ref.delete()
    
    return jsonify({'success': True})

@app.route('/admin/products')
@login_required
def admin_products():
    products_by_category = get_products_grouped_by_category()
    categories = get_all_categories()
    return render_template('admin_products.html', products_by_category=products_by_category, categories=categories)

def get_next_product_id():
    # Get all products and find the maximum product ID
    products_ref = db.collection('products').order_by('id', direction='DESCENDING').limit(1)
    # Default start ID
    max_id = 100  
    for product in products_ref.stream():
        product_data = product.to_dict()
        # Increase from the highest existing ID
        max_id = int(product_data['id']) + 1
    return max_id

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    data = request.json
    name = data['name']
    price = data['price']
    category = data['category']
    quantity = data['quantity']
    
    if not name or not price or not category:
        return jsonify({'success': False, 'message': 'Invalid product data'})

    products_ref = db.collection('products').where('name', '==', name).stream()
    for product in products_ref:
        product_data = product.to_dict()
        return jsonify({'success': False, 'message': f'Product already exists in category {product_data["category"]}'})

    product_id = get_next_product_id()
    
    # Create a new product in database
    product_ref = db.collection('products').document(str(product_id))
    product_ref.set({
        'id': product_id,
        'name': name,
        'price': price,
        'category': category,
        'quantity': quantity
    })

    return jsonify({'success': True, 'product_id': product_ref.id})


@app.route('/edit_product/<product_id>', methods=['PUT'])
@login_required
def edit_product(product_id):
    data = request.json

    name = data.get('name')
    price = data.get('price')
    category = data.get('category')
    quantity = data.get('quantity')
    quantity_type = data.get('quantity_type')

    if not name or not price or not category or (quantity_type == 'Fixed' and quantity is None):
        return jsonify({'success': False, 'message': 'Invalid product data. All fields are required.'}), 400

    try:
        product_ref = db.collection('products').document(product_id)
        product_doc = product_ref.get()

        if not product_doc.exists:
            return jsonify({'success': False, 'message': 'Product not found'}), 404

        existing_products = db.collection('products').where('name', '==', name).where('category', '==', category).stream()
        for existing_product in existing_products:
            if existing_product.id != product_id:
                return jsonify({'success': False, 'message': f'Product with name "{name}" already exists in category "{category}".'}), 400

        updated_product_data = {
            'name': name,
            'price': price,
            'category': category,
            'quantity': quantity if quantity_type != 'Fixed' else None,  # Store quantity only for 'Fixed'
            'quantity_type': quantity_type
        }

        product_ref.update(updated_product_data)

        return jsonify({'success': True, 'message': 'Product updated successfully'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500

@app.route('/delete_product/<product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    try:
        product_ref = db.collection('products').document(product_id)
        
        if not product_ref.get().exists:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        product_ref.delete()
        
        return jsonify({'success': True, 'message': 'Product successfully deleted'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/menu')
@login_required
def menu():
    current_date = datetime.utcnow().strftime('%d-%m-%Y')
    
    shift_ref = db.collection('shifts').document(current_date)
    shift_data = shift_ref.get().to_dict() if shift_ref.get().exists else None
    
    # Check if the shift is opened and not closed
    shift_opened = shift_data and shift_data.get('shift_opened', False)
    shift_closed = shift_data and shift_data.get('shift_closed', False)

    # Redirect to the shift register page if shift is not open
    if not shift_opened or shift_closed:
        return redirect(url_for('shift_register'))

    # Fetch the products and categories for the menu
    products_by_category = get_products_grouped_by_category()
    categories = get_all_categories()

    is_admin = session['email'] == 'jolynpeh03@gmail.com'

    return render_template('menu.html', products_by_category=products_by_category, categories=categories, is_admin=is_admin)

@app.route('/check_customer_phone', methods=['POST'])
@login_required
def check_customer_phone():
    data = request.json
    phone_number = data.get('phone_number')

    if not phone_number:
        return jsonify({'success': False, 'message': 'Phone number is required.'}), 400

    # Normalize the phone number by removing spaces, dashes, etc.
    normalized_phone_number = ''.join(filter(str.isdigit, phone_number))

    customers_ref = db.collection('customers')
    customers = customers_ref.get()

    for customer_doc in customers:
        customer_data = customer_doc.to_dict()
        stored_phone_number = customer_data.get('phone_number', '')
        
        # Normalize the stored phone number
        normalized_stored_phone_number = ''.join(filter(str.isdigit, stored_phone_number))

        # Check if the normalized stored phone number matches the input phone number
        if normalized_stored_phone_number == normalized_phone_number:
            return jsonify({'success': True, 'customer': customer_data}), 200


@app.route('/get_products/<category>')
@login_required
def get_products(category):
    products = get_products_by_category(category)
    return jsonify(products)

def get_all_payment_types():
    payment_types_ref = db.collection('payment_types')
    payment_types = [doc.id for doc in payment_types_ref.stream()]
    return payment_types

@app.route('/admin/payment_types')
@login_required
def admin_payment_types():
    payment_types = get_all_payment_types()
    return render_template('admin_payment.html', payment_types=payment_types)

# Add New Payment Type for Payment Management Page
@app.route('/add_payment_type', methods=['POST'])
@login_required
def add_payment_type():
    data = request.json
    payment_type_name = data.get('name')
    if payment_type_name:
        payment_type_ref = db.collection('payment_types').document(payment_type_name)
        if payment_type_ref.get().exists:
            return jsonify({'success': False, 'message': 'Payment type already exists'})
        payment_type_ref.set({'name': payment_type_name})
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid payment type name'})

# Edit Payment Type for Payment Management Page
@app.route('/edit_payment_type/<payment_type_id>', methods=['PUT'])
@login_required
def edit_payment_type(payment_type_id):
    data = request.json
    new_name = data.get('new_name')
    if new_name:
        payment_type_ref = db.collection('payment_types').document(payment_type_id)
        if payment_type_ref.get().exists:
            # Get the current payment type data
            payment_type_data = payment_type_ref.get().to_dict()

            new_payment_type_ref = db.collection('payment_types').document(new_name)
            new_payment_type_ref.set({
                'name': new_name,
                **payment_type_data
            })

            payment_type_ref.delete()

            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Payment type not found'})
    return jsonify({'success': False, 'message': 'Invalid payment type name'})

# Route to delete an existing payment type
@app.route('/delete_payment_type/<payment_type_id>', methods=['DELETE'])
@login_required
def delete_payment_type(payment_type_id):
    payment_type_ref = db.collection('payment_types').document(payment_type_id)
    payment_type_ref.delete()
    return jsonify({'success': True})

@app.route('/store_order_items', methods=['POST'])
@login_required
def store_order_items():
    data = request.get_json()
    order_items = data.get('order_items', [])
    total_amount = data.get('total_amount', 0)
    customer_id = data.get('customer_id', "")

    if order_items and total_amount:
        session['order_items'] = order_items
        session['total_amount'] = total_amount
        session['customer_id'] = customer_id
        session.modified = True
        return jsonify(success=True)
    else:
        return jsonify(success=False)

@app.route('/payment')
@login_required
def payment():
    if 'user' not in session:
        return redirect(url_for('index'))

    payment_types = []
    payment_types_ref = db.collection('payment_types')
    docs = payment_types_ref.stream()

    for doc in docs:
        payment_types.append(doc.to_dict().get('name'))

    total_amount = session.get('total_amount', 0)
    order_items = session.get('order_items', [])

    if not order_items or not total_amount:
        flash("No order items found. Please add items to the order.", 'danger')
        return redirect(url_for('menu'))

    return render_template('admin_payment_selection.html', payment_types=payment_types, total_amount=total_amount, order_items=order_items)

@app.route('/payment_success')
@login_required
def payment_success():
    order_items = session.get('order_items', [])
    total_amount = session.get('total_amount', 0)
    customer_id = session.get('customer_id', "")

    if not order_items or not total_amount:
        flash("No order items found. Please add items to the order.", 'danger')
        return redirect(url_for('menu'))
    
    session.pop('order_items', None)
    session.pop('total_amount', None)
    
    return render_template('payment_success.html', total_amount=total_amount, customer_id = customer_id)

@app.route('/process_payment', methods=['POST'])
@login_required
def process_payment():
    data = request.get_json()
    payment_type = data.get('payment_type')
    total_amount = data.get('total_amount')
    order_items = data.get('order_items')
    customer_id = session.get('customer_id', "")

    # Calculate the total quantity of products purchased
    total_quantity = sum(item['quantity'] for item in order_items)

    for item in order_items:
        itemID = item.get('id')
        quantity = item.get('quantity')

        if itemID:
            product_ref = db.collection('products').document(f"{itemID}")
            product = product_ref.get().to_dict()
            current_quantity = product.get('quantity', 0)

            # Calculate the new quantity
            new_quantity = current_quantity - quantity

            # Check that the new quantity is not below 0
            if new_quantity < 0:
                continue

            product_ref.update({'quantity': new_quantity})
        else:
            print("Error: Item ID is None.")

    # Get current date and month-year
    current_date = datetime.utcnow().strftime('%d-%m-%Y')
    current_month_year = datetime.utcnow().strftime('%m-%Y')

    month_year_ref = db.collection('transactions').document(current_month_year).collection(current_date)

    # Fetch the last order document to get the last order_id within the date
    last_order_doc = month_year_ref.order_by('order_id', direction=firestore.Query.DESCENDING).limit(1).stream()
    last_order_id = 0
    order_docs = month_year_ref.stream()
    for doc in order_docs:
        last_order_str = doc.to_dict().get('order_id', '0')
        # Extract the number after the underscore
        try:
            order_num = int(last_order_str.split('_')[-1])
            # Update to the maximum
            last_order_id = max(last_order_id, order_num)
        except ValueError:
            print(f"Error parsing order ID: {last_order_str}")

    # Increment order_id for the new transaction
    order_id = last_order_id + 1

    # Combine date and order_id in the format '23-10-2024_1'
    order_ref_id = f"{current_date}_{order_id}"

    user_id = current_user.id
    if user_id == 'OebEIQ7DDmUIflIHLFmbQvX0WXf1':
        user_id = 'Admin'
    elif user_id == 'n3Bl7ow1XPbS0Dhvko66gdEnkWA3':
        user_id = 'Owner'

    transaction_data = {
        'order_id': order_ref_id,
        'payment_type': payment_type,
        'total_amount': float(total_amount),
        'total_quantity': total_quantity,
        'user_id': user_id,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'status': 'Active',
        'cancellation_reason': '',
        'cancelled_by': '',
        'customer_id': customer_id,
        'order_items': order_items
    }

    transaction_ref = month_year_ref.document(order_ref_id)
    transaction_ref.set(transaction_data)

    orders_ref = db.collection('orders').document(current_date).collection('order_list').document(order_ref_id)

    orders_ref.set({
        'order_id': order_ref_id,
        'user_id': user_id,
        'payment_type': payment_type,
        'total_amount': float(total_amount),
        'total_quantity': total_quantity,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'items': order_items
    })

    # Retrieve and update customer points
    if customer_id:
        customer_ref = db.collection('customers').document(customer_id)
        customer_doc = customer_ref.get()

        if customer_doc.exists:
            current_points = customer_doc.to_dict().get('points', 0)
            # Accumulate the points with total amount
            new_points = current_points + int(float(total_amount))
            customer_ref.update({'points': new_points})

    return jsonify(success=True)

@app.route('/admin/admin_staff_management')
def admin_staff_management():
    staff_list = []
    staff_ref = db.collection('staff')
    docs = staff_ref.stream()
    for doc in docs:
        staff_data = doc.to_dict()
        staff_data['id'] = doc.id
        staff_list.append(staff_data)

    return render_template('admin_staff_management.html', staff_list=staff_list)

# Add Staff for Staff Management Page
@app.route('/admin/add_staff', methods=['POST'])
def add_staff():
    data = request.get_json()

    # Check if the staff ID already exists in the database
    id_number = data.get('id_number')
    staff_list = db.collection('staff').where('id_number', '==', id_number).get()

    if staff_list:
        return jsonify({'status': 'error', 'message': 'ID number already exists.'}), 400

    # Get the last added staff's ID to generate the new staff ID
    last_staff = db.collection('staff').order_by('staff_id', direction='DESCENDING').limit(1).get()

    if last_staff:
        last_staff_id = last_staff[0].to_dict().get('staff_id', 999)
    else:
        # Make the staff ID generating starting from 1000 if no staff in database
        last_staff_id = 999

    new_staff_id = last_staff_id + 1

    # Use the staff id as the document name
    new_staff_doc_name = str(new_staff_id)

    new_staff = {
        'staff_id': new_staff_id,
        'name': data.get('name'),
        'email': data.get('email'),
        'id_number': data.get('id_number'),
        'address': data.get('address'),
        'mobile': data.get('mobile'),
        'job_position': data.get('job_position'),
        'created_at': firestore.SERVER_TIMESTAMP
    }

    new_user = {
        'email': data.get('email'),
        'password': data.get('id_number'),
        'user_id': new_staff_id
    }

    # Store staff data using the staff id into the staff and users collection
    db.collection('staff').document(new_staff_doc_name).set(new_staff)
    db.collection('users').document(new_staff_doc_name).set(new_user)
    
    try:
        user = auth.create_user(
            # Set staff id as the Firebase user ID
            uid=str(new_staff_id),
            email=data.get('email'),
            password=data.get('id_number')
        )
        return jsonify({'status': 'success', 'auth_user_id': user.uid}), 200
    except exceptions.FirebaseError as e:
        return jsonify({'status': 'error', 'message': f'Error creating user: {str(e)}'}), 500

# Edit Staff for Staff Management Page
@app.route('/admin/edit_staff/<staff_id>', methods=['PUT'])
def edit_staff(staff_id):
    data = request.json

    if not staff_id:
        return jsonify({'status': 'error', 'message': 'Staff ID is required.'}), 400

    # Fetch the staff details from the staff collection
    staff_ref = db.collection('staff').document(staff_id)
    staff_doc = staff_ref.get()

    if not staff_doc.exists:
        return jsonify({'status': 'error', 'message': 'Staff not found.'}), 404

    # Update staff data in database
    updated_staff = {
        'name': data.get('name'),
        'email': data.get('email'),
        'id_number': data.get('id_number'),
        'address': data.get('address'),
        'mobile': data.get('mobile'),
        'job_position': data.get('job_position')
    }

    # Update the document with new data
    staff_ref.update(updated_staff)

    return jsonify({'status': 'success'}), 200


# Delete Staff for Staff Management Page
@app.route('/admin/delete_staff/<staff_id>', methods=['DELETE'])
def delete_staff(staff_id):
    if not staff_id:
        return jsonify({'status': 'error', 'message': 'Staff ID is required.'}), 400

    # Fetch the staff document from database
    staff_ref = db.collection('staff').document(staff_id)
    staff_doc = staff_ref.get()

    if not staff_doc.exists:
        return jsonify({'status': 'error', 'message': 'Staff not found.'}), 404

    # Retrieve staff email for Firebase Authentication deletion
    staff_email = staff_doc.to_dict().get('email')

    try:
        user = auth.get_user_by_email(staff_email)

        auth.delete_user(user.uid)

    except auth.UserNotFoundError:
        return jsonify({'status': 'error', 'message': 'Staff not found in Firebase Authentication.'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error deleting user from Firebase: {str(e)}'}), 500

    staff_ref.delete()

    return jsonify({'status': 'success', 'message': 'Staff successfully deleted.'}), 200

@app.route('/dashboard_data', methods=['GET'])
@login_required
def dashboard_data():
    # Get the month parameter from the request
    month_param = request.args.get('month', default="10-2024", type=str)
    transactions_ref = db.collection('transactions')

    if month_param:
        transactions_ref = transactions_ref.document(month_param)

    category_counter = Counter()

    if month_param:
        days_ref = transactions_ref.collections()

        for day in days_ref:
            orders = day.list_documents()
            for order_doc in orders:
                order_data = order_doc.get()
                if order_data.exists:
                    order_data = order_data.to_dict()
                
                    order_items = order_data.get('order_items', [])
                    status = order_data.get('status')

                    if not order_items:
                        continue

                    if status == 'Cancelled':
                        continue
                    
                    for item in order_items:
                        category = item.get('category')
                        if category:
                            category_counter[category] += 1
                        else:
                            print(f"Warning: 'category' key missing in order item: {item}")

    else:
        months = transactions_ref.list_documents()
        for month_doc in months:
            days_ref = month_doc.collections()

            for day in days_ref:
                orders = day.list_documents()
                for order_doc in orders:
                    order_data = order_doc.get()
                    if order_data.exists:
                        order_data = order_data.to_dict()

                        order_items = order_data.get('order_items', [])
                        if not order_items:
                            continue

                        for item in order_items:
                            category = item.get('category')
                            if category:
                                category_counter[category] += 1
                            else:
                                print(f"Warning: 'category' key missing in order item: {item}")

    # Transform the counter to a dictionary to send as JSON
    category_data = [{"category": k, "count": v} for k, v in category_counter.items()]
    return jsonify(category_data)

@app.route('/dashboard_payment_type', methods=['GET'])
@login_required
def dashboard_payment_type():
    # Get the month parameter from the request
    month_param = request.args.get('month', default='10-2024', type=str)
    
    transactions_ref = db.collection('transactions').document(month_param)
    days_ref = transactions_ref.collections() 

    bar_data = {}

    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            payment_type = data.get('payment_type')
            order_items = data.get('total_quantity')

            bar_data[payment_type] = bar_data.get(payment_type, 0) + order_items
    
    payment_type_data = [{"payment_type": k, "total_quantity": v} for k, v in bar_data.items()]
    return jsonify(payment_type_data)


@app.route('/dashboard_timestamps', methods=['GET'])
@login_required
def dashboard_timestamps():
    # Get the month parameter from the request
    month_param = request.args.get('month', default='10-2024', type=str)
    
    transactions_ref = db.collection('transactions').document(month_param)
    days_ref = transactions_ref.collections()

    scatter_data = []

    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            timestamp = data.get('timestamp')
            order_items = data.get('order_items', [])
            status = data.get('status')

            if status == 'Cancelled': 
                continue
            
            if timestamp and order_items:
                # Calculate decimal day (Day + fractional part based on hour and minute)
                decimal_day = timestamp.day + (timestamp.hour / 24) + (timestamp.minute / 1440)

                # Calculate decimal hour (Hour + fractional part based on minutes)
                decimal_hour = timestamp.hour + (timestamp.minute / 60)

                for item in order_items:
                    category = item.get('category', 'Unknown')

                    # Add random offsets to scatter the points
                    hour_offset = random.uniform(0, 0.4)
                    day_offset = random.uniform(0, 0.2)

                    scatter_data.append({
                        'Day': decimal_day + day_offset,
                        'Hour': decimal_hour + hour_offset,
                        'Category': category
                    })

    timestamp_data = [{"day": d['Day'], "hour": d['Hour'], "category": d['Category']} for d in scatter_data]

    return jsonify(timestamp_data)

@app.route('/dashboard_customer_loyalty', methods=['GET'])
@login_required
def dashboard_customer_loyalty():
    customer_ref = db.collection('customers')
    customers = customer_ref.list_documents()

    graph_data = []

    today = datetime.now(timezone.utc)

    for customer in customers:
        customer_data = customer.get().to_dict()
        created_at = customer_data.get('created_at')
        points = customer_data.get('points', 0)
        customer_id = customer_data.get('customer_id')
        customer_name = customer_data.get('customer_name')

        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            # Calculate days since registration
            days_registered = (today - created_at).days

            # Calculate points per month
            if days_registered > 0:
                points_per_day = points / days_registered
                
                # Ranking system
                if points > 1000:
                    rank = 'High'
                elif points > 500:
                    rank = 'Medium'
                else:
                    rank = 'Low'

                graph_data.append({
                    'days_registered': days_registered,
                    'points_per_day': points_per_day,
                    'rank': rank,
                    'customer_id': customer_id,
                    'customer_name': customer_name
                })

    customer_loyalty_data = [{"days_registered": d['days_registered'], "points_per_day": d['points_per_day'], "rank": d['rank'], 
                              "customer_id": d['customer_id'], "customer_name": d['customer_name']} for d in graph_data]
    return customer_loyalty_data

@app.route('/dashboard_sales', methods=['GET'])
@login_required
def dashboard_sales():
    # Get the month parameter from the request
    month_param = request.args.get('month', default='10-2024', type=str)

    transactions_ref = db.collection('transactions').document(month_param)
    days_ref = transactions_ref.collections()

    sales_data = {}

    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            total_amount = data.get('total_amount', 0)
            timestamp = data.get('timestamp')
            status = data.get('status') 

            if status == 'Cancelled':
                continue

            if timestamp:  
                day_key = timestamp.day

                if day_key in sales_data:
                    sales_data[day_key] += total_amount
                else:
                    sales_data[day_key] = total_amount

    sales_data = [{"day": k, "total_sales": v} for k, v in sales_data.items()]
    return jsonify(sales_data)

@app.route('/dashboard_admin_sales', methods=['GET'])
@login_required
def dashboard_admin_sales():
    # Get the month parameter from the request
    month_param = request.args.get('month', default='10-2024', type=str)

    transactions_ref = db.collection('transactions').document(month_param)
    days_ref = transactions_ref.collections() 

    staff_performance = {}

    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            staff_id = data.get('user_id')
            total_amount = data.get('total_amount', 0)
            
            if staff_id in staff_performance:
                staff_performance[staff_id] += total_amount
            else:
                staff_performance[staff_id] = total_amount

    # Prepare data for plotting
    staff_performance = [{"staff_id": k, "total_sales": v} for k, v in staff_performance.items()]
    return staff_performance

@app.route('/dashboard_sales_by_category', methods=['GET'])
@login_required
def dashboard_sales_by_category():
    # Get the month parameter from the request
    month_param = request.args.get('month', default="10-2024", type=str)
    transactions_ref = db.collection('transactions')
    
    if month_param:
        transactions_ref = transactions_ref.document(month_param)

    category_sales = {}

    if month_param:
        days_ref = transactions_ref.collections()

        for day in days_ref:
            orders = day.list_documents()
            for order_doc in orders:
                order_data = order_doc.get()
                if order_data.exists:
                    order_data = order_data.to_dict()

                    order_items = order_data.get('order_items', [])
                    status = order_data.get('status')

                    if not order_items:
                        continue

                    if status == 'Cancelled':
                        continue

                    for item in order_items:
                        category = item.get('category')
                        price = item.get('price', '0')
                        if category:
                            try:
                                category_sales[category] = category_sales.get(category, 0) + float(price)
                            except ValueError:
                                print(f"Warning: 'price' in order item is not a valid number: {price}")
                        else:
                            print(f"Warning: 'category' key missing in order item: {item}")

    # Transform the sales data to a format that can be sent as JSON
    category_data = [{"category": k, "total_sales": v} for k, v in category_sales.items()]
    
    return jsonify(category_data)


@app.route('/admin/customer_management')
@login_required
def customer_management():
    customers_ref = db.collection('customers')
    customers = [doc.to_dict() for doc in customers_ref.stream()]

    return render_template('customer_management.html', customer_list=customers)

@app.route('/admin/add_new_customer', methods=['POST'])
@login_required
def add_new_customer():
    data = request.form
    customer_name = data.get('customer_name')
    phone_number = data.get('phone_number')
    gender = data.get('gender')
    points = 0

    if not customer_name or not phone_number or not gender:
        return jsonify({'success': False, 'message': 'Invalid customer data'})

    prefix = 'M' if gender == 'Male' else 'F'

    # Get all existing customer IDs
    existing_customers = db.collection('customers').stream()
    customer_ids = [doc.id for doc in existing_customers]

    # Find the highest numeric suffix for existing IDs
    max_suffix = 0
    for customer_id in customer_ids:
        if customer_id.startswith(prefix):
            suffix = int(customer_id[1:])
            if suffix > max_suffix:
                max_suffix = suffix

    # Generate a new customer ID
    customer_id = f"{prefix}{max_suffix + 1}"

    customer_ref = db.collection('customers').document(customer_id)
    customer_ref.set({
        'customer_id': customer_id,
        'customer_name': customer_name,
        'phone_number': phone_number,
        'gender': gender,
        'points': points,
        'created_at': firestore.SERVER_TIMESTAMP
    })

    return jsonify({'success': True, 'message': 'Customer added successfully', 'customer_id': customer_id})

@app.route('/admin/edit_new_customer/<customer_id>', methods=['PUT'])
@login_required
def edit_new_customer(customer_id):
    data = request.json
    customer_name = data.get('customer_name')
    phone_number = data.get('phone_number')
    gender = data.get('gender')

    if not customer_name or not phone_number or not gender:
        return jsonify({'success': False, 'message': 'Invalid customer data'})

    customer_ref = db.collection('customers').document(customer_id)

    if not customer_ref.get().exists:
        return jsonify({'success': False, 'message': 'Customer not found'}), 404

    customer_ref.update({
        'customer_name': customer_name,
        'phone_number': phone_number,
        'gender': gender
    })

    return jsonify({'success': True, 'message': 'Customer updated successfully'})


@app.route('/admin/delete_new_customer/<customer_id>', methods=['DELETE'])
@login_required
def delete_new_customer(customer_id):
    customer_ref = db.collection('customers').document(customer_id)

    if not customer_ref.get().exists:
        return jsonify({'success': False, 'message': 'Customer not found'}), 404

    customer_ref.delete()

    return jsonify({'success': True, 'message': 'Customer deleted successfully'})

@app.route('/transactions')
@login_required
def transactions():
    return render_template('transactions.html')

@app.route('/get_transactions', methods=['GET'])
@login_required
def get_transactions():
    current_month_year = datetime.utcnow().strftime('%m-%Y')

    transactions = []

    transactions_ref = db.collection('transactions').document(current_month_year)
    collections = transactions_ref.collections()

    for collection in collections:
        docs = collection.stream()
        for doc in docs:
            transaction = doc.to_dict()
            transactions.append(transaction)

    return jsonify(transactions)

@app.route('/view_transactions')
@login_required
def view_transactions():
    months_ref = db.collection('transactions')
    month_docs = months_ref.stream()

    transactions_data = []
    
    for month_doc in month_docs:
        month_id = month_doc.id
        dates_ref = months_ref.document(month_id)
        # Get all subcollections (dates)
        date_docs = dates_ref.collections()

        for date_doc in date_docs:
            date_id = date_doc.id
            orders_ref = date_doc
            # Fetch all orders under this date
            order_docs = orders_ref.stream()

            for order_doc in order_docs:
                transaction = order_doc.to_dict()
                if transaction:
                    transaction['order_id'] = order_doc.id
                    transaction['date'] = date_id
                    transaction['month_year'] = month_id
                    
                    # Convert Firestore timestamp to a readable format
                    if 'timestamp' in transaction:
                        transaction['timestamp'] = datetime.fromtimestamp(transaction['timestamp'].timestamp())

                    transactions_data.append(transaction)

    # Sort transactions by timestamp in descending order
    transactions_data.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)

    return render_template('view_transaction.html', transactions=transactions_data)

@app.route('/view_transaction_detail/<order_id>', methods=['GET'])
@login_required
def view_transaction_detail(order_id):
    # Split the order_id to get the date and order number
    date_order_parts = order_id.split('_')
    # Date in day-month-year
    date = date_order_parts[0]
    # Get order number
    order_number = date_order_parts[1]

    # Current month and year (based on the date of the transaction)
    # Extract 'month-year' from 'day-month-year'
    month_year = '-'.join(date.split('-')[1:])

    transaction_ref = db.collection('transactions').document(month_year).collection(date).document(order_id)
    transaction_doc = transaction_ref.get()

    if transaction_doc.exists:
        transaction_data = transaction_doc.to_dict()
        transaction_data['order_id'] = order_id

        if 'timestamp' in transaction_data:
            transaction_data['timestamp'] = datetime.fromtimestamp(transaction_data['timestamp'].timestamp())

        return render_template('view_transaction_detail.html', transaction=transaction_data)
    else:
        return "Transaction not found", 404

@app.route('/cancel_order/<order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    cancellation_reason = request.form.get('reason')

    try:
        # Extract date (day-month-year)
        day_month_year = order_id.split('_')[0]
        day, month, year = day_month_year.split('-')
        month_year = f"{month}-{year}"

        user_id = current_user.id

        if user_id == 'OebEIQ7DDmUIflIHLFmbQvX0WXf1':
            user_id = 'Admin'
        elif user_id == 'n3Bl7ow1XPbS0Dhvko66gdEnkWA3':
            user_id = 'Owner'
        else:
            user_id = user_id

        transaction_ref = db.collection('transactions').document(f'{month_year}').collection(f'{day_month_year}').document(f'{order_id}')
        transaction_doc = transaction_ref.get()
        
        if transaction_doc.exists:
            customer_id = transaction_doc.to_dict().get('customer_id', None)
            total_amount = transaction_doc.to_dict().get('total_amount', 0)

            customer_ref = db.collection('customers').document(customer_id)
            customer_doc = customer_ref.get()

            if customer_doc.exists:
                current_points = customer_doc.to_dict().get('points', 0)
                new_points = current_points - int(float(total_amount))
                customer_ref.update({'points': new_points})
            
            transaction_ref.update({
                'status': 'Cancelled',
                'cancelled_by': user_id,
                'cancellation_reason': cancellation_reason
            })

            flash('The order has been cancelled successfully.', 'success')
        else:
            flash('Error: The transaction was not found.', 'error')

    except Exception as e:
        flash(f'An error occurred while cancelling the order: {str(e)}', 'error')

    return redirect(url_for('view_transaction_detail', order_id=order_id))

import pytz

@app.route('/shift_register', methods=['GET', 'POST'])
@login_required
def shift_register():
    # Set local timezone
    local_tz = pytz.timezone('Asia/Kuala_Lumpur')

    # Generate the current date in day-month-year format
    current_date = datetime.utcnow().strftime('%d-%m-%Y')

    shift_ref = db.collection('shifts').document(current_date)
    shift_data = shift_ref.get().to_dict() if shift_ref.get().exists else None

    # Determine if shift is opened and/or closed
    shift_opened = shift_data and shift_data.get('shift_opened', False)
    shift_closed = shift_data and shift_data.get('shift_closed', False)

    # Convert timestamps to local timezone if they exist
    if shift_data:
        if 'open_timestamp' in shift_data:
            open_timestamp_utc = shift_data['open_timestamp']
            shift_data['open_timestamp'] = open_timestamp_utc.astimezone(local_tz)

        if 'close_timestamp' in shift_data:
            close_timestamp_utc = shift_data['close_timestamp']
            shift_data['close_timestamp'] = close_timestamp_utc.astimezone(local_tz)

    return render_template('shift_register.html', shift_data=shift_data, shift_opened=shift_opened, shift_closed=shift_closed)

@app.route('/open_shift', methods=['POST'])
@login_required
def open_shift():
    user_id = current_user.id

    if user_id == 'OebEIQ7DDmUIflIHLFmbQvX0WXf1':
        user_id = 'Admin'
    elif user_id == 'n3Bl7ow1XPbS0Dhvko66gdEnkWA3':
        user_id = 'Owner'
    else:
        user_id = user_id

    open_amount = request.form.get('open_amount')

    shift_data = {
        'open_amount': float(open_amount),
        'open_timestamp': datetime.utcnow(),
        'shift_opened_by': user_id,
        'shift_opened': True,
        'shift_closed': False
    }

    current_date = datetime.utcnow().strftime('%d-%m-%Y')

    db.collection('shifts').document(current_date).set(shift_data)

    return redirect(url_for('shift_register'))

@app.route('/close_shift', methods=['POST'])
@login_required
def close_shift():
    user_id = current_user.id

    if user_id == 'OebEIQ7DDmUIflIHLFmbQvX0WXf1':
        user_id = 'Admin'
    elif user_id == 'n3Bl7ow1XPbS0Dhvko66gdEnkWA3':
        user_id = 'Owner'
    else:
        user_id = user_id

    close_amount = request.form.get('close_amount')

    current_date = datetime.utcnow().strftime('%d-%m-%Y')

    shift_ref = db.collection('shifts').document(current_date)
    shift_data = shift_ref.get().to_dict()

    shift_data.update({
        'close_amount': float(close_amount),
        'close_timestamp': datetime.utcnow(),
        'shift_closed_by': user_id,
        'shift_closed': True
    })

    shift_ref.update(shift_data)

    return redirect(url_for('shift_register'))

@app.route('/export_transactions', methods=['GET'])
@login_required
def export_transactions():
    transactions_ref = db.collection('transactions')
    months = transactions_ref.stream()

    transaction_list = []

    user_id = current_user.id
    if user_id == 'OebEIQ7DDmUIflIHLFmbQvX0WXf1':
        user_id = 'Admin'
    elif user_id == 'n3Bl7ow1XPbS0Dhvko66gdEnkWA3':
        user_id = 'Owner'

    # Iterate through months and days
    for month in months:
        month_year = month.id
        days_ref = transactions_ref.document(month_year).collections()
        
        for day in days_ref:
            day_ref = db.collection('transactions').document(month_year).collection(day.id)
            orders = day_ref.stream()
            
            for order in orders:
                data = order.to_dict()
                
                transaction_id = order.id
                payment_type = data.get('payment_type', 'N/A')
                total_amount = data.get('total_amount', 0)
                order_items = data.get('order_items', [])
                timestamp = data.get('timestamp')
                
                # Convert timestamp to a string if available
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else ''

                transaction_list.append({
                    'Transaction ID': transaction_id,
                    'Payment Type': payment_type,
                    'Total Amount': total_amount,
                    'Order Items': order_items,
                    'User ID': data.get('user_id', 'Unknown'),
                    'Timestamp': timestamp_str
                })

    # Create an in-memory CSV file
    csv_file = StringIO()
    csv_writer = csv.DictWriter(csv_file, fieldnames=['Transaction ID', 'Payment Type', 'Total Amount', 'Order Items', 'User ID', 'Timestamp'])

    # Write the header
    csv_writer.writeheader()

    # Write transaction data to CSV
    for transaction in transaction_list:
        csv_writer.writerow(transaction)

    csv_file.seek(0)

    # Perform clustering analysis and save the plot as a base64-encoded string
    clustering_image = perform_clustering_and_plot(csv_file)

    # Generate month hour graph
    month_hour_graph = generate_month_hour_graph(db)

    moneypermonth_dayspent_graph = generate_moneypermonth_daysspent_graph(db)

    sales_month_graph = generate_sales_month(db)

    # Generate the product category sales graph
    category_sales_image = generate_category_sales_graph(db)

    # Generate the payment type graph
    payment_type_image = generate_payment_type_graph(db)

    # Generate the staff performance graph
    staff_performance_image = generate_staff_performance_graph(db)

    # Generate the customer loyalty graph
    loyalty_data = fetch_customer_loyalty_data()

    # Render the dashboard HTML with the generated images
    return render_template(
        'dashboard.html', 
        clustering_image=clustering_image, 
        category_sales_image=category_sales_image, 
        payment_type_image=payment_type_image, 
        staff_performance_image=staff_performance_image,
        month_hour_graph = month_hour_graph,
        moneypermonth_dayspent_graph = moneypermonth_dayspent_graph,
        sales_month_graph = sales_month_graph,
        loyalty_data = loyalty_data
    )

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def fetch_customer_loyalty_data():
    customer_ref = db.collection('customers')
    customers = customer_ref.list_documents()

    graph_data = []
    today = datetime.now(timezone.utc)

    for customer in customers:
        customer_data = customer.get().to_dict()
        created_at = customer_data.get('created_at')
        points = customer_data.get('points', 0)

        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            days_registered = (today - created_at).days

            if days_registered > 0:
                points_per_day = points / days_registered
                
                rank = 'High' if points > 1000 else 'Medium' if points > 500 else 'Low'

                graph_data.append({
                    'days_registered': days_registered,
                    'points_per_day': points_per_day,
                    'total_points': points,
                    'loyalty': 1 if points > 1000 else 0
                })

    df = pd.DataFrame(graph_data)

    X = df[['days_registered', 'points_per_day', 'total_points']]
    y = df['loyalty']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Train Random Forest model
    model = RandomForestClassifier(random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)

    days_registered = 30
    points_per_day = 100
    total_points = 500

    # Prepare input data for the model
    input_data = pd.DataFrame({
        'days_registered': [days_registered],
        'points_per_day': [points_per_day],
        'total_points': [total_points]
    })

    prediction = model.predict(input_data)

def generate_sales_month(db):
    transactions_ref = db.collection('transactions').document('10-2024')
    days_ref = transactions_ref.collections() 

    sales_data = {}

    for day in days_ref:
        orders = day.stream()  
        for order in orders:
            data = order.to_dict()  
            total_amount = data.get('total_amount', 0)
            timestamp = data.get('timestamp')  

            if timestamp:  
                day_key = timestamp.day

                # Accumulate sales for each day
                if day_key in sales_data:
                    sales_data[day_key] += total_amount
                else:
                    sales_data[day_key] = total_amount


from datetime import datetime, timezone
from collections import defaultdict

def generate_moneypermonth_daysspent_graph(db):
    customer_ref = db.collection('customers')
    customers = customer_ref.list_documents()

    graph_data = []

    # Get the current date
    today = datetime.now(timezone.utc)

    for customer in customers:
        customer_data = customer.get().to_dict()
        created_at = customer_data.get('created_at')
        points = customer_data.get('points', 0)

        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            # Calculate days since registration
            days_registered = (today - created_at).days

            # Calculate points per month
            if days_registered > 0:
                points_per_day = points / days_registered
                
                # Ranking system
                if points > 1000:
                    rank = 'High'
                elif points > 500:
                    rank = 'Medium'
                else:
                    rank = 'Low'

                # Prepare data for the graph
                graph_data.append({
                    'days_registered': days_registered,
                    'points_per_day': points_per_day,
                    'rank': rank
                })

    return graph_data

def generate_month_hour_graph(db):
    transactions_ref = db.collection('transactions').document('10-2024')
    days_ref = transactions_ref.collections()

    scatter_data = []

    # Iterate over each day collection
    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            timestamp = data.get('timestamp')
            order_items = data.get('order_items', [])

            if timestamp and order_items:
                # Calculate decimal day (Day + fractional part based on hour and minute)
                decimal_day = timestamp.day + (timestamp.hour / 24) + (timestamp.minute / 1440)

                # Calculate decimal hour (Hour + fractional part based on minutes)
                decimal_hour = timestamp.hour + (timestamp.minute / 60)

                # Append to scatter data for each order item category
                for item in order_items:
                    category = item.get('category', 'Unknown')
                    
                    # Add random offsets to scatter the points
                    hour_offset = random.uniform(-0.5, 0.5)
                    day_offset = random.uniform(-0.25, 0.25)
                    
                    scatter_data.append({
                        'Day': decimal_day + day_offset,
                        'Hour': decimal_hour + hour_offset,
                        'Category': category
                    })

    timestamp_data = [{"day": d['Day'], "hour": d['Hour'], "category": d['Category']} for d in scatter_data]
    return timestamp_data

def generate_staff_performance_graph(db):
    transactions_ref = db.collection('transactions').document('10-2024')
    days_ref = transactions_ref.collections()
    
    staff_performance = {}

    # Iterate over each day collection
    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            staff_id = data.get('user_id')
            total_amount = data.get('total_amount', 0)

            # Update the total amount for each unique staff ID
            if staff_id in staff_performance:
                staff_performance[staff_id] += total_amount
            else:
                staff_performance[staff_id] = total_amount

    return staff_performance

def generate_payment_type_graph(db):
    # Get the month parameter from the request
    month_param = request.args.get('month', default='10-2024', type=str)
    
    transactions_ref = db.collection('transactions').document(month_param)
    days_ref = transactions_ref.collections() 

    bar_data = {}

    # Iterate over each day collection
    for day in days_ref:
        orders = day.stream()
        for order in orders:
            data = order.to_dict()
            payment_type = data.get('payment_type')
            order_items = data.get('total_quantity')

            bar_data[payment_type] = bar_data.get(payment_type, 0) + order_items
    
    payment_type_data = [{"payment_type": k, "total_quantity": v} for k, v in bar_data.items()]
    return payment_type_data

def generate_category_sales_graph(db):
    # Get the month parameter from the request
    month_param = request.args.get('month', default="10-2024", type=str)
    transactions_ref = db.collection('transactions')
    
    # If month_param is provided, filter by that month
    if month_param:
        transactions_ref = transactions_ref.document(month_param)

    # Use defaultdict to store sales totals by category, initializing missing keys with 0
    category_sales = {}

    # If a specific month was selected, get the days in that month
    if month_param:
        days_ref = transactions_ref.collections()

        for day in days_ref:
            orders = day.list_documents()
            for order_doc in orders:
                order_data = order_doc.get()
                if order_data.exists:
                    order_data = order_data.to_dict()

                    order_items = order_data.get('order_items', [])
                    if not order_items:
                        continue

                    for item in order_items:
                        category = item.get('category')
                        price = item.get('price', '0')
                        if category:
                            try:
                                category_sales[category] = category_sales.get(category, 0) + float(price)
                            except ValueError:
                                print(f"Warning: 'price' in order item is not a valid number: {price}")
                        else:
                            print(f"Warning: 'category' key missing in order item: {item}")

    # Transform the sales data to a format that can be sent as JSON
    category_data = [{"category": k, "total_sales": v} for k, v in category_sales.items()]
    return jsonify(category_data)

def perform_clustering_and_plot(db):
    transactions_ref = db.collection('transactions')
    months = transactions_ref.list_documents()

    category_counts = {}

    for month in months:
        days_ref = transactions_ref.document(month.id).collections()

        for day in days_ref:
            day_ref = db.collection('transactions').document(month.id).collection(day.id)
            orders = day_ref.stream()

            for order in orders:
                order_data = order.to_dict()

                if not order_data:
                    continue

                order_items = order_data.get('order_items', [])
                if not order_items:
                    continue

                # Count each category occurrence
                for item in order_items:
                    category = item.get('category')
                    if category:
                        category_counts[category] = category_counts.get(category, 0) + 1
                    else:
                        print(f"    Warning: 'category' key missing in order item: {item}")

    if not category_counts:
        return None

    # Prepare the data for clustering
    data = pd.DataFrame(list(category_counts.items()), columns=['Category', 'Frequency'])
    X = data[['Frequency']].values  # Use only the frequency for clustering

    # Verify if X contains data
    if X.size == 0:
        print("Error: No data available for clustering.")
    else:
        # Determine the number of unique frequencies for clustering
        unique_frequencies = np.unique(X).size
        n_clusters = min(3, unique_frequencies)

        if unique_frequencies < 2:
            image_data = None
        else:
            try:
                # Perform KMeans clustering
                kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(X)
                data['Cluster'] = kmeans.labels_
                
                # Plot the clusters
                plt.figure(figsize=(10, 6))
                colors = ['red', 'blue', 'green']
                for i in range(n_clusters):
                    cluster_data = data[data['Cluster'] == i]
                    plt.scatter(cluster_data['Category'], cluster_data['Frequency'], 
                                label=f'Cluster {i+1}', color=colors[i])

                plt.xlabel('Product Category')
                plt.ylabel('Purchase Frequency')
                plt.title('Product Category Clustering by Purchase Frequency')
                plt.xticks(rotation=45)
                plt.legend()

                # Save the plot to a PNG image in-memory and encode it as base64
                image_io = BytesIO()
                plt.savefig(image_io, format='png')
                image_io.seek(0)
                image_base64 = base64.b64encode(image_io.read()).decode('utf-8')
                plt.close()

                image_data = f"data:image/png;base64,{image_base64}"
                return image_data

            
            except ValueError as e:
                print(f"Clustering Error: {e}")
                image_data = None
    return image_data

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', clustering_image=None)

if __name__ == '__main__':
    app.run(debug=True)
