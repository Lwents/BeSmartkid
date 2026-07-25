import os
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
from dotenv import load_dotenv

# -------------------------------
# Base paths & environment
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------
# Static files
# -------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # nơi collectstatic sẽ gom các file tĩn

# -------------------------------
# Media files
# -------------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

load_dotenv(BASE_DIR / ".env")

def env_list(name, default=""):
    """Split comma-separated values into Python list"""
    value = os.getenv(name, default)
    return [x.strip() for x in value.split(",") if x.strip()]

# -------------------------------
# Core settings
# -------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-prod")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

DEFAULT_ALLOWED_HOSTS = [
    "api.smartedu.click",
    "smartedu.click",
    "www.smartedu.click",
    "localhost",
    "127.0.0.1",
]
DEFAULT_FRONTEND_ORIGINS = [
    "https://smartedu.click",
    "https://www.smartedu.click",
    "https://api.smartedu.click",
]

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*" if DEBUG else "") or (
    ["*"] if DEBUG else DEFAULT_ALLOWED_HOSTS
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS") or DEFAULT_FRONTEND_ORIGINS
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS") or DEFAULT_FRONTEND_ORIGINS
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Allow all origins in dev mode
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'cache-control',
    'pragma',
]

# -------------------------------
# Installed apps
# -------------------------------
INSTALLED_APPS = [
    # Django default
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third-party
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'rest_framework.authtoken',                                                                                                 

    # Project apps
    'custom_account',
    'school',
    'content',
    'activities',
    'assignments',
    'progress',
    'gamification',
    'ai_personalization',
    'events',
    'payments',
    'admin_api',
    'teacher_api',
    'student_api',

    # Allauth                                                                                                            
    'allauth',                                                                                                                  
    'allauth.account',                                                                                                                                                                                                     
    'allauth.socialaccount',                                                                                                    
    'allauth.socialaccount.providers.google',
    'dj_rest_auth', 
]

# -------------------------------
# Middleware
# -------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'infrastructure.middleware.GlobalExceptionMiddleware',
]

ROOT_URLCONF = 'backend.urls'
WSGI_APPLICATION = 'backend.wsgi.application'

# -------------------------------
# Templates
# -------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# -------------------------------
# Database
# -------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "elearning"),
        "USER": os.getenv("DB_USER", "elearning"),
        "PASSWORD": os.getenv("DB_PASSWORD", "123456"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# -------------------------------
# REST Framework / JWT
# -------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # 'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': "%Y-%m-%d %H:%M:%S",
    'USE_TZ': True,
    'EXCEPTION_HANDLER': 'infrastructure.exceptions.custom_exception_handler'
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# -------------------------------
# Authentication / User model
# -------------------------------
AUTH_USER_MODEL = 'custom_account.UserModel'


# -------------------------------
# Static & Media files
# -------------------------------
STATIC_URL = '/static/'
STATIC_SOURCE_DIR = BASE_DIR / 'static'
STATICFILES_DIRS = [STATIC_SOURCE_DIR] if STATIC_SOURCE_DIR.exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

USE_S3 = os.getenv("STORAGE_PROVIDER", "local").lower() == "s3"

if USE_S3:
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")

    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "ap-southeast-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or None
    AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN") or ""
    AWS_S3_ADDRESSING_STYLE = "virtual" if AWS_S3_CUSTOM_DOMAIN else "path"
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False

    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    elif AWS_S3_ENDPOINT_URL:
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/"
    elif AWS_S3_REGION_NAME == "us-east-1":
        MEDIA_URL = f"https://s3.amazonaws.com/{AWS_STORAGE_BUCKET_NAME}/"
    else:
        MEDIA_URL = f"https://s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_STORAGE_BUCKET_NAME}/"

LOG_DIR = BASE_DIR / 'runtime_logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------
# Email / SMTP
# -------------------------------
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@smartedu")

# -------------------------------
# Celery / Redis
# -------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", f"{REDIS_URL}/0")

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 1800
CELERY_TASK_SOFT_TIME_LIMIT = 1200

# -------------------------------
# Cache (Redis)
# -------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}

# -------------------------------
# AI / OpenAI
# -------------------------------
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# -------------------------------
# Payment gateways - MoMo
# -------------------------------
MOMO_PARTNER_CODE = os.getenv("MOMO_PARTNER_CODE", "")
MOMO_ACCESS_KEY = os.getenv("MOMO_ACCESS_KEY", "")
MOMO_SECRET_KEY = os.getenv("MOMO_SECRET_KEY", "")
MOMO_CREATE_ENDPOINT = os.getenv(
    "MOMO_CREATE_ENDPOINT",
    "https://test-payment.momo.vn/v2/gateway/api/create",
)
MOMO_POS_ENDPOINT = os.getenv(
    "MOMO_POS_ENDPOINT",
    "https://test-payment.momo.vn/v2/gateway/api/pos",
)
MOMO_PARTNER_NAME = os.getenv("MOMO_PARTNER_NAME", "SunEdu")
MOMO_STORE_ID = os.getenv("MOMO_STORE_ID", "SunEduStore")
MOMO_REDIRECT_URL = os.getenv("MOMO_REDIRECT_URL", "http://localhost:5173/payment/result")
MOMO_IPN_URL = os.getenv("MOMO_IPN_URL", "")
try:
    MOMO_MIN_CUSTOM_AMOUNT = Decimal(os.getenv("MOMO_MIN_CUSTOM_AMOUNT", "1000"))
except Exception:
    MOMO_MIN_CUSTOM_AMOUNT = Decimal("1000")

# -------------------------------
# Logging
# -------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'level': 'DEBUG', 'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'loggers': {
        'ai_personalization': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'DEBUG'},
    },
}

# -------------------------------
# Locale / Time
# -------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# -------------------------------
# Miscellaneous
# -------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://smartedu.click/')
PASSWORD_RESET_TIMEOUT = 600  # 10 minutes

# Upload limits (allow larger lesson/course video files)
# 300MB per file keeps teacher uploads practical without exhausting memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 300 * 1024 * 1024      # 300MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 1 * 1024 * 1024 * 1024 # 1GB

# HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
CORS_ALLOW_CREDENTIALS = True

# Cho allauth
SITE_ID = 1
AUTHENTICATION_BACKENDS = (                    
    # `allauth` specific authentication methods, such as login by e-mail                                                                                 
    'allauth.account.auth_backends.AuthenticationBackend',   

    # Needed to login by username in Django admin, regardless of `allauth`                                                                   
    'django.contrib.auth.backends.ModelBackend',                                                                                
)                                                                                                                               

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_HTTPONLY': False,

    'JWT_AUTH_REFRESH_COOKIE': 'refresh_token_cookie',
    'USER_DETAILS_SERIALIZER': 'custom_account.serializers.UserPublicOutputSerializer',
}

ACCOUNT_LOGIN_METHODS = {'username', 'email'}

ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'optional'
                                                                                                                                                                                                                                                                                        
ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'allauth.socialaccount.adapter.DefaultSocialAccountAdapter'

SOCIALACCOUNT_PROVIDERS = {                                                                                                     
    'google': {                                                                                                                 
        'SCOPE': [
            'profile',                                                                                                          
            'email',                                                                                                            
        ],                                                                                                                      
        'AUTH_PARAMS': {                                                                                                        
            'access_type': 'online',                                                                                            
        },                                                                                                                      
        # 'APP': {                                                                                                                
        #     'client_id': '{GOOGLE_CLIENT_ID}',                                                                               
        #     'secret': '{GOOGLE_CLIENT_SECRET}',                                                                                 
        # }                                                                                                                       
    }                                                                                                                           
}  
