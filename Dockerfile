FROM jnstockley/poetry:2.0.0-python3.13.1 AS build

RUN apk update && \
    apk upgrade && \
    apk add alpine-sdk python3-dev musl-dev libffi-dev gcc curl openssl-dev cargo pkgconfig && \
    mkdir /bsn

COPY . /bsn

WORKDIR /bsn/

RUN poetry lock && \
    poetry check && \
    poetry install

FROM jnstockley/poetry:2.0.0-python3.13.1

COPY --from=build /root/.cache/pypoetry/virtualenvs  /root/.cache/pypoetry/virtualenvs

COPY --from=build /bsn /bsn

WORKDIR /bsn/

ENTRYPOINT ["poetry", "run", "python", "src/bsn.py"]
