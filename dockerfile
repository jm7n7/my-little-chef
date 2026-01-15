# Use the official Python image.
# https://hub.docker.com/_/python
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
# We will create the requirements.txt file in the next step.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup.
# We use Gunicorn (a production web server) instead of the default Flask server
# because it is faster and more stable.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app