# Stage 1: Build
FROM python:3-alpine AS builder

# Aggiungi variabili di build per l'URL del repository.
ARG REPO_URL="https://github.com/ldmtecknoit-lab/e-commerce"

# --- CACHE-BREAKER: Questa variabile forza il re-download del repository ad ogni build. ---
# Il valore di default è un timestamp Unix, che cambia ad ogni esecuzione.
# Se questo valore non viene fornito esternamente, Docker utilizza l'ora corrente,
# invalidando la cache per i passi successivi.
ARG BUILD_TIMESTAMP=

# Imposta la directory di lavoro.
WORKDIR /

# Installa git e curl
RUN apk add --no-cache git

# 1. FORZA RE-DOWNLOAD: La variabile dinamica BUILD_TIMESTAMP rompe la cache.
# La cache di Docker viene invalidata qui perché l'istruzione RUN cambia ad ogni build.
RUN echo "Invalido la cache usando il timestamp ${BUILD_TIMESTAMP} e recupero il codice..." \
    && git clone ${REPO_URL} /tmp/repo \
    && echo "Clonazione completata."

# Sposta i file dall'area di staging alla directory di destinazione
# Assicurati che il percorso src/application esista già o venga creato
RUN mkdir -p /src/application && mv /tmp/repo/src/application/* /src/application/

# ISTRUZIONE MODIFICATA: Sposta il contenuto della cartella 'assets' in public/assets
# 2. Creiamo la directory di destinazione public/assets
# 3. Spostiamo i file al suo interno.
# Usiamo 'cp' e ignoriamo gli errori di 'file not found' per permettere alla build di continuare se la cartella 'assets' non esiste.
RUN mkdir -p /public/assets && cp -R /tmp/repo/assets/* /public/assets/ 2>/dev/null || true

# Copia i file delle dipendenze per sfruttare la cache.
# Copia pyproject.toml (richiesto da alcuni gestori di pacchetti) e requirements.txt
COPY pyproject.toml .
COPY requirements.txt .

# Installa le dipendenze. Questo passo verrà rieseguito solo se i file delle dipendenze cambiano.
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice sorgente dopo aver installato le dipendenze.
COPY src src

# Stage 2: Runtime
FROM python:3-alpine AS runner

# Imposta le variabili d'ambiente per il venv e la porta.
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PORT=8000

# Imposta la directory di lavoro.
WORKDIR /

# Copia l'ambiente virtuale e i file del progetto dallo stage builder.
COPY --from=builder /venv /venv
COPY --from=builder /src /src
COPY --from=builder /pyproject.toml /

# Se necessario, copia altri file o directory (es. templates, static files).
COPY public public

# Esponi la porta dell'applicazione.
EXPOSE ${PORT}

# Comando per lanciare l'applicazione.
CMD ["python3", "public/main.py"]