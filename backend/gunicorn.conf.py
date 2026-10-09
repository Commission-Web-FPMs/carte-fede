# Loaded by Gunicorn from /app. Request targets and headers never enter access logs.
logger_class = "app.safe_logging.SafeGunicornLogger"
access_log_format = "%(m)s %(s)s %(L)s"
