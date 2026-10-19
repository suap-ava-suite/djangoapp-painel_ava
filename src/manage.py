#!/usr/bin/env python
import logging
import os
import sys
import time

import psycopg

from settings.databases import DATABASES  # noqa: F401
from settings.indebug import DEBUG, TESTING_MODE  # noqa: F401


def _wait_db(timeout: float = 60.0, interval: float = 3.0) -> None:
    db = DATABASES["default"]
    host = db["HOST"]
    port = db["PORT"]
    dbname = db["NAME"]
    user = db["USER"]
    password = db["PASSWORD"]

    deadline = time.monotonic() + timeout
    while True:
        try:
            psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password).close()
            return
        except psycopg.OperationalError as e:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Banco {host}:{port}/{dbname} não respondeu em {timeout:.0f}s: {e}") from e
            logging.warning(f"Aguardando o banco {host}:{port}/{dbname} subir: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("ops!") from exc

    if len(sys.argv) > 1 and sys.argv[1] in ["runserver", "runserver_plus"]:
        _wait_db()
        # execute_from_command_line([sys.argv[0], "collectstatic", "--noinput"])
        execute_from_command_line([sys.argv[0], "migrate"])

        if DEBUG:
            try:
                import debugpy

                debugpy.listen(("0.0.0.0", 5678))  # noqa S104
                # debugpy.wait_for_client()
            except Exception as e:
                logging.error(e)

    execute_from_command_line(sys.argv)
