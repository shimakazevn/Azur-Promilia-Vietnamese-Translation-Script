# -*- coding: utf-8 -*-
"""VStringPool 重建哈希表最大素数桶容量求解器。"""


def is_prime(n: int) -> bool:
    """Deterministic Miller-Rabin primality test for 64-bit / 32-bit integers."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while (d & 1) == 0:
        d >>= 1
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if a >= n:
            break
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True


def choose_max_prime_capacity(hashes, hash_total: int, min_padding: int = 4, min_cap: int = 65521, max_cap: int = None) -> int:
    """在不超过 hash_total - min_padding 的前提下，求解能容纳全部哈希项的最大素数桶容量。"""
    entry_count = len(hashes)
    unique_hashes = tuple(set(hashes))
    limit = hash_total - min_padding
    fixed_bytes = 24 + 12 * entry_count
    minimum_occupied = 1 if unique_hashes else 0
    if min_cap < 2 or limit < fixed_bytes + 4 * min_cap + 4 * minimum_occupied:
        raise ValueError('No hash capacity fits original slot')

    hi = (limit - fixed_bytes) // 4 - minimum_occupied
    if max_cap is not None:
        hi = min(hi, max_cap)
    if hi < min_cap:
        raise ValueError('No hash capacity fits original slot')

    def fits(cap: int) -> bool:
        allowed_occupied = (limit - fixed_bytes) // 4 - cap
        if allowed_occupied >= len(unique_hashes):
            return True
        occupied = set()
        # Reject over-budget candidates early, without scanning every hash.
        for start in range(0, len(unique_hashes), 256):
            occupied.update(h % cap for h in unique_hashes[start:start + 256])
            if len(occupied) > allowed_occupied:
                return False
        return True

    # Occupied bucket counts are not monotonic in cap. Check primes from the
    # proven upper bound downwards so a fitting interval cannot be discarded.
    cand = hi if (hi & 1) else (hi - 1)
    while cand >= min_cap:
        if is_prime(cand) and fits(cand):
            return cand
        cand -= 2

    if min_cap == 2 and hi >= 2 and fits(2):
        return 2
    raise ValueError('No hash capacity fits original slot')
