FROM python:3.12-slim

RUN apt update && apt install -y git gdal-bin gdal-data libgdal-dev && apt clean

WORKDIR /src

ARG GITLAB_USER=gitlab-ci-token
ARG OCEANUM_PYTHON_REF=entry-points-cli

RUN --mount=type=secret,id=token,env=GITLAB_TOKEN git clone --depth=1 --branch $OCEANUM_PYTHON_REF https://$GITLAB_USER:$GITLAB_TOKEN@gitlab.com/oceanum/oceanum-io/oceanum-python.git &&\
    pip install --no-cache-dir ./oceanum-python
ADD . oceanum-run-cli
RUN pip install --no-cache-dir ./oceanum-run-cli

ENTRYPOINT ["oceanum", "run"]