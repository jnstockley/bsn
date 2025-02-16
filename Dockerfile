FROM jnstockley/poetry:2.1.1-python3.13.2 AS build

RUN apk update && \
    apk upgrade && \
    apk add alpine-sdk python3-dev musl-dev libffi-dev gcc curl openssl-dev cargo pkgconfig && \
    mkdir /bsn

COPY . /bsn

WORKDIR /bsn/

RUN poetry lock && \
    poetry check && \
    poetry install --without=dev

FROM jnstockley/poetry:2.1.1-python3.13.2

COPY --from=build /root/.cache/pypoetry/virtualenvs  /root/.cache/pypoetry/virtualenvs

COPY --from=build /bsn /bsn

WORKDIR /bsn/

ENTRYPOINT ["poetry", "run", "python", "src/bsn.py"]
