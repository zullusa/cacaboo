FROM python:3.12-slim

# Устанавливаем часовой пояс
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Инструменты для дампа БД (mysqldump) и загрузки на Windows-шару (smbclient)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-mysql-client \
        smbclient \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backup_worker.py .

CMD ["python", "-u", "backup_worker.py"]