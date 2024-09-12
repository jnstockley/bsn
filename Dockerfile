FROM ubuntu:latest
LABEL authors="jackstockley"

ENTRYPOINT ["top", "-b"]