import sqlite3
import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'supersecretkey2026'
DATABASE = 'database.db'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def generate_image_filename(english_name):
    """Генерирует имя файла из английского названия"""
    if not english_name:
        return 'placeholder.jpg'
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', english_name)
    filename = clean.lower().strip().replace(' ', '_') + '.jpg'
    if os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return filename
    return 'placeholder.jpg'

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS place (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                english_name TEXT,
                description TEXT,
                category TEXT,
                address TEXT,
                image TEXT,
                rating_avg REAL DEFAULT 0,
                views INTEGER DEFAULT 0
            )
        ''')

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorite (
                user_id INTEGER NOT NULL,
                place_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, place_id),
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (place_id) REFERENCES place (id)
            )
        ''')

        admin = cursor.execute("SELECT * FROM user WHERE username = 'admin'").fetchone()
        if not admin:
            cursor.execute(
                "INSERT INTO user (username, password, role) VALUES (?, ?, ?)",
                ('admin', generate_password_hash('admin'), 'admin')
            )

        if cursor.execute("SELECT COUNT(*) FROM place").fetchone()[0] == 0:
            places = [
                ('Памятник А.А. Угарову', 'Monument of Ugarov', 'Памятник основателю Оскольского электрометаллургического комбината.', 'monument', 'Площадь Победы'),
                ('Парк Победы', 'Victory Park', 'Центральный парк культуры и отдыха с фонтанами.', 'park', 'ул. Ленина, 1'),
                ('Краеведческий музей', 'Local Lore Museum', 'История Старооскольского края.', 'museum', 'ул. Ленина, 50'),
                ('Калипсо', 'Kalipso', 'Лучшая кофейня Старого Оскола', 'cafe', 'мкр.Жукова, 48'),
            ]
            for name, en_name, desc, cat, addr in places:
                image = generate_image_filename(en_name)
                cursor.execute(
                    "INSERT INTO place (name, english_name, description, category, address, image) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, en_name, desc, cat, addr, image)
                )
            db.commit()

# Создаём заглушку
placeholder_path = os.path.join(UPLOAD_FOLDER, 'placeholder.jpg')
if not os.path.exists(placeholder_path):
    try:
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (300, 200), color=(200, 200, 200))
        d = ImageDraw.Draw(img)
        d.text((50, 80), "Нет фото", fill=(50,50,50))
        img.save(placeholder_path)
    except:
        # Если Pillow не установлен, просто создаём пустой файл
        open(placeholder_path, 'w').close()

# ----- Декораторы -----
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'warning')
            return redirect(url_for('login'))
        db = get_db()
        user = db.execute("SELECT role FROM user WHERE id = ?", (session['user_id'],)).fetchone()
        if user['role'] != 'admin':
            flash('У вас нет прав администратора', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ----- Маршруты -----
@app.route('/')
def index():
    db = get_db()
    category = request.args.get('cat')
    if category and category != 'all':
        places = db.execute("SELECT * FROM place WHERE category = ? ORDER BY rating_avg DESC", (category,)).fetchall()
    else:
        places = db.execute("SELECT * FROM place ORDER BY rating_avg DESC").fetchall()
    categories = ['monument', 'park', 'museum', 'cafe']
    return render_template('index.html', places=places, current_cat=category, categories=categories)

@app.route('/place/<int:place_id>')
def place_detail(place_id):
    db = get_db()
    db.execute("UPDATE place SET views = views + 1 WHERE id = ?", (place_id,))
    db.commit()
    place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    if not place:
        return render_template('404.html'), 404
    reviews = db.execute(
        "SELECT r.*, u.username FROM review r JOIN user u ON r.user_id = u.id WHERE r.place_id = ? ORDER BY r.created_at DESC",
        (place_id,)
    ).fetchall()
    avg = db.execute("SELECT AVG(rating) as avg FROM review WHERE place_id = ?", (place_id,)).fetchone()['avg']
    if avg:
        db.execute("UPDATE place SET rating_avg = ? WHERE id = ?", (avg, place_id))
        db.commit()
        place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    return render_template('place.html', place=place, reviews=reviews)

@app.route('/add_review/<int:place_id>', methods=['POST'])
@login_required
def add_review(place_id):
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    if not comment:
        flash('Комментарий не может быть пустым', 'danger')
        return redirect(url_for('place_detail', place_id=place_id))
    db = get_db()
    db.execute(
        "INSERT INTO review (user_id, place_id, rating, comment) VALUES (?, ?, ?, ?)",
        (session['user_id'], place_id, rating, comment)
    )
    db.commit()
    flash('Ваш отзыв добавлен, спасибо!', 'success')
    return redirect(url_for('place_detail', place_id=place_id))

@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    places = db.execute("SELECT * FROM place ORDER BY id DESC").fetchall()
    return render_template('admin.html', places=places)

@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required
def add_place():
    if request.method == 'POST':
        name = request.form['name'].strip()
        english_name = request.form['english_name'].strip()
        description = request.form['description'].strip()
        category = request.form['category']
        address = request.form['address'].strip()
        if not name:
            flash('Название обязательно', 'danger')
            return redirect(url_for('add_place'))
        image = generate_image_filename(english_name)
        db = get_db()
        db.execute(
            "INSERT INTO place (name, english_name, description, category, address, image) VALUES (?, ?, ?, ?, ?, ?)",
            (name, english_name, description, category, address, image)
        )
        db.commit()
        flash(f'Место "{name}" добавлено', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('add_place.html')

@app.route('/admin/edit/<int:place_id>', methods=['GET', 'POST'])
@admin_required
def edit_place(place_id):
    db = get_db()
    place = db.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    if not place:
        flash('Место не найдено', 'danger')
        return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        english_name = request.form['english_name'].strip()
        description = request.form['description'].strip()
        category = request.form['category']
        address = request.form['address'].strip()
        image = generate_image_filename(english_name)
        db.execute(
            "UPDATE place SET name=?, english_name=?, description=?, category=?, address=?, image=? WHERE id=?",
            (name, english_name, description, category, address, image, place_id)
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
    flash('Место удалено', 'info')
    return redirect(url_for('admin_panel'))

# ----- Аутентификация -----
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Заполните все поля', 'danger')
            return redirect(url_for('register'))
        db = get_db()
        existing = db.execute("SELECT id FROM user WHERE username = ?", (username,)).fetchone()
        if existing:
            flash('Имя пользователя уже занято', 'danger')
        else:
            db.execute(
                "INSERT INTO user (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            flash('Регистрация успешна! Теперь войдите', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM user WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'С возвращением, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    init_db()
    app.run(debug=True)