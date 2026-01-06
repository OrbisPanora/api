FROM python:3.12.5-slim

WORKDIR /app

COPY requirements.txt ./
COPY ./orbispanora_lib-1.0.0-py3-none-any.whl ./

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/kubernetes/iut-inf63-projets-etudiants-orbispanora/orbispanora-api"]
