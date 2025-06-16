FROM bakingbad/pytezos

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER root
RUN python -m pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib discord-webhook; \
    mkdir data; \
    chown pytezos data; \
    apk add curl
USER pytezos

# Copy the source code into the container.
COPY . .

# Run the application.
CMD python3 -m fountain
ENTRYPOINT ["python", "-m", "fountain"]
