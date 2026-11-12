/*
 * _ribbon.c - CPython binding for the pyribbon C core. Thin by design: key conversion, argument checking,
 * GIL handling and error mapping live here; everything algorithmic is in core/.
 *
 * Built with the limited API (abi3, floor 3.11) where possible; the same source builds non-limited for 3.10
 * (Py_buffer joined the stable ABI in 3.11). See DESIGN.md section 6.
 *
 * GIL: key hashing touches Python objects and runs with the GIL held. rb_build and large rb_contains_many
 * batches run without it, touching only plain C memory (no Python objects, refcounts or PyMem allocators).
 * Single-key __contains__ never releases the GIL: save/restore costs more than the ~30 ns of work.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdlib.h>
#include <string.h>

#include "ribbon.h"

#define BATCH_NOGIL_THRESHOLD 1024 /* contains_many releases the GIL from this many keys on */

typedef struct {
  PyObject *ribbon_error;
  PyObject *construction_error;
  PyObject *format_error;
  PyTypeObject *filter_type;
} ModState;

typedef struct {
  PyObject_HEAD
  rb_filter *filter;
  Py_buffer view; /* the exporter of the serialized bytes when created by from_buffer (zero copy) */
  int has_view;
} FilterObject;

/* New reference to the type's name as a str (tp_name is not visible in the limited API). */
static PyObject *type_name_of(PyObject *obj) {
#if PY_VERSION_HEX >= 0x030B0000
  return PyType_GetName(Py_TYPE(obj));
#else
  return PyUnicode_FromString(Py_TYPE(obj)->tp_name);
#endif
}

static ModState *state_of_type(PyTypeObject *tp) {
  PyObject *module = PyType_GetModule(tp);
  return module ? (ModState *)PyModule_GetState(module) : NULL;
}

/* ------------------------------------------------------------------------------------------------- */
/* key conversion (DESIGN.md section 3.1)                                                            */

static int hash_int(PyObject *value, uint64_t seed, uint64_t *out) {
  int overflow = 0;
  long long x = PyLong_AsLongLongAndOverflow(value, &overflow);
  if (x == -1 && PyErr_Occurred()) return -1;
  if (!overflow) {
    *out = rb_hash_i64((int64_t)x, seed);
    return 0;
  }
  /* outside int64: little-endian two's complement of length bit_length // 8 + 1, hashed as bytes */
  int rc = -1;
  PyObject *bits = PyObject_CallMethod(value, "bit_length", NULL);
  if (!bits) return -1;
  Py_ssize_t nbits = PyLong_AsSsize_t(bits);
  Py_DECREF(bits);
  if (nbits < 0 && PyErr_Occurred()) return -1;
  Py_ssize_t length = nbits / 8 + 1;
  PyObject *method = PyObject_GetAttrString(value, "to_bytes");
  PyObject *args = method ? Py_BuildValue("(ns)", length, "little") : NULL;
  PyObject *kwargs = args ? Py_BuildValue("{s:O}", "signed", Py_True) : NULL;
  PyObject *encoded = kwargs ? PyObject_Call(method, args, kwargs) : NULL;
  if (encoded) {
    char *buf = NULL;
    Py_ssize_t len = 0;
    if (PyBytes_AsStringAndSize(encoded, &buf, &len) == 0) {
      *out = rb_hash_bytes(buf, (size_t)len, seed, RB_KEY_BIGINT);
      rc = 0;
    }
  }
  Py_XDECREF(encoded);
  Py_XDECREF(kwargs);
  Py_XDECREF(args);
  Py_XDECREF(method);
  return rc;
}

/* 0 on success, -1 with an exception set. */
static int key_hash(PyObject *key, uint64_t seed, uint64_t *out) {
  if (PyLong_Check(key)) return hash_int(key, seed, out);
  if (PyUnicode_Check(key)) {
    Py_ssize_t len = 0;
    const char *utf8 = PyUnicode_AsUTF8AndSize(key, &len); /* strict: a lone surrogate raises UnicodeEncodeError */
    if (!utf8) return -1;
    *out = rb_hash_bytes(utf8, (size_t)len, seed, RB_KEY_STR);
    return 0;
  }
  if (PyBytes_Check(key)) {
    char *buf = NULL;
    Py_ssize_t len = 0;
    if (PyBytes_AsStringAndSize(key, &buf, &len) < 0) return -1;
    *out = rb_hash_bytes(buf, (size_t)len, seed, RB_KEY_BYTES);
    return 0;
  }
  if (PyByteArray_Check(key) || PyObject_TypeCheck(key, &PyMemoryView_Type)) {
    Py_buffer view;
    if (PyObject_GetBuffer(key, &view, PyBUF_SIMPLE) < 0) return -1; /* BufferError for non-contiguous views */
    *out = rb_hash_bytes(view.buf, (size_t)view.len, seed, RB_KEY_BYTES);
    PyBuffer_Release(&view);
    return 0;
  }
  if (PyIndex_Check(key)) { /* e.g. numpy integers */
    PyObject *index = PyNumber_Index(key);
    if (!index) return -1;
    int rc = hash_int(index, seed, out);
    Py_DECREF(index);
    return rc;
  }
  PyObject *name = type_name_of(key);
  if (name) {
    PyErr_Format(PyExc_TypeError, "unsupported key type '%U': keys must be bytes, bytearray, memoryview, str or int", name);
    Py_DECREF(name);
  }
  return -1;
}

/* ------------------------------------------------------------------------------------------------- */
/* collecting key hashes from an iterable                                                            */

typedef struct {
  uint64_t *data;
  size_t len, cap;
} HashVec;

static int hashvec_push(HashVec *hv, uint64_t h) {
  if (hv->len == hv->cap) {
    size_t cap = hv->cap ? hv->cap * 2 : 1024;
    if (cap > SIZE_MAX / sizeof(uint64_t)) { PyErr_NoMemory(); return -1; }
    uint64_t *data = (uint64_t *)realloc(hv->data, cap * sizeof(uint64_t));
    if (!data) { PyErr_NoMemory(); return -1; }
    hv->data = data;
    hv->cap = cap;
  }
  hv->data[hv->len++] = h;
  return 0;
}

/* A lone str/bytes would silently iterate its characters/ints: almost certainly a bug, so refuse it. */
static int reject_single_key(PyObject *keys, const char *what) {
  if (PyUnicode_Check(keys) || PyBytes_Check(keys) || PyByteArray_Check(keys) ||
      PyObject_TypeCheck(keys, &PyMemoryView_Type)) {
    PyObject *name = type_name_of(keys);
    if (name) {
      PyErr_Format(PyExc_TypeError, "%s must be an iterable of keys, not a single %U (wrap it in a list)", what, name);
      Py_DECREF(name);
    }
    return -1;
  }
  return 0;
}

/* A 1-D C-contiguous buffer of integers (array.array, numpy) is an array of int keys, hashed exactly as the same
 * ints would be one by one, but in C and without the GIL. Returns 1 if handled, 0 if the object is not such a buffer
 * (the caller then iterates it), -1 with an exception set. */
static int int_array_layout(const Py_buffer *v, int *is_signed) {
  const char *fmt = v->format ? v->format : "B";
  if (v->ndim != 1) return 0;
  if (*fmt == '@' || *fmt == '=') fmt++;
  else if (*fmt == '<') {
    const unsigned one = 1;
    if (*(const unsigned char *)&one != 1) return 0; /* little-endian format on a big-endian host: iterate instead */
    fmt++;
  }
  if (fmt[0] == '\0' || fmt[1] != '\0') return 0;
  Py_ssize_t size = v->itemsize;
  switch (fmt[0]) {
    case 'b': *is_signed = 1; return size == 1 ? 1 : 0;
    case 'B': *is_signed = 0; return size == 1 ? 1 : 0;
    case 'h': *is_signed = 1; return size == 2 ? 2 : 0;
    case 'H': *is_signed = 0; return size == 2 ? 2 : 0;
    case 'i': *is_signed = 1; return size == 4 ? 4 : 0;
    case 'I': *is_signed = 0; return size == 4 ? 4 : 0;
    case 'l': *is_signed = 1; return (size == 4 || size == 8) ? (int)size : 0;
    case 'L': *is_signed = 0; return (size == 4 || size == 8) ? (int)size : 0;
    case 'q': *is_signed = 1; return size == 8 ? 8 : 0;
    case 'Q': *is_signed = 0; return size == 8 ? 8 : 0;
    default: return 0;
  }
}

static void hash_int_array(const unsigned char *data, size_t count, int size, int is_signed, uint64_t seed,
                           uint64_t *out) {
  for (size_t i = 0; i < count; i++) {
    uint64_t raw = 0;
    memcpy(&raw, data + i * (size_t)size, (size_t)size); /* native byte order, any alignment */
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    raw >>= 8 * (8 - size);
#endif
    if (is_signed) {
      int shift = 64 - 8 * size; /* sign-extend from the item width */
      out[i] = rb_hash_i64((int64_t)(raw << shift) >> shift, seed);
    } else if (raw < (UINT64_C(1) << 63)) {
      out[i] = rb_hash_i64((int64_t)raw, seed);
    } else { /* uint64 >= 2**63 is outside int64: the canonical 9-byte little-endian encoding, as for a Python int */
      unsigned char enc[9];
      for (int k = 0; k < 8; k++) enc[k] = (unsigned char)(raw >> (8 * k));
      enc[8] = 0;
      out[i] = rb_hash_bytes(enc, 9, seed, RB_KEY_BIGINT);
    }
  }
}

static int collect_int_array(PyObject *keys, uint64_t seed, HashVec *hv) {
  if (PyUnicode_Check(keys) || PyBytes_Check(keys) || PyByteArray_Check(keys) ||
      PyObject_TypeCheck(keys, &PyMemoryView_Type) || !PyObject_CheckBuffer(keys))
    return 0;
  Py_buffer view;
  if (PyObject_GetBuffer(keys, &view, PyBUF_FORMAT | PyBUF_C_CONTIGUOUS) < 0) {
    PyErr_Clear(); /* e.g. a strided numpy slice: the generic iteration path still handles it */
    return 0;
  }
  int is_signed = 0;
  int size = int_array_layout(&view, &is_signed);
  if (size == 0) {
    PyBuffer_Release(&view);
    return 0;
  }
  size_t count = (size_t)view.len / (size_t)size;
  uint64_t *data = (uint64_t *)malloc(count ? count * sizeof(uint64_t) : 1);
  if (!data) {
    PyBuffer_Release(&view);
    PyErr_NoMemory();
    return -1;
  }
  Py_BEGIN_ALLOW_THREADS
  hash_int_array((const unsigned char *)view.buf, count, size, is_signed, seed, data);
  Py_END_ALLOW_THREADS
  PyBuffer_Release(&view);
  hv->data = data;
  hv->len = hv->cap = count;
  return 1;
}

static int collect_hashes(PyObject *keys, uint64_t seed, HashVec *hv, const char *what) {
  int handled = collect_int_array(keys, seed, hv);
  if (handled != 0) return handled < 0 ? -1 : 0;
  if (reject_single_key(keys, what) < 0) return -1;
  Py_ssize_t hint = PyObject_Size(keys);
  if (hint < 0) { /* generators and other unsized iterables */
    PyErr_Clear();
    hint = 0;
  }
  PyObject *it = PyObject_GetIter(keys);
  if (!it) return -1;
  if (hint > 0) {
    hv->data = (uint64_t *)malloc((size_t)hint * sizeof(uint64_t));
    if (!hv->data) { Py_DECREF(it); PyErr_NoMemory(); return -1; }
    hv->cap = (size_t)hint;
  }
  PyObject *item;
  while ((item = PyIter_Next(it)) != NULL) {
    uint64_t h;
    int rc = key_hash(item, seed, &h);
    Py_DECREF(item);
    if (rc < 0 || hashvec_push(hv, h) < 0) { Py_DECREF(it); return -1; }
    if ((hv->len & 0xffffu) == 0 && PyErr_CheckSignals() < 0) { Py_DECREF(it); return -1; }
  }
  Py_DECREF(it);
  return PyErr_Occurred() ? -1 : 0;
}

/* ------------------------------------------------------------------------------------------------- */
/* error mapping                                                                                     */

static PyObject *raise_status(ModState *st, rb_status status) {
  switch (status) {
    case RB_E_NOMEM: return PyErr_NoMemory();
    case RB_E_INVALID_ARG:
    case RB_E_TOO_LARGE: PyErr_SetString(PyExc_ValueError, rb_strerror(status)); return NULL;
    default: PyErr_Format(st->format_error, "invalid pyribbon data: %s", rb_strerror(status)); return NULL;
  }
}

/* ------------------------------------------------------------------------------------------------- */
/* RibbonFilter                                                                                      */

static PyObject *Filter_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
  static char *kwlist[] = {"keys", "fp_bits", "seed", "overhead", "max_attempts", NULL};
  PyObject *keys, *seed_obj = NULL, *overhead_obj = NULL;
  int fp_bits = (int)RB_DEFAULT_FP_BITS, max_attempts = (int)RB_DEFAULT_MAX_ATTEMPTS;
  if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|$iOOi:RibbonFilter", kwlist, &keys, &fp_bits, &seed_obj,
                                   &overhead_obj, &max_attempts))
    return NULL;
  ModState *st = state_of_type(type);
  if (!st) return NULL;
  if (fp_bits < (int)RB_MIN_FP_BITS || fp_bits > (int)RB_MAX_FP_BITS) {
    PyErr_Format(PyExc_ValueError, "fp_bits must be between %u and %u, got %d", RB_MIN_FP_BITS, RB_MAX_FP_BITS, fp_bits);
    return NULL;
  }
  if (max_attempts < 1 || max_attempts > (int)RB_MAX_ATTEMPTS) {
    PyErr_Format(PyExc_ValueError, "max_attempts must be between 1 and %u, got %d", RB_MAX_ATTEMPTS, max_attempts);
    return NULL;
  }
  uint64_t seed = 0;
  if (seed_obj && seed_obj != Py_None) {
    PyObject *index = PyNumber_Index(seed_obj);
    if (!index) return NULL;
    seed = PyLong_AsUnsignedLongLong(index);
    Py_DECREF(index);
    if (seed == (uint64_t)-1 && PyErr_Occurred()) {
      if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
        PyErr_Clear();
        PyErr_SetString(PyExc_ValueError, "seed must be in the range [0, 2**64)");
      }
      return NULL;
    }
  }
  double overhead = -1.0; /* auto */
  if (overhead_obj && overhead_obj != Py_None) {
    overhead = PyFloat_AsDouble(overhead_obj);
    if (overhead == -1.0 && PyErr_Occurred()) return NULL;
    if (!(overhead >= 0.0 && overhead <= 4.0)) {
      PyErr_SetString(PyExc_ValueError, "overhead must be a number in [0, 4] (extra rows as a fraction of the key count)");
      return NULL;
    }
  }

  HashVec hv = {NULL, 0, 0};
  if (collect_hashes(keys, seed, &hv, "keys") < 0) {
    free(hv.data);
    return NULL;
  }
  rb_params params = rb_params_default();
  params.fp_bits = (uint32_t)fp_bits;
  params.max_attempts = (uint32_t)max_attempts;
  params.overhead = overhead;
  params.seed = seed;
  rb_filter *filter = NULL;
  rb_status status;
  Py_BEGIN_ALLOW_THREADS
  status = rb_build(hv.data, hv.len, &params, &filter, NULL);
  Py_END_ALLOW_THREADS
  size_t n = hv.len;
  free(hv.data);
  if (status == RB_E_CONSTRUCT) {
    PyErr_Format(st->construction_error,
                 "could not build a filter for %zu keys in %d attempts (fp_bits=%d); "
                 "raise overhead= or max_attempts=, or change seed=",
                 n, max_attempts, fp_bits);
    return NULL;
  }
  if (status != RB_OK) return raise_status(st, status);
  FilterObject *self = (FilterObject *)PyType_GenericAlloc(type, 0);
  if (!self) {
    rb_free(filter);
    return NULL;
  }
  self->filter = filter;
  self->has_view = 0;
  return (PyObject *)self;
}

static void Filter_dealloc(PyObject *obj) {
  FilterObject *self = (FilterObject *)obj;
  PyTypeObject *tp = Py_TYPE(obj);
  rb_free(self->filter);
  if (self->has_view) PyBuffer_Release(&self->view);
  freefunc tp_free = (freefunc)PyType_GetSlot(tp, Py_tp_free);
  tp_free(obj);
  Py_DECREF(tp);
}

static int Filter_contains(PyObject *obj, PyObject *key) {
  FilterObject *self = (FilterObject *)obj;
  uint64_t h;
  if (key_hash(key, rb_seed(self->filter), &h) < 0) return -1;
  return rb_contains(self->filter, h);
}

static Py_ssize_t Filter_length(PyObject *obj) {
  uint64_t n = rb_num_keys(((FilterObject *)obj)->filter);
  if (n > (uint64_t)PY_SSIZE_T_MAX) {
    PyErr_SetString(PyExc_OverflowError, "key count does not fit in Py_ssize_t");
    return -1;
  }
  return (Py_ssize_t)n;
}

static PyObject *Filter_contains_many(PyObject *obj, PyObject *keys) {
  FilterObject *self = (FilterObject *)obj;
  HashVec hv = {NULL, 0, 0};
  if (collect_hashes(keys, rb_seed(self->filter), &hv, "keys") < 0) {
    free(hv.data);
    return NULL;
  }
  size_t n = hv.len;
  uint8_t *flags = (uint8_t *)malloc(n ? n : 1);
  if (!flags) {
    free(hv.data);
    return PyErr_NoMemory();
  }
  if (n >= BATCH_NOGIL_THRESHOLD) {
    Py_BEGIN_ALLOW_THREADS
    rb_contains_many(self->filter, hv.data, n, flags);
    Py_END_ALLOW_THREADS
  } else {
    rb_contains_many(self->filter, hv.data, n, flags);
  }
  free(hv.data);
  PyObject *list = PyList_New((Py_ssize_t)n);
  if (list) {
    for (size_t i = 0; i < n; i++) PyList_SetItem(list, (Py_ssize_t)i, Py_NewRef(flags[i] ? Py_True : Py_False));
  }
  free(flags);
  return list;
}

static PyObject *Filter_to_bytes(PyObject *obj, PyObject *Py_UNUSED(ignored)) {
  FilterObject *self = (FilterObject *)obj;
  size_t size = rb_serialized_size(self->filter);
  PyObject *out = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)size);
  if (!out) return NULL;
  if (rb_serialize(self->filter, PyBytes_AsString(out), size) != RB_OK) {
    Py_DECREF(out);
    PyErr_SetString(PyExc_SystemError, "rb_serialize failed on a correctly sized buffer");
    return NULL;
  }
  return out;
}

static PyObject *Filter_from_buffer(PyObject *cls, PyObject *args, PyObject *kwds) {
  static char *kwlist[] = {"buffer", "verify", NULL};
  PyObject *buffer;
  int verify = 1;
  if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|$p:from_buffer", kwlist, &buffer, &verify)) return NULL;
  PyTypeObject *type = (PyTypeObject *)cls;
  ModState *st = state_of_type(type);
  if (!st) return NULL;
  FilterObject *self = (FilterObject *)PyType_GenericAlloc(type, 0);
  if (!self) return NULL;
  if (PyObject_GetBuffer(buffer, &self->view, PyBUF_SIMPLE) < 0) { /* C-contiguous bytes; BufferError otherwise */
    Py_DECREF(self);
    return NULL;
  }
  self->has_view = 1;
  rb_status status;
  Py_BEGIN_ALLOW_THREADS
  status = rb_from_buffer(self->view.buf, (size_t)self->view.len, verify, &self->filter);
  Py_END_ALLOW_THREADS
  if (status != RB_OK) {
    Py_DECREF(self); /* dealloc releases the buffer; self->filter is NULL */
    return raise_status(st, status);
  }
  return (PyObject *)self;
}

static PyObject *Filter_reduce(PyObject *obj, PyObject *Py_UNUSED(ignored)) {
  /* pickle / copy: rebuilt through from_buffer(bytes) with full verification */
  PyObject *data = Filter_to_bytes(obj, NULL);
  if (!data) return NULL;
  PyObject *factory = PyObject_GetAttrString((PyObject *)Py_TYPE(obj), "from_buffer");
  if (!factory) {
    Py_DECREF(data);
    return NULL;
  }
  PyObject *result = Py_BuildValue("(O(O))", factory, data);
  Py_DECREF(factory);
  Py_DECREF(data);
  return result;
}

static PyObject *Filter_repr(PyObject *obj) {
  FilterObject *self = (FilterObject *)obj;
  return PyUnicode_FromFormat("RibbonFilter(keys=%llu, fp_bits=%u, size_in_bytes=%zu)",
                              (unsigned long long)rb_num_keys(self->filter), rb_fp_bits(self->filter),
                              rb_serialized_size(self->filter));
}

static PyObject *Filter_get_size_in_bytes(PyObject *obj, void *Py_UNUSED(closure)) {
  return PyLong_FromSize_t(rb_serialized_size(((FilterObject *)obj)->filter));
}

static PyObject *Filter_get_fp_bits(PyObject *obj, void *Py_UNUSED(closure)) {
  return PyLong_FromUnsignedLong(rb_fp_bits(((FilterObject *)obj)->filter));
}

static PyObject *Filter_get_bits_per_key(PyObject *obj, void *Py_UNUSED(closure)) {
  const rb_filter *f = ((FilterObject *)obj)->filter;
  uint64_t n = rb_num_keys(f);
  return PyFloat_FromDouble(n ? 8.0 * (double)rb_serialized_size(f) / (double)n : 0.0);
}

static PyMethodDef Filter_methods[] = {
    {"contains_many", Filter_contains_many, METH_O,
     "contains_many($self, keys, /)\n--\n\nReturn a list of bools, one per key: whether each key is possibly in the filter.\n\n"
     "`keys` is an iterable of keys or a 1-D integer buffer (array.array, numpy), which is much faster. Large batches\n"
     "release the GIL while probing."},
    {"to_bytes", Filter_to_bytes, METH_NOARGS,
     "to_bytes($self, /)\n--\n\nReturn the filter in the versioned, little-endian serialization format."},
    {"from_buffer", (PyCFunction)(void (*)(void))Filter_from_buffer, METH_VARARGS | METH_KEYWORDS | METH_CLASS,
     "from_buffer($type, /, buffer, *, verify=True)\n--\n\nView serialized filter bytes without copying them.\n\n"
     "`buffer` must be C-contiguous and must not be modified while the filter exists. With verify=False the payload\n"
     "checksum (which reads every byte) is skipped; the header is always validated. Raises FormatError on bad input."},
    {"__reduce__", Filter_reduce, METH_NOARGS, "Support pickle and copy."},
    {NULL, NULL, 0, NULL}};

static PyGetSetDef Filter_getset[] = {
    {"size_in_bytes", Filter_get_size_in_bytes, NULL, "Length of the serialized filter in bytes, header included.", NULL},
    {"bits_per_key", Filter_get_bits_per_key, NULL, "8 * size_in_bytes / len(filter); 0.0 for an empty filter.", NULL},
    {"fp_bits", Filter_get_fp_bits, NULL, "Fingerprint bits r: the false-positive rate is about 2**-r.", NULL},
    {NULL, NULL, NULL, NULL, NULL}};

static PyType_Slot Filter_slots[] = {
    {Py_tp_doc,
     (void *)"RibbonFilter(keys, *, fp_bits=8, seed=0, overhead=None, max_attempts=32)\n--\n\n"
             "An immutable approximate-membership filter (standard ribbon filter).\n\n"
             "Build it from an iterable of keys (bytes, bytearray, memoryview, str or int), or from a 1-D integer buffer such as\n"
             "an array.array or numpy array (hashed in C, same result as the ints one by one). `key in filter` never gives a\n"
             "false negative and gives a false positive with probability about 2**-fp_bits. Safe to query from many threads."},
    {Py_tp_new, (void *)Filter_new},
    {Py_tp_dealloc, (void *)Filter_dealloc},
    {Py_tp_repr, (void *)Filter_repr},
    {Py_tp_methods, Filter_methods},
    {Py_tp_getset, Filter_getset},
    {Py_sq_contains, (void *)Filter_contains},
    {Py_sq_length, (void *)Filter_length},
    {0, NULL}};

static PyType_Spec Filter_spec = {"pyribbon.RibbonFilter", sizeof(FilterObject), 0,
                                  Py_TPFLAGS_DEFAULT | Py_TPFLAGS_IMMUTABLETYPE, Filter_slots};

/* ------------------------------------------------------------------------------------------------- */
/* module                                                                                            */

static int module_exec(PyObject *module) {
  ModState *st = (ModState *)PyModule_GetState(module);
  st->ribbon_error = PyErr_NewExceptionWithDoc("pyribbon.RibbonError", "Base class of all pyribbon errors.", NULL, NULL);
  if (!st->ribbon_error) return -1;
  st->construction_error = PyErr_NewExceptionWithDoc(
      "pyribbon.ConstructionError", "No filter could be built: every construction attempt failed.", st->ribbon_error, NULL);
  if (!st->construction_error) return -1;
  PyObject *bases = PyTuple_Pack(2, st->ribbon_error, PyExc_ValueError);
  if (!bases) return -1;
  st->format_error = PyErr_NewExceptionWithDoc("pyribbon.FormatError", "Serialized filter data is invalid or corrupt.",
                                               bases, NULL);
  Py_DECREF(bases);
  if (!st->format_error) return -1;
  st->filter_type = (PyTypeObject *)PyType_FromModuleAndSpec(module, &Filter_spec, NULL);
  if (!st->filter_type) return -1;
  if (PyModule_AddObjectRef(module, "RibbonError", st->ribbon_error) < 0) return -1;
  if (PyModule_AddObjectRef(module, "ConstructionError", st->construction_error) < 0) return -1;
  if (PyModule_AddObjectRef(module, "FormatError", st->format_error) < 0) return -1;
  if (PyModule_AddObjectRef(module, "RibbonFilter", (PyObject *)st->filter_type) < 0) return -1;
  return 0;
}

static int module_traverse(PyObject *module, visitproc visit, void *arg) {
  ModState *st = (ModState *)PyModule_GetState(module);
  Py_VISIT(st->ribbon_error);
  Py_VISIT(st->construction_error);
  Py_VISIT(st->format_error);
  Py_VISIT(st->filter_type);
  return 0;
}

static int module_clear(PyObject *module) {
  ModState *st = (ModState *)PyModule_GetState(module);
  Py_CLEAR(st->ribbon_error);
  Py_CLEAR(st->construction_error);
  Py_CLEAR(st->format_error);
  Py_CLEAR(st->filter_type);
  return 0;
}

static void module_free(void *module) { (void)module_clear((PyObject *)module); }

static PyModuleDef_Slot module_slots[] = {{Py_mod_exec, (void *)module_exec}, {0, NULL}};

static struct PyModuleDef module_def = {PyModuleDef_HEAD_INIT, "pyribbon._ribbon", "C core of pyribbon.", sizeof(ModState),
                                        NULL, module_slots, module_traverse, module_clear, module_free};

PyMODINIT_FUNC PyInit__ribbon(void) { return PyModuleDef_Init(&module_def); }
