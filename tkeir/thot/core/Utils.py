"""Title: Utilitary functions

Core T-KEIR libraries (logging, config, paths, utilities).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import ctypes
import errno
import gzip
import json
import os
import random
import re
import string
import threading
import time

from spacy.tokens import Doc, Token


def timeit(f):  # pragma: no cover
    """Decorator that prints the elapsed runtime of the wrapped function.

    Args:
        f: Function to wrap and time.

    Returns:
        Wrapped function that prints runtime then returns the original result.

    Example:
        >>> from thot.core.Utils import timeit
        >>> @timeit
        ... def add(a, b):
        ...     return a + b
        >>> add(1, 2)  # doctest: +SKIP
        3
    """

    def timed(*args, **kw):
        ts = time.time()
        result = f(*args, **kw)
        te = time.time()

        print("func:%r took: %2.4f sec" % (f.__name__, te - ts))
        return result

    return timed


def terminate_thread(thread):  # pragma: no cover
    """Terminate a Python thread from another thread.

    Args:
        thread: ``threading.Thread`` instance to terminate.

    Raises:
        ValueError: If the thread id does not exist.
        SystemError: If ``PyThreadState_SetAsyncExc`` fails.

    Example:
        >>> import threading
        >>> from thot.core.Utils import terminate_thread
        >>> t = threading.Thread(target=lambda: None)
        >>> terminate_thread(t)  # doctest: +SKIP
    """
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), exc
    )
    if res == 0:
        raise ValueError("nonexistent thread id")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class TimeLimitExpired(Exception):
    """Raised when ``timelimit`` exceeds the allowed runtime."""

    pass


def timelimit(timeout, func, args=(), kwargs={}):
    """Run ``func`` with the given timeout.

    Args:
        timeout: Maximum runtime in seconds.
        func: Callable to execute.
        args: Positional arguments for ``func``.
        kwargs: Keyword arguments for ``func``.

    Returns:
        Result returned by ``func``.

    Raises:
        TimeLimitExpired: If ``func`` does not finish within ``timeout``.

    Example:
        >>> from thot.core.Utils import timelimit
        >>> timelimit(5, sum, args=([1, 2, 3],))  # doctest: +SKIP
        6
    """

    class FuncThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)
            self.result = None

        def run(self):
            self.result = func(*args, **kwargs)

        def stop(self):
            terminate_thread(self)

    it = FuncThread()
    it.start()
    it.join(timeout)
    if it.is_alive():
        it.stop()
        raise TimeLimitExpired()
    else:
        return it.result


def set_if_not_exists(d: dict, att, v):
    """Set a dictionary key only when it is absent.

    Args:
        d: Target dictionary updated in place.
        att: Key to set when missing.
        v: Value assigned to ``att``.

    Example:
        >>> from thot.core.Utils import set_if_not_exists
        >>> payload = {"keep": 1}
        >>> set_if_not_exists(payload, "keep", 2)
        >>> set_if_not_exists(payload, "add", 3)
        >>> payload
        {'keep': 1, 'add': 3}
    """
    if att not in d:
        d[att] = v


def check_pid(pid):
    """Check for the existence of a Unix process id.

    Args:
        pid: Process id to probe.

    Returns:
        ``True`` when the process exists, otherwise ``False``.

    Example:
        >>> import os
        >>> from thot.core.Utils import check_pid
        >>> check_pid(os.getpid())
        True
    """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def mkdir_p(path):
    """Create a directory and any missing parents.

    Args:
        path: Directory path to create.

    Example:
        >>> import os
        >>> import tempfile
        >>> from thot.core.Utils import mkdir_p
        >>> target = os.path.join(tempfile.gettempdir(), "tkeir-utils-doc-test")
        >>> mkdir_p(target)
        >>> os.path.isdir(target)
        True
    """
    try:
        os.makedirs(path)
    except OSError as exc:  # Python ≥ 2.5
        if exc.errno != errno.EEXIST or (not os.path.isdir(path)):
            raise


def type_to_bool(entry):
    """Convert common truthy or falsy literals to a boolean.

    Args:
        entry: String, boolean, or numeric value to convert.

    Returns:
        ``True`` or ``False`` according to the input value.

    Raises:
        ValueError: If the value cannot be converted.

    Example:
        >>> from thot.core.Utils import type_to_bool
        >>> type_to_bool("1")
        True
        >>> type_to_bool("false")
        False
    """
    if isinstance(entry, str):
        return entry.lower() in ["true", "1", "t", "y", "yes", "on"]
    if isinstance(entry, bool):
        return entry
    if isinstance(entry, int) or isinstance(entry, float):
        return entry > 0
    raise ValueError("Cannot convert to bool")


def generate_id(prefix="default", length=32):
    """Generate a pseudo-unique identifier.

    Args:
        prefix: Prefix prepended to the generated id.
        length: Number of random characters in the id body.

    Returns:
        Identifier string containing process and thread metadata.

    Example:
        >>> from thot.core.Utils import generate_id
        >>> generated = generate_id(prefix="test", length=8)
        >>> generated.startswith("test-")
        True
    """
    qid = "".join(
        [
            random.choice(string.ascii_letters + string.digits)
            for _ in range(length)
        ]
    )
    qid = (
        prefix
        + "-"
        + qid
        + "-"
        + str(os.getppid())
        + "-"
        + str(os.getpid())
        + "-"
        + str(threading.current_thread().name)
    )
    return qid


def is_numeric(literal):
    """Return whether a literal can be parsed as a numeric value.

    Args:
        literal: Value to inspect.

    Returns:
        ``True`` when ``literal`` is numeric, otherwise ``False``.

    Example:
        >>> from thot.core.Utils import is_numeric
        >>> is_numeric(3)
        True
        >>> is_numeric("3.14")
        True
    """
    if (
        isinstance(literal, int)
        or isinstance(literal, float)
        or isinstance(literal, complex)
    ):
        return True
    if isinstance(literal, str):
        return literal.replace(".", "", 1).isdigit()
    return False


def is_email(email):
    """Validate a simple email address pattern.

    Args:
        email: Email address to validate.

    Returns:
        Match object when the email matches, otherwise ``None``.

    Example:
        >>> from thot.core.Utils import is_email
        >>> bool(is_email("user.name@example.com"))
        True
        >>> is_email("not-an-email") is None
        True
    """
    return re.search(r"^[a-z0-9]+[._]?[a-z0-9]+@\w+\.\w{2,3}$", email.lower())


def str_to_uni(str_catch):
    """Convert a tokenizer unicode escape token to a character.

    Args:
        str_catch: Token string such as ``"u0041"``.

    Returns:
        Decoded Unicode character, or an empty string for empty input.

    Example:
        >>> from thot.core.Utils import str_to_uni
        >>> str_to_uni("u0041")
        'A'
        >>> str_to_uni("")
        ''
    """
    if len(str_catch) > 0:
        merged_token = "0x" + str_catch[1:]
        return chr(int(merged_token, 0))
    return ""


def config_use_mwe(config_entry: dict | None) -> bool:
    """Return ``True`` when a task config explicitly enables MWE resources.

    Args:
        config_entry: Task configuration dictionary.

    Returns:
        ``True`` when ``use-mwe`` is enabled in the config entry.

    Example:
        >>> from thot.core.Utils import config_use_mwe
        >>> config_use_mwe(None)
        False
        >>> config_use_mwe({"use-mwe": True})
        True
    """
    if not config_entry:
        return False
    return bool(config_entry.get("use-mwe", False))


DEFAULT_MWE_FILENAME = "tkeir_mwe.pkl"


def apply_use_mwe_to_entries(entries: list, use_mwe: bool) -> None:
    """Set ``use-mwe`` and default MWE pickle on tokenizer or NER config rows.

    Args:
        entries: Configuration rows updated in place.
        use_mwe: Whether multi-word expression resources should be enabled.

    Example:
        >>> from thot.core.Utils import apply_use_mwe_to_entries
        >>> rows = [{"language": "en"}]
        >>> apply_use_mwe_to_entries(rows, True)
        >>> rows[0]["use-mwe"]
        True
        >>> rows[0]["mwe"]
        'tkeir_mwe.pkl'
    """
    for entry in entries:
        entry["use-mwe"] = use_mwe
        if use_mwe and not entry.get("mwe"):
            entry["mwe"] = DEFAULT_MWE_FILENAME


class ThotTokenizerToSpacy:
    """Adapt pre-tokenized T-KEIR payloads to spaCy ``Doc`` objects."""

    def __init__(
        self,
        vocab,
        config: dict = None,
        call_context=None,
        use_mwe: bool = False,
    ):
        """Initialize the tokenizer adapter.

        Args:
            vocab: spaCy vocabulary used to build documents.
            config: Optional tokenizer configuration.
            call_context: Optional logging context.
            use_mwe: Whether MWE metadata should be preserved.

        Example:
            >>> from spacy.lang.en import English
            >>> from thot.core.Utils import ThotTokenizerToSpacy
            >>> nlp = English()
            >>> tokenizer = ThotTokenizerToSpacy(nlp.vocab)
            >>> tokenizer.use_mwe
            False
        """
        self.vocab = vocab
        self.config = config
        self.use_mwe = use_mwe
        Token.set_extension(
            "advanced_tag",
            default={"is-compound": False, "data": {}},
            force=True,
        )

    def _flattern_table(self, text):
        """Flatten recursive tokenizer tables into parallel token lists.

        Args:
            text: Tokenized entry from the tokenizer service.

        Returns:
            List containing words, sentence starts, and optional MWE data.

        Example:
            >>> from spacy.lang.en import English
            >>> from thot.core.Utils import ThotTokenizerToSpacy
            >>> tokenizer = ThotTokenizerToSpacy(English().vocab)
            >>> tokenizer._flattern_table(
            ...     {"token": "Hi", "start_sentence": True}
            ... )
            (['Hi'], [True], [{}])
        """
        if isinstance(text, list):
            flattern_text: list[str] = []
            flattern_sentence: list[bool] = []
            flattern_data: list[dict] = []
            for text_i in text:
                words, sentences, data = self._flattern_table(text_i)
                flattern_text.extend(words)
                flattern_sentence.extend(sentences)
                flattern_data.extend(data)
            return flattern_text, flattern_sentence, flattern_data
        data = {}
        if self.use_mwe and ("mwe" in text) and ("data" in text["mwe"]):
            data = text["mwe"]["data"]
        return [text["token"]], [text["start_sentence"]], [data]

    def __call__(self, text, pre_tagging_with_concept=False):
        """Build a spaCy document from pre-tokenized input.

        Args:
            text: Tokenized entry generally produced by the tokenizer service.
            pre_tagging_with_concept: Whether concept tags should be attached.

        Returns:
            spaCy ``Doc`` built from the flattened token stream.

        Example:
            >>> from spacy.lang.en import English
            >>> from thot.core.Utils import ThotTokenizerToSpacy
            >>> tokenizer = ThotTokenizerToSpacy(English().vocab)
            >>> doc = tokenizer(
            ...     [{"token": "Hello", "start_sentence": True}]
            ... )
            >>> [token.text for token in doc]
            ['Hello']
        """
        words, sentences, data = self._flattern_table(text)
        if not (self.use_mwe and pre_tagging_with_concept):
            doc = Doc(self.vocab, words=words)
            for token_i, is_start in enumerate(sentences):
                if is_start:
                    doc[token_i].is_sent_start = True
                if self.use_mwe:
                    doc[token_i]._.advanced_tag = []
            return doc

        pos_tags = []
        tags = []
        advanced_tags = []
        pos_mapping = {
            "NOUN": "NN",
            "PROPN": "NNP",
        }
        for data_i in range(len(data)):
            is_concept = False
            pos = ""
            advanced_tags.append([])
            for label in data[data_i]:
                if "data" in data[data_i][label]:
                    for data_entry in data[data_i][label]["data"]:
                        if ("type" in data_entry) and (
                            data_entry["type"] == "concept"
                        ):
                            if len(advanced_tags[-1]) == 0:
                                advanced_tags[-1].append({label: None})
                            if label not in advanced_tags[-1][-1]:
                                advanced_tags[-1][-1][label] = None
                            advanced_tags[-1][-1][label] = data_entry
                            is_concept = True
                    if is_concept and ("pos" in data[data_i][label]):
                        pos = data[data_i][label]["pos"]
                        break
            pos_tags.append(pos)
            if pos in pos_mapping:
                tags.append(pos_mapping[pos])
            else:
                tags.append("")
        doc = Doc(self.vocab, words=words, pos=pos_tags, tags=tags)
        token_i = 0
        for token in doc:
            token.is_sent_start = sentences[token_i]
            token._.advanced_tag = advanced_tags[token_i]
            token_i = token_i + 1
        return doc


def get_elastic_url(configuration):
    """Build an Elasticsearch URL and certificate verification flag.

    Args:
        configuration: Service configuration containing a ``network`` section.

    Returns:
        Tuple of URL string and certificate verification boolean.

    Example:
        >>> from thot.core.Utils import get_elastic_url
        >>> url, verify = get_elastic_url(
        ...     {
        ...         "network": {
        ...             "use_ssl": "false",
        ...             "verify_certs": True,
        ...             "host": "localhost",
        ...             "port": 9200,
        ...         }
        ...     }
        ... )
        >>> url
        'http://localhost:9200'
        >>> verify
        True
    """
    es_scheme = "http"
    es_verify_certs = True
    if type_to_bool(configuration["network"]["use_ssl"]):
        es_scheme = "https"
    if not configuration["network"]["verify_certs"]:
        es_verify_certs = False
    else:
        es_verify_certs = configuration["network"]["verify_certs"]
    if isinstance(es_verify_certs, str):
        if es_verify_certs.lower() == "true":
            es_verify_certs = True
        else:
            es_verify_certs = False

    es_user = None
    es_password = None
    if "auth" in configuration["network"]:
        if "user" in configuration["network"]["auth"]:
            es_user = configuration["network"]["auth"]["user"]
        if "password" in configuration["network"]["auth"]:
            es_password = configuration["network"]["auth"]["password"]
    es_url = es_scheme + "://"
    if es_user and es_password:
        es_url = es_url + es_user + ":" + es_password + "@"
    es_url = (
        es_url
        + configuration["network"]["host"]
        + ":"
        + str(configuration["network"]["port"])
    )
    return (es_url, es_verify_certs)


def save_json(data: dict, filename: str, zip_file: bool = False):
    """Serialize a dictionary to JSON, optionally gzip-compressed.

    Args:
        data: Dictionary to serialize.
        filename: Output file path.
        zip_file: When ``True``, write gzip-compressed JSON.

    Example:
        >>> import json
        >>> import os
        >>> import tempfile
        >>> from thot.core.Utils import save_json
        >>> path = os.path.join(tempfile.gettempdir(), "tkeir-save-json.json")
        >>> save_json({"a": 1}, path)
        >>> with open(path, encoding="utf-8") as handle:
        ...     json.load(handle)
        {'a': 1}
    """
    if zip_file:
        json_data = json.dumps(data, indent=2)
        with gzip.open(filename, "wb") as f:
            f.write(json_data.encode("utf-8"))
            f.close()
    else:
        with open(filename, "w", encoding="utf-8") as output_f:
            json.dump(
                data, output_f, indent=2, sort_keys=True, ensure_ascii=False
            )
            output_f.close()


def load_json(filename: str, zip_file: bool = False):
    """Load JSON from plain or gzip-compressed files.

    Args:
        filename: Input file path.
        zip_file: When ``True``, read gzip-compressed JSON directly.

    Returns:
        Parsed JSON object.

    Example:
        >>> import os
        >>> import tempfile
        >>> from thot.core.Utils import load_json, save_json
        >>> path = os.path.join(tempfile.gettempdir(), "tkeir-load-json.json")
        >>> save_json({"loaded": True}, path)
        >>> load_json(path)
        {'loaded': True}
    """
    load_error = True
    data = dict()
    if not zip_file:
        try:
            with open(filename, encoding="utf-8") as json_f:
                data = json.load(json_f)
                json_f.close()
                load_error = False
        except Exception:
            pass
    if load_error:
        with gzip.open(filename, "rb") as gzip_f:
            gdata = gzip_f.read()
            data = json.loads(gdata)
            gzip_f.close()
    return data
