ARG BASEIMAGE=6.0.8.40

#########################
# 1. Base stage
########################################################################
FROM ctezlifrn/avaintegrationbase:$BASEIMAGE AS base

RUN uv pip install --system \
        django-compressor django-sass-processor


#########################
# 2. Build stage
########################################################################
FROM base AS build

COPY --chown=root:app src /app/src
WORKDIR /app/src

RUN python manage.py collectstatic --noinput -v 0 \
    && find /app/static -type d -name "__pycache__" -exec rm -rf {} + \
    && find /usr/local/lib/python3.14/site-packages/ -type d -name "__pycache__" -exec rm -rf {} + \
    && ls -l /app/static


#########################
# 3. Production stage
########################################################################
FROM base AS production

COPY --chown=root:app --from=build /app /app

USER app
EXPOSE 8000
WORKDIR /app/src
ENTRYPOINT []

CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn"]


#########################
# 4. Development stage (Ferramentas locais)
########################################################################
FROM base AS development

RUN uv pip install --system \
        black ruff doc8 pytest pytest-cov python-dotenv pytest-coverage-gate pytest-django \
        Werkzeug django-debug-toolbar debugpy ipython

WORKDIR /app/src
USER app
EXPOSE 8000
CMD  ["python", "manage.py", "runserver_plus", "0.0.0.0:8000"]
