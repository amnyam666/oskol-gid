import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # замените на свой

# ----- Подключение к базе данных (SQLite) -----
DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
        # Таблица достопримечательностей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS place (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                address TEXT,
                photo_url TEXT,
                rating_avg REAL DEFAULT 0,
                views INTEGER DEFAULT 0
            )
        ''')
        # Таблица отзывов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                place_id INTEGER NOT NULL,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (place_id) REFERENCES place (id)
            )
        ''')
        # Таблица избранного (многие ко многим)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorite (
                user_id INTEGER NOT NULL,
                place_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, place_id),
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (place_id) REFERENCES place (id)
            )
        ''')
        # Добавим тестового администратора (логин: admin, пароль: admin)
        admin = cursor.execute("SELECT * FROM user WHERE username = 'admin'").fetchone()
        if not admin:
            cursor.execute(
                "INSERT INTO user (username, password, role) VALUES (?, ?, ?)",
                ('admin', generate_password_hash('admin'), 'admin')
            )
        # Добавим несколько тестовых мест
        if cursor.execute("SELECT COUNT(*) FROM place").fetchone()[0] == 0:
            places = [
                ('Памятник А.А. Угарову', 'Памятник основателю ОЭМК', 'monument', 'Площадь Победы', 'https://via.placeholder.com/300x200?text=Угаров'),
                ('Парк Победы', 'Центральный парк с фонтанами', 'park', 'ул. Ленина, 1', 'https://via.placeholder.com/300x200?text=Парк+Победы'),
                ('Краеведческий музей', 'История края', 'museum', 'ул. Ленина, 50', 'https://via.placeholder.com/300x200?text=Музей'),
            ]
            cursor.executemany(
                "INSERT INTO place (name, description, category, address, photo_url) VALUES (?, ?, ?, ?, ?)",
                places
            )
        db.commit()

# ----- Декоратор для проверки авторизации -----
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите, чтобы продолжить', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ----- Декоратор для проверки прав администратора -----
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите как администратор', 'warning')
            return redirect(url_for('login'))
        db = get_db()
        user = db.execute("SELECT role FROM user WHERE id = ?", (session['user_id'],)).fetchone()
        if user['role'] != 'admin':
            flash('Недостаточно прав', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ----- Маршруты -----
@app.route('/')
def index():
    db = get_db()
    category = request.args.get('cat')
    if category and category != 'all':
        places = db.execute("SELECT * FROM place WHERE category = ? ORDER BY rating_avg DESC", (category,)).fetchall()
    else:
        places = db.execute("SELECT * FROM place ORDER BY rating_avg DESC").fetchall()
    print("DEBUG: найдено мест:", len(places))   # <-- добавить
    categories = ['monument', 'park', 'museum', 'cafe']
    return render_template('index.html', places=places, current_cat=category, categories=categories)

@app.route('/place/<int:place_id>')
def place_detail(place_id):
    db = get_db()
    # увеличиваем счётчик просмотров
    db.execute("UPDATE place SET views = views + 1 WHERE id = ?", (place_id,))
    place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    reviews = db.execute("SELECT r.*, u.username FROM review r JOIN user u ON r.user_id = u.id WHERE place_id = ? ORDER BY r.created_at DESC", (place_id,)).fetchall()
    # средний рейтинг
    avg = db.execute("SELECT AVG(rating) as avg FROM review WHERE place_id = ?", (place_id,)).fetchone()['avg']
    if avg:
        db.execute("UPDATE place SET rating_avg = ? WHERE id = ?", (avg, place_id))
        db.commit()
    db.commit()
    place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    return render_template('place.html', place=place, reviews=reviews)

@app.route('/add_review/<int:place_id>', methods=['POST'])
@login_required
def add_review(place_id):
    rating = request.form['rating']
    comment = request.form['comment']
    db = get_db()
    db.execute(
        "INSERT INTO review (user_id, place_id, rating, comment) VALUES (?, ?, ?, ?)",
        (session['user_id'], place_id, rating, comment)
    )
    db.commit()
    flash('Отзыв добавлен', 'success')
    return redirect(url_for('place_detail', place_id=place_id))

@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    places = db.execute("SELECT * FROM place").fetchall()
    return render_template('admin.html', places=places)

@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required
def add_place():
    if request.method == 'POST':
        name = request.form['name']
        desc = request.form['description']
        cat = request.form['category']
        address = request.form['address']
        photo = request.form['photo_url']
        db = get_db()
        db.execute(
            "INSERT INTO place (name, description, category, address, photo_url) VALUES (?, ?, ?, ?, ?)",
            (name, desc, cat, address, photo)
        )
        db.commit()
        flash('Место добавлено', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('add_place.html')

@app.route('/admin/edit/<int:place_id>', methods=['GET', 'POST'])
@admin_required
def edit_place(place_id):
    db = get_db()
    place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    if request.method == 'POST':
        name = request.form['name']
        desc = request.form['description']
        cat = request.form['category']
        address = request.form['address']
        photo = request.form['photo_url']
        db.execute(
            "UPDATE place SET name=?, description=?, category=?, address=?, photo_url=? WHERE id=?",
            (name, desc, cat, address, photo, place_id)
        )
        db.commit()
        flash('Изменения сохранены', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('edit_place.html', place=place)

@app.route('/admin/delete/<int:place_id>')
@admin_required
def delete_place(place_id):
    db = get_db()
    db.execute("DELETE FROM review WHERE place_id = ?", (place_id,))
    db.execute("DELETE FROM favorite WHERE place_id = ?", (place_id,))
    db.execute("DELETE FROM place WHERE id = ?", (place_id,))
    db.commit()
    flash('Место удалено', 'danger')
    return redirect(url_for('admin_panel'))

# ----- Авторизация и регистрация -----
from flask import session

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        existing = db.execute("SELECT id FROM user WHERE username = ?", (username,)).fetchone()
        if existing:
            flash('Имя уже занято', 'danger')
        else:
            db.execute(
                "INSERT INTO user (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            flash('Регистрация успешна, войдите', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Добро пожаловать!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# ----- Запуск -----
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
