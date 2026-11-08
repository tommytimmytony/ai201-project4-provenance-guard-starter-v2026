import os


bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = 1
threads = 2
timeout = 180
accesslog = "-"
errorlog = "-"


def post_fork(server, worker):
    """Load GPT-2 before the worker begins serving requests."""
    import detector

    server.log.info(detector.warm_up())

