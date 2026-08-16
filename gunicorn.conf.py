"""Production Gunicorn settings for long-running AI lesson generation."""

# Both AI providers are raced with a 60-second deadline. Leave enough room for
# validation and Supabase persistence after the winning response arrives.
timeout = 90
graceful_timeout = 30
keepalive = 5
