import random
import time

import requests


def retryable(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    code = getattr(exc, "code", None)
    return status in {429, 500, 502, 503, 504} or code in {429, 500, 502, 503, 504}


def retry(operation, on_retry=lambda: None, attempts=4, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if attempt == attempts - 1 or not retryable(exc):
                raise
            on_retry()
            sleep(min(8, 0.5 * 2**attempt) + random.uniform(0, 0.25))
