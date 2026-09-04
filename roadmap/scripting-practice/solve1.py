import re
from collections import Counter

# 10.0.1.5 - - [07/Jun/2026:10:00:01 +0000] "GET /api/health HTTP/1.1" 200 142 0.012

def parse(filepath):
    with open(filepath) as f:
        pattern = re.compile(r'^(\S+).*"(\S+) (\S+) HTTP[^"]*" (\d+)')
        status_counts = Counter()
        ip_counts = Counter()
        route_500s = Counter()
        valid_requests = 0

        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            valid_requests += 1
            ip, _method, route, status = m.group(1), m.group(2), m.group(3), m.group(4) 
            status_counts[status] += 1
            if status.startswith('5'):
                norm = re.sub(r'/\d+', '/{id}', route)
                route_500s[norm] += 1
            ip_counts[ip] += 1
    
    return {
        'valid_requests': valid_requests,
        'status_counts': status_counts.most_common(),
        'route_500s': route_500s.most_common(3),
        'ip_counts': ip_counts.most_common(1)
    }


import json
print(json.dumps(parse("access.log"), indent=2))