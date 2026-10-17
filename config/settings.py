"""Django settings. Secrets and API credentials come from environment / .env only."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Ensure socket and dnspython resolve Atlas hosts via IPv4 (Atlas clusters do not support IPv6/NAT64)
import socket
_orig_gai = socket.getaddrinfo

def _ipv4_preferring_gai(host, port, family=0, type=0, proto=0, flags=0):
    try:
        res = _orig_gai(host, port, family, type, proto, flags)
        if host and "mongodb.net" in str(host):
            v4 = [r for r in res if r[0] == socket.AF_INET]
            if v4:
                return v4
        return res
    except Exception:
        return _orig_gai(host, port, family, type, proto, flags)

socket.getaddrinfo = _ipv4_preferring_gai

try:
    import dns.resolver
    _res = dns.resolver.get_default_resolver()
    for _ns in ["8.8.8.8", "1.1.1.1"]:
        if _ns not in _res.nameservers:
            _res.nameservers.append(_ns)
except Exception:
    pass

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
if DEBUG and "*" not in ALLOWED_HOSTS:
    for host in ("testserver", "localhost", "127.0.0.1"):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_NAME = os.environ.get("MONGODB_NAME", "flight_portal").strip()
USE_MONGODB = os.environ.get("USE_MONGODB", "1").lower() in ("1", "true", "yes")

if USE_MONGODB and MONGODB_URI:
    import django.contrib.admin.apps
    import django.contrib.auth.apps
    import django.contrib.contenttypes.apps

    django.contrib.auth.apps.AuthConfig.default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    django.contrib.contenttypes.apps.ContentTypesConfig.default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    django.contrib.admin.apps.AdminConfig.default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"

    INSTALLED_APPS = [
        "django_mongodb_backend",
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "flights",
    ]
else:
    INSTALLED_APPS = [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "flights",
    ]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_NAME = os.environ.get("MONGODB_NAME", "flight_portal").strip()
USE_MONGODB = os.environ.get("USE_MONGODB", "1").lower() in ("1", "true", "yes")

if USE_MONGODB and MONGODB_URI:
    DATABASES = {
        "default": {
            "ENGINE": "django_mongodb_backend",
            "HOST": MONGODB_URI,
            "NAME": MONGODB_NAME,
        }
    }
    DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
    DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
    MIGRATION_MODULES = {
        "admin": "mongo_migrations.admin",
        "auth": "mongo_migrations.auth",
        "contenttypes": "mongo_migrations.contenttypes",
        "flights": "mongo_migrations.flights",
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
    DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "flight-portal"}}

# ---- Live flight API (server-side only) ----
# Provider adapter: ixigo | aerodatabox | aviationstack
FLIGHT_API_PROVIDER = os.environ.get("FLIGHT_API_PROVIDER", "ixigo").lower()
FLIGHT_API_KEY = os.environ.get("FLIGHT_API_KEY", "")
FLIGHT_API_AUTH_STYLE = os.environ.get("FLIGHT_API_AUTH_STYLE", "rapidapi").lower()
FLIGHT_API_BASE_URL = os.environ.get("FLIGHT_API_BASE_URL", "")
FLIGHT_API_TIMEOUT = float(os.environ.get("FLIGHT_API_TIMEOUT", "12"))
FLIGHT_API_CACHE_SECONDS = int(os.environ.get("FLIGHT_API_CACHE_SECONDS", "30"))
FLIGHT_AUTO_REFRESH_SECONDS = max(30, int(os.environ.get("FLIGHT_AUTO_REFRESH_SECONDS", "60")))
SITE_NAME = os.environ.get("SITE_NAME", "Airvoyage")

