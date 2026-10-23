from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import os
import re

app = Flask(__name__)
# Set SECRET_KEY in your environment before deploying publicly.
app.secret_key = os.environ.get("SECRET_KEY", "local-development-only-change-me")
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        email TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no INTEGER NOT NULL UNIQUE,
        customer_id INTEGER NOT NULL,
        table_number TEXT NOT NULL,
        subtotal REAL NOT NULL,
        discount REAL NOT NULL,
        gst REAL NOT NULL,
        total REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        item_total REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        image TEXT,
        emoji TEXT,
        is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        price REAL NOT NULL CHECK(price >= 0),
        rating REAL NOT NULL DEFAULT 4.5,
        image TEXT,
        is_available INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );


    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        quantity REAL NOT NULL DEFAULT 0,
        unit TEXT NOT NULL,
        min_quantity REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_item_id INTEGER NOT NULL,
        ingredient_id INTEGER NOT NULL,
        quantity_required REAL NOT NULL CHECK(quantity_required > 0),
        FOREIGN KEY (menu_item_id) REFERENCES menu_items(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
        UNIQUE(menu_item_id, ingredient_id)
    );

    CREATE TABLE IF NOT EXISTS inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        quantity REAL NOT NULL,
        previous_stock REAL,
        remaining_stock REAL,
        reason TEXT,
        order_no INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
    );
    """)

    # Add stock snapshot columns to older databases created before this feature.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory_transactions)").fetchall()}
    if "previous_stock" not in existing_columns:
        conn.execute("ALTER TABLE inventory_transactions ADD COLUMN previous_stock REAL")
    if "remaining_stock" not in existing_columns:
        conn.execute("ALTER TABLE inventory_transactions ADD COLUMN remaining_stock REAL")

    # Create the first admin only from environment variables.
    # Never commit real admin credentials to GitHub.
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    admin_count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if admin_count == 0 and admin_username and admin_password:
        conn.execute(
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            (
                admin_username,
                generate_password_hash(admin_password),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    elif admin_count == 0:
        print(
            "No admin account created. Set ADMIN_USERNAME and ADMIN_PASSWORD "
            "environment variables to create the first admin account."
        )

    categories = [
        ("Coffee", "images/coffee.png", "☕"),
        ("Burger", "images/burger.png", "🍔"),
        ("Pizza", "images/pizza.png", "🍕"),
        ("Pasta", "images/pasta.png", "🍝"),
        ("Desserts", "images/desserts.png", "🍰"),
        ("Cold Drinks", "images/colddrinks.png", "🥤"),
        ("Tea", "images/tea.png", "🍵"),
        ("Mocktails", "images/mocktails.png", "🍹"),
        ("Sandwiches", "images/sandwiches.jpeg", "🥪"),
        ("Salads", "images/salads.png", "🥗"),
        ("Combos", "images/burgercombo.png", "🍱"),
    ]
    # Keep category records synchronized with the real café categories.
    # This also fixes older databases where food names were accidentally stored
    # as category names.
    for name, image, emoji in categories:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, image, emoji) VALUES (?, ?, ?)",
            (name, image, emoji)
        )
        conn.execute(
            "UPDATE categories SET image = ?, emoji = ?, is_active = 1 WHERE name = ?",
            (image, emoji, name)
        )

    # If an older database contains food names as categories, move those food
    # items into their correct category before removing the old category rows.
    legacy_category_map = {
        "Espresso": "Coffee",
        "Latte": "Coffee",
        "Ice latte": "Coffee",
        "Americano": "Coffee",
        "Cappuccino": "Coffee",
        "Chicken Burger": "Burger",
        "Cheese Burger": "Burger",
        "Margherita Pizza": "Pizza",
        "Veggie Pizza": "Pizza",
        "Sicilian Pizza": "Pizza",
        "Veggie Corn Pizza": "Pizza",
        "Chocolate cake": "Desserts",
        "Coffee Brownie": "Desserts",
        "Chocolate Shake": "Cold Drinks",
        "Cold Brew": "Cold Drinks",
        "Lemon Mint": "Cold Drinks",
        "Green Tea": "Tea",
        "Margherita Mocktail": "Mocktails",
        "Cheese Sandwich": "Sandwiches",
        "Burger + Fries": "Combos",
        "Pasta": "Pasta",
    }
    for food_name, correct_category in legacy_category_map.items():
        target = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (correct_category,)
        ).fetchone()
        if target:
            conn.execute(
                "UPDATE menu_items SET category_id = ? WHERE name = ?",
                (target["id"], food_name)
            )

    # Remove inactive/legacy category rows that no longer contain menu items.
    canonical_names = tuple(name for name, _, _ in categories)
    placeholders = ",".join("?" for _ in canonical_names)
    conn.execute(
        f"DELETE FROM categories WHERE name NOT IN ({placeholders}) "
        "AND id NOT IN (SELECT DISTINCT category_id FROM menu_items)",
        canonical_names
    )


    # Seed the existing menu once. After this, prices/items are database-driven.
    seed_items = [
        ("Coffee", "Espresso", 150, 4.7, "images/espresso.jpeg"),
        ("Coffee", "Latte", 220, 4.9, "images/latte.jpeg"),
        ("Coffee", "Ice latte", 220, 4.9, "images/iced_latte.jpeg"),
        ("Coffee", "Americano", 220, 4.9, "images/americano.jpeg"),
        ("Coffee", "Cappuccino", 220, 4.9, "images/cappuccino.jpeg"),
        ("Burger", "Chicken Burger", 199, 4.8, "images/chickenburger.jpeg"),
        ("Burger", "Cheese Burger", 249, 4.7, "images/cheese-burger.jpeg"),
        ("Pizza", "Margherita Pizza", 299, 4.8, "images/margherita.jpeg"),
        ("Pizza", "Veggie Pizza", 299, 4.8, "images/veggie.jpeg"),
        ("Pizza", "Sicilian Pizza", 299, 4.8, "images/sicilian.jpeg"),
        ("Pizza", "Veggie Corn Pizza", 299, 4.8, "images/cornpizza.jpeg"),
        ("Pasta", "Pasta", 299, 4.8, "images/pasta.png"),
        ("Desserts", "Chocolate cake", 299, 4.8, "images/chocolatecake.jpeg"),
        ("Desserts", "Coffee Brownie", 299, 4.8, "images/coffee-brownie.jpeg"),
        ("Cold Drinks", "Chocolate Shake", 299, 4.8, "images/chocolateshake.jpeg"),
        ("Cold Drinks", "Cold Brew", 299, 4.8, "images/cold_brew.jpeg"),
        ("Cold Drinks", "Lemon Mint", 299, 4.8, "images/lemon-mint.jpeg"),
        ("Tea", "Green Tea", 299, 4.8, "images/green-tea.jpeg"),
        ("Mocktails", "Margherita Mocktail", 299, 4.8, "images/margherita.jpeg"),
        ("Sandwiches", "Cheese Sandwich", 299, 4.8, "images/cheese-sandwich.jpeg"),
        ("Combos", "Burger + Fries", 299, 4.8, "images/burger-fries.jpeg"),
        ("Combos", "Burger Combo", 399, 4.8, "images/burgercombo.png"),
    ]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for category, name, price, rating, image in seed_items:
        cat = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()
        conn.execute("""
            INSERT OR IGNORE INTO menu_items
            (category_id, name, description, price, rating, image, is_available, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (cat["id"], name, "Freshly prepared with quality ingredients.", price, rating, image, now))

    # -------------------- INVENTORY SEED DATA --------------------
    inventory_seed = [
        ("Burger Bun", 30, "pcs", 5), ("Chicken Patty", 25, "pcs", 5),
        ("Cheese Slice", 40, "pcs", 10), ("Tomato", 20, "pcs", 5),
        ("Lettuce", 20, "pcs", 5), ("Pizza Base", 20, "pcs", 5),
        ("Pizza Cheese", 30, "pcs", 5), ("Pizza Sauce", 10, "L", 2),
        ("Pasta", 10, "kg", 2), ("Pasta Sauce", 10, "L", 2),
        ("Coffee Beans", 5, "kg", 1), ("Milk", 20, "L", 3),
        ("Chocolate Syrup", 5, "L", 1), ("Tea Leaves", 2, "kg", 0.5),
        ("Cake Portion", 30, "pcs", 5), ("Brownie", 30, "pcs", 5),
        ("Lemon", 30, "pcs", 5), ("Mint", 2, "kg", 0.5),
        ("Bread", 40, "slices", 10), ("French Fries", 20, "kg", 3),
        ("Mocktail Syrup", 5, "L", 1),
        ("Cold Drink", 30, "pcs", 5),
    ]
    for name, qty, unit, minimum in inventory_seed:
        conn.execute("""
            INSERT OR IGNORE INTO ingredients
            (name, quantity, unit, min_quantity, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, qty, unit, minimum, now))

    recipe_seed = {
        "Chicken Burger":[("Burger Bun",1),("Chicken Patty",1),("Cheese Slice",1),("Tomato",2),("Lettuce",1)],
        "Cheese Burger":[("Burger Bun",1),("Cheese Slice",2),("Tomato",2),("Lettuce",1)],
        "Margherita Pizza":[("Pizza Base",1),("Pizza Cheese",1),("Pizza Sauce",0.15)],
        "Veggie Pizza":[("Pizza Base",1),("Pizza Cheese",1),("Pizza Sauce",0.15),("Tomato",2)],
        "Sicilian Pizza":[("Pizza Base",1),("Pizza Cheese",1),("Pizza Sauce",0.20)],
        "Veggie Corn Pizza":[("Pizza Base",1),("Pizza Cheese",1),("Pizza Sauce",0.15),("Tomato",2)],
        "Pasta":[("Pasta",0.15),("Pasta Sauce",0.10),("Pizza Cheese",0.25)],
        "Chocolate cake":[("Cake Portion",1),("Chocolate Syrup",0.05)],
        "Coffee Brownie":[("Brownie",1),("Chocolate Syrup",0.03)],
        "Chocolate Shake":[("Milk",0.25),("Chocolate Syrup",0.05)],
        "Cold Brew":[("Coffee Beans",0.03)],
        "Lemon Mint":[("Lemon",1),("Mint",0.01)],
        "Green Tea":[("Tea Leaves",0.005)],
        "Margherita Mocktail":[("Mocktail Syrup",0.05),("Lemon",1),("Mint",0.01)],
        "Cheese Sandwich":[("Bread",2),("Cheese Slice",1),("Tomato",1),("Lettuce",1)],
        "Burger + Fries":[("Burger Bun",1),("Chicken Patty",1),("Cheese Slice",1),("Tomato",2),("Lettuce",1),("French Fries",0.15)],
        "Espresso":[("Coffee Beans",0.018)], "Latte":[("Coffee Beans",0.018),("Milk",0.20)],
        "Ice latte":[("Coffee Beans",0.018),("Milk",0.20)], "Americano":[("Coffee Beans",0.018)],
        "Cappuccino":[("Coffee Beans",0.018),("Milk",0.15)],
        "Burger Combo": [("Burger Bun", 1),("Chicken Patty", 1),("Cheese Slice", 1),("Tomato", 2),("Lettuce", 1),("French Fries", 0.15),("Cold Drink", 1)],
    }
    for menu_name, recipe_items in recipe_seed.items():
        menu_row = conn.execute("SELECT id FROM menu_items WHERE name=?", (menu_name,)).fetchone()
        if menu_row:
            for ingredient_name, required in recipe_items:
                ing = conn.execute("SELECT id FROM ingredients WHERE name=?", (ingredient_name,)).fetchone()
                if ing:
                    conn.execute("""
                        INSERT OR IGNORE INTO recipes
                        (menu_item_id, ingredient_id, quantity_required)
                        VALUES (?, ?, ?)
                    """, (menu_row["id"], ing["id"], required))

    conn.commit()
    conn.close()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


init_db()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/combo")
def combo():
    return render_template("combo.html")

@app.route("/cart")
def cart():
    return render_template("cart.html")

@app.route("/success")
def success():
    return render_template("success.html", order_no=request.args.get("order_no"))

@app.route("/menu")
def menu():
    conn = get_db()

    try:
        rows = conn.execute("""
            SELECT c.name AS category, c.id AS category_id, c.image AS category_image,
                   c.emoji, m.id, m.name, m.description, m.price, m.rating, m.image, m.is_available
            FROM categories c
            JOIN menu_items m ON m.category_id = c.id
            WHERE c.is_active = 1 AND m.is_available = 1
            ORDER BY c.id, m.id
        """).fetchall()

        products = {}
        category_meta = []
        seen = set()

        for r in rows:

            products.setdefault(r["category"], []).append({
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "price": r["price"],
                "rating": r["rating"],
                "image": r["image"]
            })

            if r["category_id"] not in seen:
                category_meta.append({
                    "name": r["category"],
                    "image": r["category_image"],
                    "emoji": r["emoji"]
                })
                seen.add(r["category_id"])

        return render_template(
            "menu.html",
            products=products,
            category_meta=category_meta
        )

    finally:
        conn.close()

@app.route("/place_order", methods=["POST"])
def place_order():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip()
    table_number = str(data.get("table_number", "")).strip()
    items = data.get("items", [])

    if not name or not phone or not table_number:
        return jsonify({"success": False, "message": "Name, phone number and table number are required."}), 400
    if not re.fullmatch(r"[0-9]{10}", phone):
        return jsonify({"success": False, "message": "Please enter a valid 10-digit phone number."}), 400
    if not items:
        return jsonify({"success": False, "message": "Your cart is empty."}), 400

    conn = get_db()
    try:
        subtotal = 0
        clean_items = []
        required_stock = {}

        for item in items:
            item_name = str(item.get("name", "")).strip()
            quantity = int(item.get("qty", 0))
            if not item_name or quantity <= 0:
                conn.rollback()
                return jsonify({"success": False, "message": "Invalid cart item."}), 400

            db_item = conn.execute("""
                SELECT id, name, price FROM menu_items
                WHERE name = ? AND is_available = 1
            """, (item_name,)).fetchone()

            if not db_item:
                conn.rollback()
                return jsonify({"success": False, "message": f"{item_name} is currently unavailable."}), 400

            price = float(db_item["price"])
            item_total = price * quantity
            subtotal += item_total
            clean_items.append((item_name, price, quantity, item_total))

            recipes = conn.execute("""
                SELECT r.ingredient_id, r.quantity_required, i.name, i.quantity, i.unit
                FROM recipes r JOIN ingredients i ON i.id=r.ingredient_id
                WHERE r.menu_item_id=?
            """, (db_item["id"],)).fetchall()

            for r in recipes:
                iid = r["ingredient_id"]
                required_stock.setdefault(iid, {"name":r["name"], "unit":r["unit"], "available":float(r["quantity"]), "required":0})
                required_stock[iid]["required"] += float(r["quantity_required"]) * quantity

        for iid, req in required_stock.items():
            stock = conn.execute("SELECT name, quantity, unit FROM ingredients WHERE id=?", (iid,)).fetchone()
            if not stock:
                conn.rollback()
                return jsonify({"success":False,"message":f"Inventory item for {req['name']} was not found."}),400
            if float(stock["quantity"]) < req["required"]:
                conn.rollback()
                return jsonify({"success":False,"message":
                    f"Insufficient stock for {stock['name']}. Available: {float(stock['quantity']):g} {stock['unit']}, "
                    f"Required: {req['required']:g} {stock['unit']}."}),400

        discount = 50 if subtotal >= 500 else 0
        gst = round((subtotal - discount) * 0.05)
        total = subtotal - discount + gst
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        customer = conn.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if customer:
            customer_id = customer["id"]
            conn.execute("UPDATE customers SET name=?, email=? WHERE id=?", (name,email,customer_id))
        else:
            customer_id = conn.execute("""
                INSERT INTO customers (name, phone, email, created_at) VALUES (?, ?, ?, ?)
            """,(name,phone,email,now)).lastrowid

        last_order = conn.execute("SELECT MAX(order_no) AS max_order FROM orders").fetchone()
        order_no = max(100, last_order["max_order"] or 100) + 1

        order_id = conn.execute("""
            INSERT INTO orders
            (order_no, customer_id, table_number, subtotal, discount, gst, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
        """,(order_no,customer_id,table_number,subtotal,discount,gst,total,now)).lastrowid

        conn.executemany("""
            INSERT INTO order_items (order_id,item_name,price,quantity,item_total)
            VALUES (?,?,?,?,?)
        """,[(order_id,*x) for x in clean_items])

        for iid, req in required_stock.items():
            qty = float(req["required"])
            previous_stock = float(req["available"])
            remaining_stock = previous_stock - qty

            conn.execute(
                "UPDATE ingredients SET quantity=? WHERE id=?",
                (remaining_stock, iid)
            )
            conn.execute("""
                INSERT INTO inventory_transactions
                (ingredient_id,transaction_type,quantity,previous_stock,remaining_stock,reason,order_no,created_at)
                VALUES (?,'Stock Out',?,?,?,'Customer order',?,?)
            """,(iid,qty,previous_stock,remaining_stock,order_no,now))

        conn.commit()
        return jsonify({"success":True,"order_no":order_no,"order_id":order_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"success":False,"message":str(e)}),500
    finally:
        conn.close()

# -------------------- INVENTORY --------------------

@app.route("/admin/inventory")
@admin_required
def admin_inventory():
    return render_template("inventory.html")


@app.route("/api/admin/inventory")
@admin_required
def api_admin_inventory():
    conn=get_db()
    try:
        rows=conn.execute("""
            SELECT id,name,quantity,unit,min_quantity,
            CASE WHEN quantity<=0 THEN 'Out of Stock'
                 WHEN quantity<=min_quantity THEN 'Low Stock'
                 ELSE 'In Stock' END AS status
            FROM ingredients ORDER BY name
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/inventory/add", methods=["POST"])
@admin_required
def api_add_inventory():
    data=request.get_json(silent=True) or {}
    ingredient_id=data.get("ingredient_id")
    reason=str(data.get("reason","Manual stock addition")).strip()
    try: quantity=float(data.get("quantity",0))
    except (TypeError,ValueError): quantity=0

    if not ingredient_id or quantity<=0:
        return jsonify({"success":False,"message":"Enter a valid ingredient and quantity."}),400

    conn=get_db()
    try:
        ing=conn.execute("SELECT id,name,quantity,unit FROM ingredients WHERE id=?",(ingredient_id,)).fetchone()
        if not ing:
            return jsonify({"success":False,"message":"Ingredient not found."}),404
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        previous_stock = float(ing["quantity"])
        remaining_stock = previous_stock + quantity
        conn.execute("UPDATE ingredients SET quantity=? WHERE id=?",(remaining_stock,ingredient_id))
        conn.execute("""
            INSERT INTO inventory_transactions
            (ingredient_id,transaction_type,quantity,previous_stock,remaining_stock,reason,created_at)
            VALUES (?,'Stock In',?,?,?, ?,?)
        """,(ingredient_id,quantity,previous_stock,remaining_stock,reason or "Manual stock addition",now))
        conn.commit()
        return jsonify({"success":True,"message":f"{quantity:g} {ing['unit']} added to {ing['name']}."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success":False,"message":str(e)}),500
    finally:
        conn.close()


@app.route("/api/admin/inventory/ingredient", methods=["POST"])
@admin_required
def api_create_ingredient():
    data=request.get_json(silent=True) or {}
    name=str(data.get("name","")).strip()
    unit=str(data.get("unit","")).strip()
    try:
        quantity=float(data.get("quantity",0)); minimum=float(data.get("min_quantity",0))
    except (TypeError,ValueError):
        return jsonify({"success":False,"message":"Quantity values must be numbers."}),400
    if not name or not unit:
        return jsonify({"success":False,"message":"Ingredient name and unit are required."}),400
    if quantity<0 or minimum<0:
        return jsonify({"success":False,"message":"Quantity cannot be negative."}),400
    conn=get_db()
    try:
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur=conn.execute("""
            INSERT INTO ingredients(name,quantity,unit,min_quantity,created_at)
            VALUES(?,?,?,?,?)
        """,(name,quantity,unit,minimum,now))
        if quantity>0:
            conn.execute("""
                INSERT INTO inventory_transactions
                (ingredient_id,transaction_type,quantity,previous_stock,remaining_stock,reason,created_at)
                VALUES (?,'Stock In',?,0,?,'Opening stock',?)
            """,(cur.lastrowid,quantity,quantity,now))
        conn.commit()
        return jsonify({"success":True,"message":"Ingredient added successfully."})
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"success":False,"message":"Ingredient already exists."}),400
    finally:
        conn.close()


@app.route("/api/admin/inventory/recipes")
@admin_required
def api_get_recipes():
    conn=get_db()
    try:
        rows=conn.execute("""
            SELECT r.id,r.menu_item_id,m.name AS menu_item_name,
                   r.ingredient_id,i.name AS ingredient_name,
                   r.quantity_required,i.unit
            FROM recipes r
            JOIN menu_items m ON m.id=r.menu_item_id
            JOIN ingredients i ON i.id=r.ingredient_id
            ORDER BY m.name,i.name
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/admin/inventory/recipes", methods=["POST"])
@admin_required
def api_save_recipe():
    data=request.get_json(silent=True) or {}
    try:
        menu_item_id=int(data.get("menu_item_id",0))
        ingredient_id=int(data.get("ingredient_id",0))
        required=float(data.get("quantity_required",0))
    except (TypeError,ValueError):
        return jsonify({"success":False,"message":"Invalid recipe data."}),400
    if menu_item_id<=0 or ingredient_id<=0 or required<=0:
        return jsonify({"success":False,"message":"Select menu item, ingredient and quantity."}),400
    conn=get_db()
    try:
        conn.execute("""
            INSERT INTO recipes(menu_item_id,ingredient_id,quantity_required)
            VALUES(?,?,?)
            ON CONFLICT(menu_item_id,ingredient_id)
            DO UPDATE SET quantity_required=excluded.quantity_required
        """,(menu_item_id,ingredient_id,required))
        conn.commit()
        return jsonify({"success":True,"message":"Recipe saved successfully."})
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"success":False,"message":"Invalid menu item or ingredient."}),400
    finally:
        conn.close()


@app.route("/api/admin/inventory/recipes/<int:recipe_id>", methods=["DELETE"])
@admin_required
def api_delete_recipe(recipe_id):
    conn=get_db()
    try:
        cur=conn.execute("DELETE FROM recipes WHERE id=?",(recipe_id,))
        if cur.rowcount==0:
            return jsonify({"success":False,"message":"Recipe not found."}),404
        conn.commit()
        return jsonify({"success":True,"message":"Recipe deleted."})
    finally:
        conn.close()


@app.route("/api/admin/inventory/history")
@admin_required
def api_inventory_history():
    conn=get_db()
    try:
        rows=conn.execute("""
            SELECT t.id,i.name AS ingredient_name,t.transaction_type,
                   t.quantity,t.previous_stock,t.remaining_stock,
                   i.unit,t.reason,t.order_no,t.created_at
            FROM inventory_transactions t
            JOIN ingredients i ON i.id=t.ingredient_id
            ORDER BY t.id DESC LIMIT 200
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


# -------------------- ADMIN --------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        admin = conn.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        conn.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        error = "Invalid username or password."
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", admin_username=session.get("admin_username"))

@app.route("/admin/menu")
@admin_required
def admin_menu():
    return render_template("admin_menu.html")

@app.route("/kitchen")
@admin_required
def kitchen():
    return render_template("kitchen.html")

@app.route("/api/admin/categories")
@admin_required
def api_admin_categories():
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/menu", methods=["GET", "POST"])
@admin_required
def api_admin_menu():
    conn = get_db()
    try:
        if request.method == "GET":
            rows = conn.execute("""
                SELECT m.*, c.name AS category_name
                FROM menu_items m JOIN categories c ON c.id = m.category_id
                ORDER BY c.id, m.id
            """).fetchall()
            return jsonify([dict(r) for r in rows])

        # The Add Food form uses multipart/form-data so the restaurant owner can
        # choose or drag an image instead of typing a file path.
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            name = request.form.get("name", "").strip()
            category_id = int(request.form.get("category_id", 0))
            description = request.form.get("description", "").strip()
            price = float(request.form.get("price", 0))
            rating = float(request.form.get("rating", 4.5))
            image = ""

            uploaded = request.files.get("image")
            if uploaded and uploaded.filename:
                allowed_extensions = {"png", "jpg", "jpeg", "webp", "gif"}
                original_name = secure_filename(uploaded.filename)
                extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
                if extension not in allowed_extensions:
                    return jsonify({"success": False, "message": "Please upload PNG, JPG, JPEG, WEBP or GIF image."}), 400

                upload_dir = os.path.join(app.root_path, "static", "images", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                filename = f"{uuid.uuid4().hex}.{extension}"
                uploaded.save(os.path.join(upload_dir, filename))
                image = f"images/uploads/{filename}"
        else:
            data = request.get_json(silent=True) or {}
            category_id = int(data.get("category_id", 0))
            name = str(data.get("name", "")).strip()
            description = str(data.get("description", "")).strip()
            price = float(data.get("price", 0))
            rating = float(data.get("rating", 4.5))
            image = str(data.get("image", "")).strip()

        if not name or category_id <= 0 or price < 0:
            return jsonify({"success": False, "message": "Name, category and valid price are required."}), 400
        conn.execute("""
            INSERT INTO menu_items (category_id, name, description, price, rating, image, is_available, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (category_id, name, description, price, rating, image, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError as e:
        conn.rollback()
        return jsonify({"success": False, "message": "Food name already exists or category is invalid."}), 400
    finally:
        conn.close()

@app.route("/api/admin/menu/<int:item_id>", methods=["PUT", "DELETE"])
@admin_required
def api_admin_menu_item(item_id):
    conn = get_db()
    try:
        if request.method == "DELETE":
            conn.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
            conn.commit()
            return jsonify({"success": True})
        data = request.get_json(silent=True) or {}
        fields = {
            "name": str(data.get("name", "")).strip(),
            "description": str(data.get("description", "")).strip(),
            "price": float(data.get("price", 0)),
            "rating": float(data.get("rating", 4.5)),
            "image": str(data.get("image", "")).strip(),
            "category_id": int(data.get("category_id", 0)),
            "is_available": 1 if data.get("is_available", True) else 0,
        }
        if not fields["name"] or fields["price"] < 0 or fields["category_id"] <= 0:
            return jsonify({"success": False, "message": "Invalid menu data."}), 400
        conn.execute("""
            UPDATE menu_items
            SET category_id=?, name=?, description=?, price=?, rating=?, image=?, is_available=?
            WHERE id=?
        """, (fields["category_id"], fields["name"], fields["description"], fields["price"], fields["rating"], fields["image"], fields["is_available"], item_id))
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"success": False, "message": "Food name already exists."}), 400
    finally:
        conn.close()

@app.route("/api/customers/<int:customer_id>", methods=["DELETE"])
@admin_required
def delete_customer(customer_id):
    """Delete a customer and their order history from the demo database."""
    return delete_customers([customer_id])


@app.route("/api/customers/bulk-delete", methods=["POST"])
@admin_required
def bulk_delete_customers():
    payload = request.get_json(silent=True) or {}
    customer_ids = payload.get("customer_ids", [])
    if not isinstance(customer_ids, list) or not customer_ids:
        return jsonify({"success": False, "message": "Select at least one customer."}), 400
    try:
        ids = sorted({int(value) for value in customer_ids if str(value).isdigit()})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid customer selection."}), 400
    if not ids:
        return jsonify({"success": False, "message": "Select at least one valid customer."}), 400
    return delete_customers(ids)


def delete_customers(customer_ids):
    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in customer_ids)
        existing = conn.execute(
            f"SELECT id FROM customers WHERE id IN ({placeholders})", customer_ids
        ).fetchall()
        existing_ids = [row["id"] for row in existing]
        if not existing_ids:
            return jsonify({"success": False, "message": "No matching customers were found."}), 404

        marks = ",".join("?" for _ in existing_ids)
        order_rows = conn.execute(
            f"SELECT id FROM orders WHERE customer_id IN ({marks})", existing_ids
        ).fetchall()
        order_ids = [row["id"] for row in order_rows]
        if order_ids:
            order_marks = ",".join("?" for _ in order_ids)
            conn.execute(f"DELETE FROM order_items WHERE order_id IN ({order_marks})", order_ids)
            conn.execute(f"DELETE FROM orders WHERE id IN ({order_marks})", order_ids)
        conn.execute(f"DELETE FROM customers WHERE id IN ({marks})", existing_ids)
        conn.commit()
        return jsonify({"success": True, "deleted_count": len(existing_ids)})
    except Exception as exc:
        conn.rollback()
        app.logger.exception("Customer deletion failed")
        return jsonify({"success": False, "message": "Unable to delete customer records."}), 500
    finally:
        conn.close()


@app.route("/api/dashboard")
@admin_required
def api_dashboard():
    conn = get_db()
    try:
        orders = conn.execute("""
            SELECT o.id, o.order_no, o.table_number, o.subtotal, o.discount, o.gst, o.total,
                   o.status, o.created_at, c.name AS customer_name, c.phone, c.email
            FROM orders o JOIN customers c ON c.id = o.customer_id
            ORDER BY o.id DESC
        """).fetchall()
        order_data = []
        for order in orders:
            items = conn.execute("SELECT item_name, price, quantity, item_total FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall()
            order_data.append({**dict(order), "items": [dict(i) for i in items]})

        customers = conn.execute("""
            SELECT c.id, c.name, c.phone, c.email, COUNT(o.id) AS order_count,
                   COALESCE(SUM(o.total), 0) AS total_spent
            FROM customers c LEFT JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id ORDER BY c.id DESC
        """).fetchall()
        today = datetime.now().strftime("%Y-%m-%d")
        # Ingredients that have reached their configured minimum stock level.
        # These are surfaced on the admin dashboard as low/out-of-stock alerts.
        low_stock = conn.execute("""
            SELECT id, name, quantity, unit, min_quantity,
                   CASE
                       WHEN quantity <= 0 THEN 'Out of Stock'
                       ELSE 'Low Stock'
                   END AS stock_alert
            FROM ingredients
            WHERE quantity <= min_quantity
            ORDER BY
                CASE WHEN quantity <= 0 THEN 0 ELSE 1 END,
                quantity ASC, name ASC
        """).fetchall()

        stats = {
            "total_orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "today_orders": conn.execute("SELECT COUNT(*) FROM orders WHERE date(created_at)=date(?)", (today,)).fetchone()[0],
            "pending": conn.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0],
            "preparing": conn.execute("SELECT COUNT(*) FROM orders WHERE status='Preparing'").fetchone()[0],
            "revenue": conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled'").fetchone()[0],
            "today_revenue": conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled' AND date(created_at)=date(?)", (today,)).fetchone()[0],
            "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        }
        top_items = conn.execute("""
            SELECT item_name, SUM(quantity) AS quantity, ROUND(SUM(item_total),2) AS sales
            FROM order_items oi JOIN orders o ON o.id=oi.order_id
            WHERE o.status != 'Cancelled'
            GROUP BY item_name ORDER BY quantity DESC LIMIT 5
        """).fetchall()
        return jsonify({
            "stats": stats,
            "orders": order_data,
            "customers": [dict(c) for c in customers],
            "top_items": [dict(i) for i in top_items],
            "low_stock": [dict(i) for i in low_stock]
        })
    finally:
        conn.close()

@app.route("/api/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status=str((request.get_json(silent=True) or {}).get("status","")).strip()
    allowed={"Pending","Preparing","Ready","Completed","Cancelled"}
    if status not in allowed:
        return jsonify({"success":False,"message":"Invalid order status."}),400

    conn=get_db()
    try:
        order=conn.execute(
            "SELECT id,order_no,status FROM orders WHERE id=?",(order_id,)
        ).fetchone()
        if not order:
            return jsonify({"success":False,"message":"Order not found."}),404

        old=order["status"]
        if old==status:
            return jsonify({"success":True,"status":status})

        items=conn.execute("""
            SELECT oi.item_name,oi.quantity,m.id AS menu_item_id
            FROM order_items oi
            LEFT JOIN menu_items m ON m.name=oi.item_name
            WHERE oi.order_id=?
        """,(order_id,)).fetchall()

        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if old!="Cancelled" and status=="Cancelled":
            restored={}
            for item in items:
                if not item["menu_item_id"]: continue
                recipes=conn.execute(
                    "SELECT ingredient_id,quantity_required FROM recipes WHERE menu_item_id=?",
                    (item["menu_item_id"],)
                ).fetchall()
                for r in recipes:
                    restored[r["ingredient_id"]]=restored.get(r["ingredient_id"],0)+float(r["quantity_required"])*int(item["quantity"])

            for iid,qty in restored.items():
                current = conn.execute("SELECT quantity FROM ingredients WHERE id=?", (iid,)).fetchone()
                previous_stock = float(current["quantity"])
                remaining_stock = previous_stock + float(qty)
                conn.execute("UPDATE ingredients SET quantity=? WHERE id=?",(remaining_stock,iid))
                conn.execute("""
                    INSERT INTO inventory_transactions
                    (ingredient_id,transaction_type,quantity,previous_stock,remaining_stock,reason,order_no,created_at)
                    VALUES (?,'Stock In',?,?,?,'Cancelled order - stock restored',?,?)
                """,(iid,qty,previous_stock,remaining_stock,order["order_no"],now))

        elif old=="Cancelled" and status!="Cancelled":
            required={}
            for item in items:
                if not item["menu_item_id"]: continue
                recipes=conn.execute("""
                    SELECT r.ingredient_id,r.quantity_required,i.name,i.quantity,i.unit
                    FROM recipes r JOIN ingredients i ON i.id=r.ingredient_id
                    WHERE r.menu_item_id=?
                """,(item["menu_item_id"],)).fetchall()
                for r in recipes:
                    iid=r["ingredient_id"]
                    required.setdefault(iid,{"name":r["name"],"unit":r["unit"],"available":float(r["quantity"]),"required":0})
                    required[iid]["required"]+=float(r["quantity_required"])*int(item["quantity"])

            for iid,info in required.items():
                if info["available"]<info["required"]:
                    conn.rollback()
                    return jsonify({"success":False,"message":
                        f"Cannot reopen order. Insufficient stock for {info['name']}. "
                        f"Available: {info['available']:g} {info['unit']}, required: {info['required']:g} {info['unit']}."}),400

            for iid,info in required.items():
                previous_stock = float(info["available"])
                qty = float(info["required"])
                remaining_stock = previous_stock - qty
                conn.execute("UPDATE ingredients SET quantity=? WHERE id=?",(remaining_stock,iid))
                conn.execute("""
                    INSERT INTO inventory_transactions
                    (ingredient_id,transaction_type,quantity,previous_stock,remaining_stock,reason,order_no,created_at)
                    VALUES (?,'Stock Out',?,?,?,'Order reopened',?,?)
                """,(iid,qty,previous_stock,remaining_stock,order["order_no"],now))

        conn.execute("UPDATE orders SET status=? WHERE id=?",(status,order_id))
        conn.commit()
        return jsonify({"success":True,"status":status})
    except Exception as e:
        conn.rollback()
        return jsonify({"success":False,"message":str(e)}),500
    finally:
        conn.close()


@app.route("/api/orders/by-number/<int:order_no>")
def order_by_number(order_no):
    conn = get_db()
    try:
        order = conn.execute("""
            SELECT o.id, o.order_no, o.table_number, o.total, o.status, o.created_at, c.name AS customer_name
            FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.order_no=?
        """, (order_no,)).fetchone()
        if not order:
            return jsonify({"success": False, "message": "Order not found."}), 404
        items = conn.execute("SELECT item_name, quantity, price, item_total FROM order_items WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
        return jsonify({"success": True, "order": dict(order), "items": [dict(i) for i in items]})
    finally:
        conn.close()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
