# Write a function retry_with_backoff that calls a flaky function and retries it when it fails (raises an exception).
# The retries should back off exponentially, with jitter, and give up after a max number of attemps.

# Requirements:

# Take the function to call, a max_retries count, and a base_delay (seconds).
# On attempt n (starting at 0), wait roughly base_delay * 2**n seconds before the next try — but add jitter so all clients don't retry in sync.
# Cap the delay at some max_delay so it doesn't grow unbounded.
# If it succeeds, return the result immediately.
# If all attempts are exhausted, re-raise the last exception (don't swallow it).
# Print each attempt so you can see the backoff working.

# Expected behavior: you should see ~3 failed attempts with increasing (but jittered) sleeps,
# then Final result: success!.

import random
import time


attempt_counter = {"n": 0}

def flaky_call():
    attempt_counter["n"] += 1
    if attempt_counter["n"] < 4:
        raise ConnectionError(f"failed (call #{attempt_counter['n']})")
    return "success!"

def retry_with_backoff(func, max_retries=5, base_delay=0.5, max_delay=10):
    last_exc = None
    for attempt in range(max_retries):
        try: 
            print(f"Attempt: {attempt} at calling {func.__name__}")
            return func()
        except Exception as e: # ideally, use a more specific exception
            last_exc = e
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                total_delay = random.uniform(0, delay)
                print(f"Failed: {e}. Retrying {func.__name__} call after {total_delay:.2f}s...")
                time.sleep(total_delay)
    raise last_exc


result = retry_with_backoff(flaky_call, max_retries=5, base_delay=0.5, max_delay=10)
print("Final result:", result)
