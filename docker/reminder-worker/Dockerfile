FROM python:3.12-slim

# Устанавливаем часовой пояс
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reminder_worker.py .
COPY worker_metrics.py .

EXPOSE 8002

CMD ["python", "-u", "reminder_worker.py"]
