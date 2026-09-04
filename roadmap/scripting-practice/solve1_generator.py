import re
import json
from collections import Counter

# 10.0.1.5 - - [07/Jun/2026:10:00:01 +0000] "GET /api/health HTTP/1.1" 200 142 0.012

pattern = re.compile(r'^(\S+).*"(\S+) (\S+) HTTP[^"]*" (\d+)')


# The generator: read lines, yield one parsed row at a time, skip junk.
# This is the whole trick — `yield` instead of building a list.
def parse_lines(filepath):
    with open(filepath) as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            ip, method, route, status = m.group(1), m.group(2), m.group(3), m.group(4)
            yield ip, route, status          # hand one row back, then pause here


def parse(filepath):
    status_counts = Counter()
    ip_counts = Counter()
    route_500s = Counter()
    valid_requests = 0

    for ip, route, status in parse_lines(filepath):   # pull rows one at a time
        valid_requests += 1
        status_counts[status] += 1
        ip_counts[ip] += 1
        if status.startswith('5'):
            norm = re.sub(r'/\d+', '/{id}', route)
            route_500s[norm] += 1

    return {
        'valid_requests': valid_requests,
        'status_counts': status_counts.most_common(),
        'route_500s': route_500s.most_common(3),
        'ip_counts': ip_counts.most_common(1),
    }


print(json.dumps(parse("access.log"), indent=2))
