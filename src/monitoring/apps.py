from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    name = "monitoring"

    def ready(self):
        from .http import install_requests_monitoring

        install_requests_monitoring()
