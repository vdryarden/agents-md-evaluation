FROM mirror.gcr.io/library/python:3.12
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY repo/ /app/
RUN git init -q && git add -A && git -c user.email=bench@local -c user.name=bench commit -qm "initial"
