from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length
import pyrebase
import firebase_admin
from firebase_admin import credentials, firestore
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
auth = firebase.auth()

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
    if 'user' in session:
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
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = user['localId']
            session['email'] = email

            # Save user info to Firestore
            db.collection('users').document(user['localId']).set({
                'user_id': user['localId'],
                'email': email
            })

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
        except:
            flash('Invalid credentials')
            return redirect(url_for('index'))
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error in {field}: {error}")
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

    # Add product to Firestore
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

    # Update product in Firestore
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
    # Delete product from Firestore
    db.collection('products').document(product_id).delete()
    return jsonify({'success': True})

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

@app.route('/payment')
@login_required
def payment():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('payment.html')

@app.route('/payment_success')
@login_required
def payment_success():
    return render_template('payment_success.html')

if __name__ == '__main__':
    app.run(debug=True)
