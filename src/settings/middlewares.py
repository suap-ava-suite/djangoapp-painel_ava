# -*- coding: utf-8 -*-
from settings.indebug import DEBUG

# Middleware
MIDDLEWARE = [
    "monitoring.middleware.HTTPMetricsMiddleware",
    "painel.middleware.ExceptionMiddleware",
    "painel.middleware.GoToHTTPSMiddleware",  # <-
    "painel.middleware.XForwardedForMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "painel.middleware.AuthMobileUserMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

if not DEBUG:
    MIDDLEWARE.insert(4, "whitenoise.middleware.WhiteNoiseMiddleware")
