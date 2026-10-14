def decode(data, invert_all=False):
    """ZX0 v2 decoder. First literal indicator bit is implicit. invert_all=True
    inverts the data bits of every gamma code (what the PyPI port writes);
    False inverts only the offset's high part (as I remember Einar's format)."""
    pos = 0; bitbuf = 0; bits = 0
    def rbit():
        nonlocal pos, bitbuf, bits
        if bits == 0:
            bitbuf = data[pos]; pos += 1; bits = 8
        bits -= 1
        return (bitbuf >> bits) & 1
    def gamma(inv, first=None):
        v = 1
        while True:
            if first is not None:
                b, first = first, None
            else:
                b = rbit()
            if b: return v
            v = (v << 1) | (rbit() ^ inv)
    out = bytearray(); last = 1
    plain = 1 if invert_all else 0
    n = gamma(plain)
    state = 'lit'
    while True:
        if state == 'lit':
            for _ in range(n):
                out.append(data[pos]); pos += 1
            state = 'afterlit'
        if state in ('afterlit', 'aftermatch'):
            if not rbit():
                if state == 'aftermatch':
                    n = gamma(plain); state = 'lit'; continue
                n = gamma(plain)
                for _ in range(n): out.append(out[-last])
                state = 'aftermatch'; continue
            state = 'newoffset'
        if state == 'newoffset':
            msb = gamma(1)
            if msb == 256: return bytes(out)
            byte = data[pos]; pos += 1
            last = (msb << 7) - (byte >> 1)
            n = gamma(plain, first=byte & 1) + 1
            for _ in range(n): out.append(out[-last])
            state = 'aftermatch'
