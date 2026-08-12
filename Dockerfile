FROM python:3.10-slim

WORKDIR /app

# نصب وابستگی‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کد
COPY . .

# ایجاد پوشه‌های مورد نیاز
RUN mkdir -p data/logs data/cache data/history data/signals

# اجرا
CMD ["python", "run.py"]
