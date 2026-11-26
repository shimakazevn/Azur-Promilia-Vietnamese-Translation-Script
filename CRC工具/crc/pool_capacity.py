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
    if limit < fixed_bytes + 4 * min_cap + 4:
        raise ValueError('No hash capacity fits original slot')

    hi = (limit - fixed_bytes - 4) // 4
    if max_cap is not None:
        hi = min(hi, max_cap)
    if hi < min_cap:
        raise ValueError('No hash capacity fits original slot')

    def used_bytes(cap: int) -> int:
        occupied = len({h % cap for h in unique_hashes})
        return fixed_bytes + 4 * cap + 4 * occupied

    lo = min_cap
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if used_bytes(mid) <= limit:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best is None:
        raise ValueError('No hash capacity fits original slot')

    # Search downward from best (plus small jitter margin) to find the largest fitting prime.
    start = min((limit - fixed_bytes - 4) // 4, best + 64)
    if max_cap is not None:
        start = min(start, max_cap)
    cand = start if (start & 1) else (start - 1)
    while cand >= min_cap:
        if is_prime(cand) and used_bytes(cand) <= limit:
            return cand
        cand -= 2

    if min_cap == 2 and used_bytes(2) <= limit:
        return 2
    raise ValueError('No hash capacity fits original slot')
