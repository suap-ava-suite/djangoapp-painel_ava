import multiprocessing
import os

from sc4py.env import env_as_bool

wsgi_app = "wsgi:application"
bind_port = os.getenv("VIRTUAL_PORT", "8000")
bind = f"0.0.0.0:{bind_port}"
default_web_concurrency = multiprocessing.cpu_count() * int(os.getenv("WORKER_PER_CPU", 2)) + 1
workers = int(os.getenv("WEB_CONCURRENCY", default_web_concurrency))
worker_class = os.getenv("WORKER_CLASS", "sync")
worker_tmp_dir = os.getenv("WORKER_TMP_DIR", "/dev/shm")  # noqa S108
loglevel = "info"
timeout = int(os.getenv("WORKER_TIMEOUT", 120))
error_logfile = "-"
errorlog = "-"
accesslog = env_as_bool("DJANGO_DEBUG", False) and "-" or None
access_logfile = env_as_bool("DJANGO_DEBUG", False) and "-" or None
capture_output = False
syslog = False
logger_class = "gunicorn.glogging.Logger"


def child_exit(server, worker):
    from prometheus_client import multiprocess

    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(worker.pid)
