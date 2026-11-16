#!/bin/sh
set -eu

# Diretório exclusivo deste master, compartilhado somente por seus workers.
PROMETHEUS_MULTIPROC_DIR=$(mktemp -d /tmp/painel-metrics.XXXXXX)
export PROMETHEUS_MULTIPROC_DIR
python manage.py migrate --noinput
exec gunicorn
