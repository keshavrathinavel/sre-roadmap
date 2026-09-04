# Build an LRU cache with a fixed capacity. Both operations must be O(1).
#
#   get(key)        -> return value if present, else -1.
#                      A get COUNTS AS USE: the key becomes most-recently-used.
#   put(key, value) -> insert or update. If at capacity, evict the
#                      least-recently-used key BEFORE inserting the new one.
#
# Approach: dict + doubly linked list (from scratch, no OrderedDict).
#   - dict maps key -> node, for O(1) lookup.
#   - doubly linked list keeps usage order: MRU at one end, LRU at the other.
#   - on get/put: move the touched node to the MRU end.
#   - on eviction: pop the node at the LRU end (and delete it from the dict).
#
# Trick that kills edge cases: use two sentinel/dummy nodes, `head` and `tail`,
# that always exist. Real nodes live between them. Then add/remove never has to
# check for None neighbours -- there's always a node on each side.
#
#   head(dummy) <-> [MRU] <-> ... <-> [LRU] <-> tail(dummy)
#
# Follow-up (do after the base works): add TTL -- entries expire N seconds
# after being written; an expired entry on get() is a miss + should be removed.

import time


class Node:
    def __init__(self, key, val, expiry: float) -> None:
        self.key, self.val, self.expiry = key, val, expiry
        self.next = self.prev = None

class LRU:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.cache = {} # map key to Node object
        self.ttl = 5 # 5s 

        self.head, self.tail = Node(0,0,0), Node(0,0,0)
        self.head.next, self.tail.prev = self.tail, self.head

    def insert(self, node: Node):
        prevnode = self.tail.prev
        prevnode.next = self.tail.prev = node
        node.next, node.prev = self.tail, prevnode

    def remove(self, node: Node):
        prevnode, nextnode = node.prev, node.next
        prevnode.next, nextnode.prev = nextnode, prevnode

    def get(self, key: int):
        # getting a key, makes it MRU - so it has to be on the right side now 
        # remove wherever it is from linked list, and insert on right side
        if key in self.cache:
            node = self.cache[key]
            if time.monotonic() > node.expiry:                
                self.remove(self.cache[key])
                del self.cache[key]
                return -1
            self.remove(self.cache[key])
            self.insert(self.cache[key])
            return self.cache[key].val
        return -1

    def put(self, key: int, value: int):
        expiry = time.monotonic() + self.ttl
        if key in self.cache:
            self.remove(self.cache[key])
        self.cache[key] = Node(key, value, expiry)
        self.insert(self.cache[key])

        if len(self.cache) > self.capacity:
            lru = self.head.next
            self.remove(lru)
            del self.cache[lru.key]


if __name__ == "__main__":
    c = LRU(2)
    c.put(1, 1)
    print(c.get(1))      # 1   (fresh)
    time.sleep(6)        # TTL is 5s
    print(c.get(1))      # -1  (expired)