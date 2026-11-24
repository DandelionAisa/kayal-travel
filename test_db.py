
import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

try:
    connection = pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4"
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM tours")
        total = cursor.fetchone()[0]

    print("Подключение к MySQL успешно!")
    print(f"Количество туров в базе: {total}")

    connection.close()

except pymysql.MySQLError as error:
    print(f"Ошибка подключения: {error}")
