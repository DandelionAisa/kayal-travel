
import os

import pymysql
from flask import Flask, render_template, request, abort
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(debug=True)

