# Elterngeld- & Haushaltsplaner als Website (Docker)
#
# Build:  docker build -t elterngeld-planner .
# Run:    docker run -d -p 8501:8501 --name elterngeld elterngeld-planner
# Aufruf: http://<server-ip>:8501

FROM python:3.12-slim

WORKDIR /app

# Abhängigkeiten zuerst kopieren (besseres Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code und Server-Konfiguration
COPY calculations.py app.py ./
COPY .streamlit ./.streamlit

EXPOSE 8501

# Healthcheck: Streamlit-Endpunkt
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
