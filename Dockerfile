FROM jnstockley/poetry:2.0.0-python3.13.1 AS build

RUN apk update && \
    apk upgrade && \
    apk add alpine-sdk python3-dev musl-dev libffi-dev gcc curl openssl-dev cargo pkgconfig && \
    mkdir /bsn

COPY pyproject.toml /bsn

COPY poetry.lock /bsn

WORKDIR /bsn/src

RUN poetry install --no-root

COPY src /bsn/src

FROM jnstockley/poetry:2.0.0-python3.13.1

ENV PYTHONPATH=/bsn:$PYTHONPATH

COPY --from=build /root/.cache/pypoetry/virtualenvs  /root/.cache/pypoetry/virtualenvs

COPY --from=build /bsn /bsn

WORKDIR /bsn/src

ENTRYPOINT ["poetry", "run", "python", "main.py"]
