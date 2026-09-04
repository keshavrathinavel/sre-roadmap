"""
=============================================================================
 SRE SCRIPTING PRACTICE 2  (log parsing: time-bucketing + percentiles)
=============================================================================

Log format (Apache/nginx-ish combined). One request per line:

  10.0.2.9 - - [07/Jun/2026:10:03:02 +0000] "GET /api/orders HTTP/1.1" 500 0 1.204
  <ip>     - - [<timestamp>            ] "<method> <route> <proto>" <status> <bytes> <latency_s>

Some lines are malformed and MUST be skipped without crashing.

-----------------------------------------------------------------------------
 PART 1  — Per-minute health breakdown   (write this first)
-----------------------------------------------------------------------------
 Return, for each minute bucket (key = "HH:MM"), a dict with:
     - total:   number of valid requests in that minute
     - errors:  number of 5xx responses in that minute   (500-599)
     - error_rate: errors / total, rounded to 2 decimals

 Then print any minute whose error_rate > 0.5  -> these are "incident windows".

-----------------------------------------------------------------------------
 PART 2  — Latency p95 per route  (do this only after Part 1 works)
-----------------------------------------------------------------------------
 For each route (normalize numeric path segments: /api/users/42 -> /api/users/{id}),
 compute the p95 latency in seconds. Print routes sorted by p95 descending.

 p95 = the value at index ceil(0.95 * n) - 1 of the sorted latency list
       (nearest-rank method; don't pull in numpy).

=============================================================================
"""

import re
from collections import defaultdict


def parse(filepath):
    with open(filepath) as f:
        # need to pick key - HH:MM out of each line
        # from each line, group those with 2XX, group those with 5XX, and counter_5xx/total_requests; group = list
        # Whichever HH:MM's value has error_rate > 0.5, print the key

        # PART 1
        pattern = re.compile(r'\d{4}:(\d{2}:\d{2}):\d{2}.*?" (\d{3})')
        stats_per_min = defaultdict(lambda: {'total_requests': 0, 'counter_5xx': 0})

        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            time, status = m.group(1), int(m.group(2))
            stats_per_min[time]['total_requests'] += 1
            if 500 <= status <= 599:
                stats_per_min[time]['counter_5xx'] += 1            
        
        for minute, bucket in stats_per_min.items():
            bucket['error_rate'] = round(bucket['counter_5xx'] / bucket['total_requests'], 2) # type: ignore
            if bucket['error_rate'] > 0.5:
                print(minute)

        
        # PART 2
        # 10.0.2.9 - - [07/Jun/2026:10:03:02 +0000] "GET /api/orders HTTP/1.1" 500 0 1.204
    with open(filepath) as f:
        pattern2 = re.compile(r'.*?"\S+ (\S+) \S+" \d+ \d+ (\d+\.\d+)')
        latencies = defaultdict(list)
        for line in f:
            m = pattern2.match(line)
            if not m:
                continue
            route, latency = m.group(1), float(m.group(2))
            norm = re.sub(r'/\d+', '{id}', route)
            latencies[norm].append(latency)
        
        print(latencies)
        # No need to do the math, we wanted to learn parsing and parsing, we did.
            

    pass


if __name__ == "__main__":
    parse("access2.log")
