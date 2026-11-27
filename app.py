
import os
from functools import wraps

import pymysql
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, abort,
    redirect, url_for, session, flash, g, jsonify
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

from datetime import date
from decimal import Decimal, InvalidOperation
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("Добавь SECRET_KEY в файл .env")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

csrf = CSRFProtect(app)


def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )


@app.route("/")
def home():
    return render_template("index.html")



@app.route("/tours")
def tours():
    category = request.args.get("category", type=int)
    max_price = request.args.get("max_price", type=int)
    duration = request.args.get("duration", type=int)

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            query = """
                SELECT
                    tours.id,
                    tours.title,
                    tours.description,
                    tours.location,
                    tours.duration_days,
                    tours.price,
                    tours.image,
                    categories.name AS category
                FROM tours
                JOIN categories
                    ON tours.category_id = categories.id
                WHERE tours.is_active = TRUE
            """

            params = []

            if category:
                query += " AND tours.category_id = %s"
                params.append(category)

            if max_price:
                query += " AND tours.price <= %s"
                params.append(max_price)

            if duration:
                query += " AND tours.duration_days = %s"
                params.append(duration)

            query += " ORDER BY tours.id"

            cursor.execute(query, params)
            all_tours = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "tours.html",
        tours=all_tours
    )


@app.route("/tours/<int:tour_id>")
def tour_detail(tour_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            # Получаем информацию о туре
            cursor.execute("""
                SELECT
                    t.id,
                    t.title,
                    t.description,
                    t.location,
                    t.duration_days,
                    t.price,
                    t.max_participants,
                    t.image,
                    c.name AS category
                FROM tours t
                JOIN categories c ON t.category_id = c.id
                WHERE t.id = %s AND t.is_active = TRUE
            """, (tour_id,))

            tour = cursor.fetchone()

            if tour is None:
                abort(404)

            # Получаем доступные даты поездки
            cursor.execute("""
                SELECT
                    id,
                    start_date,
                    end_date,
                    available_places
                FROM tour_dates
                WHERE tour_id = %s
                  AND start_date >= CURDATE()
                  AND available_places > 0
                ORDER BY start_date
            """, (tour_id,))

            dates = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "tour_detail.html",
        tour=tour,
        dates=dates
    )


# Загрузка текущего пользователя
@app.before_request
def load_current_user():
    g.user = None

    user_id = session.get("user_id")

    if not user_id:
        return

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, email, role FROM users WHERE id = %s",
                (user_id,)
            )
            g.user = cursor.fetchone()
    finally:
        connection.close()

    if g.user is None:
        session.clear()


# Защита страниц для авторизованных пользователей
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Для продолжения войдите в аккаунт.", "error")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


# Проверка прав администратора
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Сначала войдите в аккаунт.", "error")
            return redirect(url_for("login"))

        if g.user["role"] != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


# Регистрация
@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Заполните все обязательные поля.", "error")
        elif len(name) > 100 or len(email) > 150:
            flash("Имя или адрес электронной почты слишком длинные.", "error")
        elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Введите корректный адрес электронной почты.", "error")
        elif len(password) < 8 or len(password) > 128:
            flash("Пароль должен содержать от 8 до 128 символов.", "error")
        elif password != confirm:
            flash("Пароли не совпадают.", "error")
        else:
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM users WHERE email = %s",
                        (email,)
                    )

                    if cursor.fetchone():
                        flash("Этот email уже зарегистрирован.", "error")
                    else:
                        password_hash = generate_password_hash(password)

                        cursor.execute("""
                            INSERT INTO users (name, email, password_hash, role)
                            VALUES (%s, %s, %s, 'user')
                        """, (name, email, password_hash))

                        user_id = cursor.lastrowid
                        connection.commit()

                        session.clear()
                        session["user_id"] = user_id

                        flash("Регистрация прошла успешно!", "success")
                        return redirect(url_for("profile"))
            finally:
                connection.close()

    return render_template("register.html")


# Авторизация
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email,)
                )
                user = cursor.fetchone()
        finally:
            connection.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]

            flash("Вы успешно вошли в аккаунт.", "success")
            return redirect(url_for("profile"))

        flash("Неверный email или пароль.", "error")

    return render_template("login.html")


# Выход из аккаунта
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("home"))


# Личный кабинет
@app.route("/profile")
@login_required
def profile():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    b.id,
                    b.participants,
                    b.total_price,
                    b.status,
                    b.created_at,
                    t.title AS tour_title,
                    td.start_date,
                    td.end_date
                FROM bookings b
                JOIN tour_dates td ON b.tour_date_id = td.id
                JOIN tours t ON td.tour_id = t.id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC, b.id DESC
            """, (g.user["id"],))

            bookings = cursor.fetchall()
    finally:
        connection.close()

    return render_template(
        "profile.html",
        user=g.user,
        bookings=bookings
    )


@app.route("/book/<int:tour_id>", methods=["POST"])
@login_required
def book_tour(tour_id):
    tour_date_id = request.form.get("tour_date_id", type=int)
    participants = request.form.get("participants", type=int)

    if not tour_date_id or not participants or participants < 1:
        flash("Выберите дату и количество участников.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))

    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    td.id,
                    td.available_places,
                    td.start_date,
                    t.id AS tour_id,
                    t.price,
                    t.max_participants
                FROM tour_dates td
                JOIN tours t ON td.tour_id = t.id
                WHERE td.id = %s
                  AND t.id = %s
                  AND t.is_active = TRUE
                FOR UPDATE
            """, (tour_date_id, tour_id))

            selected_date = cursor.fetchone()

            if not selected_date:
                connection.rollback()
                flash("Выбранная дата недоступна.", "error")
                return redirect(url_for("tour_detail", tour_id=tour_id))

            if selected_date["start_date"] < __import__("datetime").date.today():
                connection.rollback()
                flash("Нельзя забронировать прошедшую дату.", "error")
                return redirect(url_for("tour_detail", tour_id=tour_id))

            if participants > selected_date["available_places"]:
                connection.rollback()
                flash("Недостаточно свободных мест.", "error")
                return redirect(url_for("tour_detail", tour_id=tour_id))

            if participants > selected_date["max_participants"]:
                connection.rollback()
                flash("Превышено максимальное число участников.", "error")
                return redirect(url_for("tour_detail", tour_id=tour_id))

            total_price = selected_date["price"] * participants

            cursor.execute("""
                INSERT INTO bookings
                    (user_id, tour_date_id, participants, total_price, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (
                g.user["id"],
                tour_date_id,
                participants,
                total_price
            ))

            cursor.execute("""
                UPDATE tour_dates
                SET available_places = available_places - %s
                WHERE id = %s
            """, (participants, tour_date_id))

        connection.commit()

        flash("Бронирование успешно оформлено!", "success")
        return redirect(url_for("profile"))

    except Exception:
        connection.rollback()
        app.logger.exception("Ошибка при бронировании тура")
        flash("Не удалось оформить бронирование. Попробуйте позже.", "error")
        return redirect(url_for("tour_detail", tour_id=tour_id))

    finally:
        connection.close()


# Административная панель
@app.route("/admin")
@admin_required
def admin_dashboard():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    b.id,
                    u.name AS client_name,
                    u.email AS client_email,
                    t.title AS tour_title,
                    td.start_date,
                    b.participants,
                    b.total_price,
                    b.status
                FROM bookings b
                JOIN users u ON b.user_id = u.id
                JOIN tour_dates td ON b.tour_date_id = td.id
                JOIN tours t ON td.tour_id = t.id
                ORDER BY b.created_at DESC, b.id DESC
            """)
            bookings = cursor.fetchall()

            cursor.execute("""
                SELECT id, title, price, duration_days, is_active
                FROM tours
                ORDER BY id DESC
            """)
            tours = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "admin.html",
        bookings=bookings,
        tours=tours
    )


@app.route("/admin/bookings/<int:booking_id>/<action>", methods=["POST"])
@admin_required
def update_booking(booking_id, action):
    if action not in ("confirm", "cancel"):
        abort(400)

    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            # Блокируем бронирование на время изменения
            cursor.execute("""
                SELECT id, tour_date_id, participants, status
                FROM bookings
                WHERE id = %s
                FOR UPDATE
            """, (booking_id,))

            booking = cursor.fetchone()

            if not booking:
                connection.rollback()
                abort(404)

            if action == "confirm":
                if booking["status"] != "pending":
                    connection.rollback()
                    flash("Подтвердить можно только новую заявку.", "error")
                    return redirect(url_for("admin_dashboard"))

                cursor.execute("""
                    UPDATE bookings
                    SET status = 'confirmed'
                    WHERE id = %s
                """, (booking_id,))

                message = "Бронирование подтверждено."

            else:
                if booking["status"] == "cancelled":
                    connection.rollback()
                    flash("Заявка уже отменена.", "error")
                    return redirect(url_for("admin_dashboard"))

                # Оплаченную заявку не отменяем автоматически
                cursor.execute("""
                    SELECT status
                    FROM payments
                    WHERE booking_id = %s
                    FOR UPDATE
                """, (booking_id,))

                payment = cursor.fetchone()

                if payment and payment["status"] == "paid":
                    connection.rollback()
                    flash("Оплаченную заявку нельзя отменить здесь.", "error")
                    return redirect(url_for("admin_dashboard"))

                cursor.execute("""
                    UPDATE bookings
                    SET status = 'cancelled'
                    WHERE id = %s
                """, (booking_id,))

                # Возвращаем свободные места
                cursor.execute("""
                    UPDATE tour_dates
                    SET available_places = available_places + %s
                    WHERE id = %s
                """, (booking["participants"], booking["tour_date_id"]))

                message = "Бронирование отменено. Места возвращены."

        connection.commit()
        flash(message, "success")

    except Exception:
        connection.rollback()
        app.logger.exception("Ошибка изменения бронирования")
        flash("Не удалось изменить бронирование.", "error")

    finally:
        connection.close()

    return redirect(url_for("admin_dashboard"))


# Проверка данных формы тура
def read_tour_form():
    try:
        category_id = int(request.form.get("category_id", ""))
        duration = int(request.form.get("duration_days", ""))
        max_people = int(request.form.get("max_participants", ""))
        price = Decimal(request.form.get("price", ""))
    except (ValueError, InvalidOperation):
        raise ValueError("Проверьте цену, категорию и количество участников.")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()
    image = request.form.get("image", "").strip()

    if not title or not description or not location:
        raise ValueError("Заполните обязательные поля.")

    if len(title) > 150 or len(location) > 150:
        raise ValueError("Название или местоположение слишком длинное.")

    if duration < 1 or max_people < 1 or price < 0:
        raise ValueError("Длительность и число участников должны быть больше нуля.")

    if price > Decimal("99999999.99") or price.as_tuple().exponent < -2:
        raise ValueError("Укажите корректную цену с точностью до копеек.")

    if image:
        if image != secure_filename(image) or len(image) > 255:
            raise ValueError("Укажите допустимое имя файла изображения.")
        if not image.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            raise ValueError("Фотография должна быть JPG, PNG или WebP.")
        image_path = os.path.join(app.static_folder, "images", image)
        if not os.path.isfile(image_path):
            raise ValueError("Такой фотографии нет в static/images.")

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM categories WHERE id = %s",
                (category_id,)
            )
            if cursor.fetchone() is None:
                raise ValueError("Выберите существующую категорию.")
    finally:
        connection.close()

    return (
        category_id, title, description, location,
        duration, price, max_people, image or None
    )


# Создание тура
@app.route("/admin/tours/create", methods=["GET", "POST"])
@admin_required
def admin_create_tour():
    connection = get_db_connection()

    try:
        if request.method == "POST":
            try:
                data = read_tour_form()

                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO tours
                        (category_id, title, description, location,
                         duration_days, price, max_participants, image)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, data)

                connection.commit()
                flash("Тур успешно создан.", "success")
                return redirect(url_for("admin_dashboard"))

            except ValueError as error:
                flash(str(error), "error")

        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM categories ORDER BY id")
            categories = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "admin_tour_form.html",
        tour=None,
        categories=categories,
        dates=[]
    )


# Редактирование тура
@app.route("/admin/tours/<int:tour_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_tour(tour_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tours WHERE id = %s",
                (tour_id,)
            )
            tour = cursor.fetchone()

        if tour is None:
            abort(404)

        if request.method == "POST":
            try:
                data = read_tour_form()

                with connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE tours
                        SET category_id = %s,
                            title = %s,
                            description = %s,
                            location = %s,
                            duration_days = %s,
                            price = %s,
                            max_participants = %s,
                            image = %s
                        WHERE id = %s
                    """, data + (tour_id,))

                connection.commit()
                flash("Изменения сохранены.", "success")
                return redirect(url_for("admin_dashboard"))

            except ValueError as error:
                flash(str(error), "error")

        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM categories ORDER BY id")
            categories = cursor.fetchall()

            cursor.execute("""
                SELECT id, start_date, end_date, available_places
                FROM tour_dates
                WHERE tour_id = %s
                ORDER BY start_date
            """, (tour_id,))
            dates = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "admin_tour_form.html",
        tour=tour,
        categories=categories,
        dates=dates
    )


# Скрытие и восстановление тура
@app.route("/admin/tours/<int:tour_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_tour(tour_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE tours
                SET is_active = NOT is_active
                WHERE id = %s
            """, (tour_id,))

            if cursor.rowcount == 0:
                connection.rollback()
                abort(404)

        connection.commit()
        flash("Статус тура изменён.", "success")

    finally:
        connection.close()

    return redirect(url_for("admin_dashboard"))


# Добавление доступной даты тура
@app.route("/admin/tours/<int:tour_id>/dates", methods=["POST"])
@admin_required
def admin_add_tour_date(tour_id):
    try:
        start = date.fromisoformat(request.form.get("start_date", ""))
        end = date.fromisoformat(request.form.get("end_date", ""))
        places = int(request.form.get("available_places", ""))
    except (ValueError, TypeError):
        flash("Проверьте даты и количество мест.", "error")
        return redirect(url_for("admin_edit_tour", tour_id=tour_id))

    if start < date.today() or end < start or places < 1:
        flash("Укажите будущие даты и положительное количество мест.", "error")
        return redirect(url_for("admin_edit_tour", tour_id=tour_id))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT max_participants FROM tours WHERE id = %s",
                (tour_id,)
            )
            tour = cursor.fetchone()

            if tour is None:
                abort(404)

            if places > tour["max_participants"]:
                flash("Мест больше, чем вместимость тура.", "error")
                return redirect(url_for("admin_edit_tour", tour_id=tour_id))

            try:
                cursor.execute("""
                    INSERT INTO tour_dates
                    (tour_id, start_date, end_date, available_places)
                    VALUES (%s, %s, %s, %s)
                """, (tour_id, start, end, places))
                connection.commit()
                flash("Дата поездки добавлена.", "success")

            except pymysql.err.IntegrityError:
                connection.rollback()
                flash("Такая дата уже есть у этого тура.", "error")

    finally:
        connection.close()

    return redirect(url_for("admin_edit_tour", tour_id=tour_id))



if __name__ == "__main__":
    app.run(debug=True)

