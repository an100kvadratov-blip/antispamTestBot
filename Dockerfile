# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файлы бота
COPY antispamTestBot_webhook.py .
COPY stopwords.txt .

# Открываем порт
EXPOSE 8080

# Запускаем бота
CMD ["python", "antispamTestBot_webhook.py"]
