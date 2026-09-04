# Top-K from a stream.
#
# "Stream" is the whole point: the data doesn't fit in memory and doesn't end,
# so you can't sort it -- you maintain the answer incrementally as elements arrive.
# This is the shape of most SRE dashboards/alerts:
#   - top-K talkers by bandwidth on an interface (iftop)
#   - top-K endpoints by error count in the last 5 min
#   - top-K hot keys hammering a cache (noisy-neighbour / hot-shard detection)
#   - top-K slowest queries by p99
#
# There are TWO distinct problems hiding under one name -- know which you're asked:
#
#   (A) Top-K by VALUE      -> the K largest values seen so far (e.g. Kth largest
#                              in a stream of numbers). Min-heap of size K.
#   (B) Top-K by FREQUENCY  -> the K most-frequent items (e.g. hottest cache keys).
#                              Hashmap of counts + heap. Count-Min Sketch at scale.
#
# Requirements:
#   1. KthLargestInStream(k, nums): add(val) -> the current Kth largest. O(log k)/add.
#   2. top_k_frequent(stream, k):   the K most frequent items in an iterable.
#
# Be ready to defend out loud:
#   - WHY a min-heap of size k, not a max-heap, for "K largest"? (the counterintuitive bit)
#   - Time complexity of add() and of the frequency version.
#   - Scale follow-up: 10M distinct keys/sec across a fleet, counts don't fit in RAM.
#     Now what? -> Count-Min Sketch (approximate counts, fixed memory) + heap of heavy hitters.
#
# Key one-liners:
#   - "K LARGEST -> min-heap of size k: the heap root is the SMALLEST of your current
#      top-k, i.e. the kth largest. A new value only matters if it beats the root, so
#      you compare-and-maybe-evict in O(log k). A max-heap would put the global max on
#      top, which is the wrong thing to evict against."
#   - "Top-K by frequency = O(n) count + O(n log k) heap. nlargest/heap of size k beats
#      a full sort (O(n log n)) when k << n."
#   - "At fleet scale you can't store a counter per key. Count-Min Sketch gives
#      approximate counts in fixed memory (over-counts, never under-counts) and you
#      track the heavy hitters in a small heap on the side."

import heapq
from collections import Counter


# --- 1. Kth largest in a stream (top-K by VALUE) ---------------------------

class KthLargestInStream:
    def __init__(self, k, nums):
        self.k = k
        self.min_heap = list(nums)
        heapq.heapify(self.min_heap)
        while len(self.min_heap) > k:
            heapq.heappop(self.min_heap)

    def add(self, val):
        heapq.heappush(self.min_heap, val)
        if len(self.min_heap) > self.k:
            heapq.heappop(self.min_heap)
    
        return self.min_heap[0] # root is the kth largest element



# --- 2. Top-K most frequent (top-K by FREQUENCY) ---------------------------

def top_k_frequent(stream, k):
    counts = Counter(stream)
    return [item for item,_ in counts.most_common(k)]
    # O(n) to count + O(n log k) to select


if __name__ == "__main__":
    # Kth largest: k=3 means "3rd largest seen so far".
    kth = KthLargestInStream(3, [4, 5, 8, 2])
    print("add 3 ->", kth.add(3))   # 4
    print("add 5 ->", kth.add(5))   # 5
    print("add 10 ->", kth.add(10)) # 5
    print("add 9 ->", kth.add(9))   # 8
    print("add 4 ->", kth.add(4))   # 8

    # Top-K frequent: hottest cache keys.
    keys = ["a", "b", "a", "c", "a", "b", "d", "b", "a"]
    print("top 2 frequent ->", top_k_frequent(keys, 2))  # ['a', 'b']
