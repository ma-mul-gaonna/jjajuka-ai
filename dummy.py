import random
from datetime import datetime, timedelta
import pymysql

# ------------------------
# DB 연결 설정
# ------------------------
conn = pymysql.connect(
    host="127.0.0.1",
    port=13306,
    user="admin",
    password="qwer1234",
    database="jjajuka",
    charset="utf8mb4"
)

cursor = conn.cursor()

# ------------------------
# 데이터 정의
# ------------------------
names = [
  "민준혁","서윤지","하준석","지우현","도윤성","채린아","준서민","예린수","시우찬","유진호",
  "태윤서","가온민","현우진","수빈재","지훈서","아린주","다온혁","규민수","시연우","하린재",
  "윤서호","준혁민","서진우","도현수","예진호","민재우","지안호","시훈재","채윤서","태민우",
  "하준우","수아진","지호민","예찬우","윤재호","준호진","시우현","민서윤","도윤우","서하진",
  "가온우","하윤서","지훈우","예린우","채민우","준서우","시우진","민준우","도현우","서윤우",
  "지우서","하린우","윤서우","예진우","준혁우","시훈우","민재서","도윤서","서진서","지안서",
  "하준서","윤재서","예찬서","채윤우","가온서","태민서","준호서","시우서","민준서","도현서",
  "서윤서","지우우","하린서","윤서서","예진서","준혁서","시훈서","민재우진","도윤우진","서진우진",
  "지안우진","하준우진","윤재우진","예찬우진","채윤우진","가온우진","태민우진","준호우진","시우우진","민준우진",
  "도현우진","서윤우진","지우우진","하린우진","윤서우진","예진우진","준혁우진","시훈우진","민재우서","도윤우서"
]

positions = ["SAWON", "JUIM", "DAERI", "CHAJANG", "GWAJANG", "JEONMU"]
employment_statuses = ["ACTIVE", "RESIGNED", "LEAVE"]

# ------------------------
# 랜덤 함수
# ------------------------
def random_phone():
    return f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}"

def random_date():
    start_date = datetime(2015, 1, 1)
    end_date = datetime(2024, 12, 31)
    delta = end_date - start_date
    return (start_date + timedelta(days=random.randint(0, delta.days))).strftime("%Y-%m-%d")

def random_status():
    return random.choices(employment_statuses, weights=[0.7, 0.2, 0.1])[0]

def random_position():
    return random.choices(positions, weights=[40, 25, 20, 10, 4, 1])[0]

def random_authority(i):
    return "ADMIN" if i % 20 == 0 else "USER"

TOTAL = 100
MIN_A = 50

# ------------------------
# grade 리스트 생성
# ------------------------
grades = ["GRADE_A"] * MIN_A

remaining = TOTAL - MIN_A

for _ in range(remaining):
    grades.append(random.choice(["GRADE_A", "GRADE_B", "GRADE_C"]))

# 섞어서 자연스럽게
random.shuffle(grades)

# ------------------------
# INSERT 실행 (skills 추가 ⭐)
# ------------------------
sql = """
INSERT INTO member
(name, login_id, password, authority, position, phone_number, hire_date, employment_status, skills)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

data_list = []

for idx, i in enumerate(range(6, 106)):
    data = (
        names[i % len(names)],
        f"user{i}",
        "1234",
        random_authority(i),
        random_position(),
        random_phone(),
        random_date(),
        random_status(),
        grades[idx]   # ⭐ 여기 변경
    )
    data_list.append(data)

try:
    cursor.executemany(sql, data_list)
    conn.commit()
    print(f"{cursor.rowcount} rows inserted successfully!")

except Exception as e:
    conn.rollback()
    print("Error:", e)

finally:
    cursor.close()
    conn.close()