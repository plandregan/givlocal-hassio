ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY rootfs/app/backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/backend/requirements.txt

COPY rootfs/app /app

COPY rootfs/etc/services.d /etc/services.d
RUN chmod a+x /etc/services.d/givenergy_local/run

ENV PYTHONUNBUFFERED=1
