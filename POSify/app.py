from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length
import pyrebase
import firebase_admin
from firebase_admin import credentials, firestore, auth, exceptions
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

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

# Pyrebase configuration
config = {
    "apiKey": "AIzaSyDkkXRjqHCHa_Mii-mAGD_p10n73yqqBcE",
    "authDomain": "posify-14196461.firebaseapp.com",
    "databaseURL": "https://posify-14196461.firebaseio.com",
    "projectId": "posify-14196461",
    "storageBucket": "posify-14196461.appspot.com",
    "messagingSenderId": "324894573827",
    "appId": "1:324894573827:web:d82edf8c4a4b59e1541536",
    "measurementId": "G-ECPHRV2ZX9"
}
firebase = pyrebase.initialize_app(config)
firebase_auth = firebase.auth()

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
            # Pyrebase authentication instead of Firebase Admin SDK
            user = firebase_auth.sign_in_with_email_and_password(email, password)
            session['user'] = user['localId']
            session['email'] = email

            # Check if user already exists in Firestore
            user_ref = db.collection('users').document(user['localId'])
            user_doc = user_ref.get()
            if not user_doc.exists:
                # Save new user info to Firestore if not exists
                user_ref.set({
                    'user_id': user['localId'],
                    'email': email
                })

            # Log the user in via Flask-Login
            user_obj = User(user_id=user['localId'], email=email)
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
        except Exception as e:
            flash('Login failed. Please check your email and password.', 'danger')
            return redirect(url_for('index'))

    # Show form validation errors (if any)
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
            'id': product.id,
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
                'name': new_name,  # Ensure the name field inside the document is updated
                **category_data   # Preserve any other data in the document
            })

            # Delete the old category document
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
    # Fetch all products under the category
    products_ref = db.collection('products').where('category', '==', category_id)
    products = products_ref.stream()
    
    # Delete each product
    for product in products:
        product.reference.delete()
    
    # Delete the category
    category_ref = db.collection('categories').document(category_id)
    category_ref.delete()
    
    return jsonify({'success': True})

@app.route('/admin/products')
@login_required
def admin_products():
    products_by_category = get_products_grouped_by_category()
    categories = get_all_categories()
    return render_template('admin_products.html', products_by_category=products_by_category, categories=categories)

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

    # Check if the product already exists in any category
    products_ref = db.collection('products').where('name', '==', name).stream()
    for product in products_ref:
        product_data = product.to_dict()
        return jsonify({'success': False, 'message': f'Product already exists in category {product_data["category"]}'})
    
    if category == 'new-category':
        category = data['new_category']
        # Add new category to Firestore if it doesn't exist
        category_ref = db.collection('categories').document(category)
        if not category_ref.get().exists:
            category_ref.set({})

    product_ref = db.collection('products').document()
    product_ref.set({
        'name': name,
        'price': price,
        'category': category,
        'quantity': quantity
    })
    
    return jsonify({'success': True})

@app.route('/edit_product/<product_id>', methods=['PUT'])
@login_required
def edit_product(product_id):
    data = request.json
    name = data['name']
    price = data['price']
    category = data['category']
    quantity = data['quantity']

    if not name or not price or not category:
        return jsonify({'success': False, 'message': 'Invalid product data'})

    product_ref = db.collection('products').document(product_id)
    product_ref.update({
        'name': name,
        'price': price,
        'category': category,
        'quantity': quantity,
    })

    return jsonify({'success': True})

@app.route('/delete_product/<product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    try:
        db.collection('products').document(product_id).delete()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/sales')
@login_required
def sales_list():
    sales_ref = db.collection('sales')
    sales = sales_ref.stream()
    sales_list = []
    for sale in sales:
        sales_list.append(sale.to_dict())
    return render_template('sales_list.html', sales=sales_list)

@app.route('/menu')
@login_required
def menu():
    products_by_category = get_products_grouped_by_category()
    categories = get_all_categories()
    is_admin = session['email'] == 'jolynpeh03@gmail.com'
    return render_template('menu.html', products_by_category=products_by_category, categories=categories, is_admin=is_admin)

@app.route('/check_customer_phone', methods=['POST'])
@login_required
def check_customer_phone():
    data = request.json
    phone_number = data.get('phone')
    
    customers_ref = db.collection('customers').where('phone', '==', phone_number)
    customer_doc = customers_ref.get()
    
    if customer_doc:
        for doc in customer_doc:
            customer_data = doc.to_dict()
            return jsonify({'exists': True, 'customer': customer_data})
    
    return jsonify({'exists': False})

@app.route('/add_customer', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    gender = data.get('gender')

    if not name or not phone or not gender:
        return jsonify({'success': False, 'message': 'Invalid customer data'})

    customers_ref = db.collection('customers').document()
    customers_ref.set({
        'name': name,
        'phone': phone,
        'gender': gender,
        'points': 0  # Assuming you want to initialize points to 0
    })
    
    return jsonify({'success': True})

@app.route('/get_products/<category>')
@login_required
def get_products(category):
    products = get_products_by_category(category)
    return jsonify(products)

# Function to get all payment types
def get_all_payment_types():
    payment_types_ref = db.collection('payment_types')
    payment_types = [doc.id for doc in payment_types_ref.stream()]
    return payment_types

# Route to display the payment types management page
@app.route('/admin/payment_types')
@login_required
def admin_payment_types():
    payment_types = get_all_payment_types()
    return render_template('admin_payment.html', payment_types=payment_types)

# Route to add a new payment type
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

# Route to edit an existing payment type
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

            # Create a new document with the updated name and the same data
            new_payment_type_ref = db.collection('payment_types').document(new_name)
            new_payment_type_ref.set({
                'name': new_name,  # Ensure the name field inside the document is updated
                **payment_type_data   # Preserve any other data in the document
            })

            # Delete the old payment type document
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
    # Retrieve the order items and total amount from the AJAX request
    data = request.get_json()
    order_items = data.get('order_items', [])
    total_amount = data.get('total_amount', 0)

    # Store order items and total amount in the session
    if order_items and total_amount:
        session['order_items'] = order_items
        session['total_amount'] = total_amount
        session.modified = True  # Mark the session as modified
        return jsonify(success=True)
    else:
        return jsonify(success=False)



@app.route('/payment')
@login_required
def payment():
    # Ensure the user is logged in
    if 'user' not in session:
        return redirect(url_for('index'))

    # Fetch payment types from the database
    payment_types = []
    payment_types_ref = db.collection('payment_types')  # Assuming 'payment_types' is the collection name
    docs = payment_types_ref.stream()

    for doc in docs:
        payment_types.append(doc.to_dict().get('name'))  # Assuming 'name' is the field for payment type name

    # Get the total amount and order items from the session
    total_amount = session.get('total_amount', 0)
    order_items = session.get('order_items', [])

    # Ensure we have order items and a total amount before proceeding to payment
    if not order_items or not total_amount:
        flash("No order items found. Please add items to the order.", 'danger')
        return redirect(url_for('menu'))  # Redirect back to the menu if no items are present

    return render_template('admin_payment_selection.html', payment_types=payment_types, total_amount=total_amount, order_items=order_items)




@app.route('/payment_success')
@login_required
def payment_success():
    # Check for session data
    order_items = session.get('order_items', [])
    total_amount = session.get('total_amount', 0)
    
    # If there are no items or amount, redirect to the menu
    if not order_items or not total_amount:
        flash("No order items found. Please add items to the order.", 'danger')
        return redirect(url_for('menu'))
    
    # Assuming successful payment processing has occurred, clear the session
    session.pop('order_items', None)
    session.pop('total_amount', None)
    
    # Render the payment success page
    return render_template('payment_success.html', total_amount=total_amount)


@app.route('/process_payment', methods=['POST'])
@login_required
def process_payment():
    data = request.get_json()
    payment_type = data.get('payment_type')
    total_amount = data.get('total_amount')
    order_items = data.get('order_items')
    
    # Create a Firestore client
    db = firestore.client()
    
    # Prepare transaction data
    transaction_data = {
        'payment_type': payment_type,
        'total_amount': float(total_amount),
        'order_items': order_items,
        'user_id': current_user.id,  # Assuming user is logged in and you have access to user id
        'timestamp': firestore.SERVER_TIMESTAMP
    }

    # Store the transaction data in Firestore under the 'transactions' collection
    transaction_ref = db.collection('transactions').document()
    transaction_ref.set(transaction_data)
    
    # Return success response
    return jsonify({'status': 'success'}), 200


@app.route('/admin/admin_staff_management')
def admin_staff_management():
    # Retrieve all staff from Firestore
    staff_list = []
    staff_ref = db.collection('staff')
    docs = staff_ref.stream()
    for doc in docs:
        staff_data = doc.to_dict()
        staff_data['id'] = doc.id  # Add document ID to the staff data for edit/delete operations
        staff_list.append(staff_data)

    return render_template('admin_staff_management.html', staff_list=staff_list)


# Add Staff Route
@app.route('/admin/add_staff', methods=['POST'])
def add_staff():
    data = request.get_json()

    # Check if the ID number already exists in the database
    id_number = data.get('id_number')
    staff_list = db.collection('staff').where('id_number', '==', id_number).get()

    if staff_list:
        return jsonify({'status': 'error', 'message': 'ID number already exists.'}), 400

    # Get the last added staff's ID to generate the new staff ID
    last_staff = db.collection('staff').order_by('staff_id', direction='DESCENDING').limit(1).get()

    if last_staff:
        last_staff_id = last_staff[0].to_dict().get('staff_id', 999)
    else:
        last_staff_id = 999  # Start from 1000 if no staff exist yet

    new_staff_id = last_staff_id + 1

    # Use the new_staff_id as the document name in Firestore
    new_staff_doc_name = str(new_staff_id)

    new_staff = {
        'staff_id': new_staff_id,
        'name': data.get('name'),
        'email': data.get('email'),
        'id_number': data.get('id_number'),
        'address': data.get('address'),
        'mobile': data.get('mobile'),
        'job_position': data.get('job_position')
    }

    # Store staff data using the staff_id as the document name
    db.collection('staff').document(new_staff_doc_name).set(new_staff)

    # Add staff to Firebase Authentication
    try:
        user = auth.create_user(
            uid=str(new_staff_id),  # Set staff_id as the Firebase user ID
            email=data.get('email'),
            password=data.get('id_number')
        )
        return jsonify({'status': 'success', 'auth_user_id': user.uid}), 200
    except exceptions.FirebaseError as e:
        return jsonify({'status': 'error', 'message': f'Error creating user: {str(e)}'}), 500



# Edit Staff Route (Use PUT to update staff details)
@app.route('/admin/edit_staff/<staff_id>', methods=['PUT'])
def edit_staff(staff_id):
    data = request.json
    
    # Ensure required fields are present
    if not staff_id:
        return jsonify({'status': 'error', 'message': 'Staff ID is required.'}), 400

    # Fetch the staff document using the Firestore document ID
    staff_ref = db.collection('staff').document(staff_id)
    staff_doc = staff_ref.get()

    if not staff_doc.exists:
        return jsonify({'status': 'error', 'message': 'Staff not found.'}), 404

    # Update staff data in Firestore
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


# Delete Staff Route (Use DELETE to remove staff details)
@app.route('/admin/delete_staff/<staff_id>', methods=['DELETE'])
def delete_staff(staff_id):
    # Ensure staff_id is provided
    if not staff_id:
        return jsonify({'status': 'error', 'message': 'Staff ID is required.'}), 400

    # Fetch the staff document using the Firestore document ID
    staff_ref = db.collection('staff').document(staff_id)
    staff_doc = staff_ref.get()

    if not staff_doc.exists:
        return jsonify({'status': 'error', 'message': 'Staff not found.'}), 404

    # Retrieve staff email for Firebase Authentication deletion
    staff_email = staff_doc.to_dict().get('email')

    # Try to delete the staff from Firebase Authentication
    try:
        # Fetch the user by email
        user = auth.get_user_by_email(staff_email)

        # Delete the user from Firebase Authentication
        auth.delete_user(user.uid)
        print(f"Successfully deleted user from Firebase Authentication: {user.uid}")

    except auth.UserNotFoundError:
        return jsonify({'status': 'error', 'message': 'Staff not found in Firebase Authentication.'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error deleting user from Firebase: {str(e)}'}), 500

    # Delete the document from Firestore
    staff_ref.delete()

    return jsonify({'status': 'success', 'message': 'Staff successfully deleted.'}), 200



if __name__ == '__main__':
    app.run(debug=True)
