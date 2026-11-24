
import os

import pymysql
from flask import Flask, render_template, request
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

if __name__ == "__main__":
    app.run(debug=True)

