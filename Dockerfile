FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt
# تثبيت المتصفح في الحاوية
RUN playwright install chromium

CMD ["python", "bot.py"]

