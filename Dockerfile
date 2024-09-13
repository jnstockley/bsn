FROM python:3.12.6-alpine3.20

RUN apk update

RUN apk upgrade

RUN apk add alpine-sdk python3-dev libressl-dev musl-dev libffi-dev gcc libressl-dev curl

RUN addgroup -S bsn && adduser -S bsn -G bsn

RUN mkdir /bsn

RUN chown -R bsn:bsn /bsn

USER bsn

ENV PATH="/home/bsn/.local/bin:$PATH"

ENV PYTHONPATH=/bsn

RUN python3 -m pip install --upgrade pip

RUN python3 -m pip install --user pipx

RUN pipx install poetry

COPY pyproject.toml /bsn

COPY poetry.lock /bsn

WORKDIR /bsn/src

RUN poetry install

COPY src /bsn/src

USER root

RUN apk del alpine-sdk python3-dev libressl-dev musl-dev libffi-dev gcc libressl-dev curl

USER bsn

ENTRYPOINT ["poetry", "run", "python", "main.py"]
