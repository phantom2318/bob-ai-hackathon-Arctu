"""
Django settings for Weatheria project.

Environment variables are read from the process environment (or a .env file
loaded by the developer before starting the server).  See src/.env.example
for the full list of supported variables and their defaults.
"""

from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent

# Absolute path to archive.zip at the workspace root (3 levels above BASE_DIR).
# Used by the satellite prediction endpoint's zip fallback mode.
ML_ZIP_PATH = BASE_DIR.parent.parent.parent / "archive.zip"

# Add backend directory to sys.path to allow module imports
sys.path.insert(0, str(BASE_DIR))

# ── Security ──────────────────────────────────────────────────────────────────
# Read from environment; fall back to the insecure dev key so runserver works
# out-of-the-box.  Any non-local deployment MUST set DJANGO_SECRET_KEY.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-weatheria-power-outage-advisor-key",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").strip().lower() not in ("false", "0", "no")

# Accept a comma-separated list: DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
_raw_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party applications
    'corsheaders',
    'rest_framework',
    # Local applications
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── CORS ──────────────────────────────────────────────────────────────────────
# CORS_ALLOW_ALL_ORIGINS=True is the default for local HTML file:// testing.
# Set DJANGO_CORS_ALLOW_ALL_ORIGINS=False and supply a comma-separated
# DJANGO_CORS_ALLOWED_ORIGINS list for staging / production.
CORS_ALLOW_ALL_ORIGINS = os.environ.get(
    "DJANGO_CORS_ALLOW_ALL_ORIGINS", "True"
).strip().lower() not in ("false", "0", "no")

if not CORS_ALLOW_ALL_ORIGINS:
    _raw_origins = os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "")
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
