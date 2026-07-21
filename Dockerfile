# Sistema Experto de Diagnóstico de Redes — UTH Campus Choluteca
# IAE-0611 Inteligencia Artificial
#
# Construir la imagen:
#   docker build -t sistema-experto-redes .
#
# Correr la app de Streamlit:
#   docker run -p 8501:8501 sistema-experto-redes
#
# Correr la API REST en su lugar:
#   docker run -p 8000:8000 sistema-experto-redes \
#       uvicorn api:app --host 0.0.0.0 --port 8000

FROM python:3.12-slim

WORKDIR /app

# Herramientas de red que usan los sensores del motor de inferencia (ping)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501 8000

HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
