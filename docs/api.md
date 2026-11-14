# API reference

Everything is importable from `pyribbon`: `RibbonFilter`, `RibbonError`, `ConstructionError`, `FormatError`, `Key` and
`__version__`. The package ships type stubs and is checked with `mypy --strict`.

## `Key`

The type of a key: `bytes | bytearray | memoryview | str | int`. Bytes-like keys are hashed by content, `str` as UTF-8, and `int`
at any size. `b"a"`, `"a"` and `97` are three different keys. Any other type raises `TypeError`. See [usage](usage.md#keys).

## `RibbonFilter`

An immutable approximate-membership filter (a standard ribbon filter). A key that was in the build set is always found. A key
that was not is reported as present with probability about `2**-fp_bits`. It is safe to query from many threads.

```python
RibbonFilter(keys, *, fp_bits=8, seed=0, overhead=None, max_attempts=32)
```

Builds a filter from `keys`.

| Parameter | Meaning |
|---|---|
| `keys` | An iterable of keys, or a 1-D integer buffer such as an `array.array` or a numpy array. A buffer is hashed in C and gives the same filter as the same ints passed one by one. A lone `str`, `bytes`, `bytearray` or `memoryview` is refused, because iterating it would silently hash its characters. |
| `fp_bits` | Fingerprint bits per key, 1 to 32. The false-positive rate is about `2**-fp_bits`. Default 8. |
| `seed` | The seed the build starts from, `0 <= seed < 2**64`. The same keys and seed give the same bytes. Default 0. |
| `overhead` | Extra rows as a fraction of the key count, 0 to 4. `None` picks a value that makes a build succeed about 97% of the time at that size. |
| `max_attempts` | How many times a failed build is retried with another seed and a slightly larger table, 1 to 255. Default 32. |

Raises `ConstructionError` if every attempt fails, `ValueError` for an argument out of range, `TypeError` for a key of an
unsupported type, and `MemoryError` if the build cannot allocate. Duplicate keys are harmless and counted by `len()`.
Builds release the GIL.

### Querying

| Member | Meaning |
|---|---|
| `key in f` | `True` if `key` is possibly in the set, `False` if it is definitely not. |
| `f.contains_many(keys)` | A `list[bool]`, one answer per key. `keys` is an iterable of keys or a 1-D integer buffer, which is much faster. Large batches release the GIL while probing. |
| `len(f)` | The number of keys the filter was built from, duplicates included. |

### Size

| Member | Meaning |
|---|---|
| `f.size_in_bytes` | Length of the serialized filter in bytes, header included. |
| `f.bits_per_key` | `8 * size_in_bytes / len(f)`, or `0.0` for an empty filter. |
| `f.fp_bits` | The fingerprint bits the filter was built with. |

### Saving and loading

| Member | Meaning |
|---|---|
| `f.to_bytes()` | The filter in the versioned, little-endian serialization format (a 64-byte header with a magic number and checksums, then the rows). |
| `RibbonFilter.from_buffer(buffer, *, verify=True)` | Views serialized bytes without copying them. `buffer` must be C-contiguous and must not change while the filter exists. With `verify=False` the payload checksum, which reads every byte, is skipped. The header is always checked. Raises `FormatError` on bad input. |
| `pickle`, `copy` | Both work. |

The loader treats its input as untrusted: a truncated, corrupted or hostile buffer raises `FormatError` and is never read
outside its bounds. The checksums catch accidental damage only. They are not a MAC and do not protect against tampering.

## Exceptions

| Exception | Base classes | Raised when |
|---|---|---|
| `RibbonError` | `Exception` | The base of every error below. |
| `ConstructionError` | `RibbonError` | No filter could be built: every attempt failed. A build never returns a broken filter. |
| `FormatError` | `RibbonError`, `ValueError` | Serialized data is invalid or corrupt. |

Bad arguments raise the built-in `ValueError` or `TypeError`, not a pyribbon error.
