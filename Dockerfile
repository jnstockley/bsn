FROM jnstockley/poetry:2.0.1-python3.13.1@sha256:639d51cbf1a730d117a4067b2558b1be2748f1a6dbd45347c6d22c18ec5a715e AS build

RUN apk update && \
    apk upgrade && \
    apk add alpine-sdk python3-dev musl-dev libffi-dev gcc curl openssl-dev cargo pkgconfig && \
    mkdir /bsn

COPY . /bsn

WORKDIR /bsn/

RUN poetry lock && \
    poetry check && \
    poetry install --without=dev

FROM jnstockley/poetry:2.0.1-python3.13.1@sha256:639d51cbf1a730d117a4067b2558b1be2748f1a6dbd45347c6d22c18ec5a715e

COPY --from=build /root/.cache/pypoetry/virtualenvs  /root/.cache/pypoetry/virtualenvs

COPY --from=build /bsn /bsn

WORKDIR /bsn/

ENTRYPOINT ["poetry", "run", "python", "src/bsn.py"]
