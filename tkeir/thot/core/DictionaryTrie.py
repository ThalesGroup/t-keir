"""Title: Trie structure for lexical resources

Core T-KEIR libraries (logging, config, paths, utilities).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from fold_to_ascii import fold

from thot.core.ThotLogger import ThotLogger


def ascii_fold(text: str) -> str:
    """Fold diacritics to ASCII (same mapping as gazetteer compile).

    Example:
        >>> from thot.core.DictionaryTrie import ascii_fold
        >>> ascii_fold("são")
        'sao'
        >>> ascii_fold("café")
        'cafe'
    """
    if not text:
        return text
    folded = fold(text)
    return folded if folded else text


def trie_get(trie, token: str):
    """Return the child node for ``token``, then an ASCII-folded fallback.

    Token-level MWE tries store lowercased gazetteer forms. Folding the
    query token captures diacritic variants (``São`` → ``sao``) without
    requiring every surface form in the gazetteer.

    Example:
        >>> from thot.core.DictionaryTrie import Trie, trie_get
        >>> t = Trie()
        >>> t.insert(("sao",), "LOC", True, "PROPN", {}, 1.0)
        >>> trie_get(t, "são") is not None
        True
        >>> trie_get(t, "missing") is None
        True
    """
    if not isinstance(trie, dict) or not token:
        return None
    if token in trie:
        return trie[token]
    folded = ascii_fold(token)
    if folded != token and folded in trie:
        return trie[folded]
    return None


def make_trie(words: set) -> dict:
    """Create a trie structure from a set of words.

    Args:
        words: Set of words to insert into the trie.

    Returns:
        Nested dictionary trie with ``_end_`` markers on complete words.

    Example:
        >>> from thot.core.DictionaryTrie import make_trie
        >>> trie = make_trie({"abc", "abd"})
        >>> trie["a"]["b"]["c"]["_end_"]
        '_end_'
    """
    root: dict = {}
    for word in words:
        current_dict = root
        for letter in word:
            current_dict = current_dict.setdefault(letter, {})
        current_dict["_end_"] = "_end_"
    return root


def prefix_trie(trie: dict, word: str) -> dict | None:
    """Return the trie subtree that follows a prefix.

    When the exact prefix is missing, retries after ASCII-folding so
    diacritic query tokens (``café``) match folded gazetteer keys (``cafe``).

    Args:
        trie: Source trie structure.
        word: Prefix to resolve.

    Returns:
        Subtree dictionary, or ``None`` when the prefix is absent.

    Example:
        >>> from thot.core.DictionaryTrie import make_trie, prefix_trie
        >>> trie = make_trie({"abc", "abd"})
        >>> subtree = prefix_trie(trie, "ab")
        >>> subtree["c"]["_end_"]
        '_end_'
        >>> prefix_trie(make_trie({"cafe"}), "café")["_end_"]
        '_end_'
    """
    found = _prefix_trie_exact(trie, word)
    if found is not None:
        return found
    folded = ascii_fold(word)
    if folded != word:
        return _prefix_trie_exact(trie, folded)
    return None


def _prefix_trie_exact(trie: dict, word: str) -> dict | None:
    """Walk ``trie`` with ``word`` as-is (no diacritic folding).

    Example:
        >>> from thot.core.DictionaryTrie import make_trie, _prefix_trie_exact
        >>> _prefix_trie_exact(make_trie({"cafe"}), "cafe")["_end_"]
        '_end_'
        >>> _prefix_trie_exact(make_trie({"cafe"}), "café") is None
        True
    """
    current_dict = trie
    for letter in word:
        if letter not in current_dict:
            return None
        current_dict = current_dict[letter]
    return current_dict


def end_trie(trie: dict) -> bool:
    """Return whether a trie node marks the end of a word.

    Args:
        trie: Trie node to inspect.

    Returns:
        ``True`` when the node contains an ``_end_`` marker.

    Example:
        >>> from thot.core.DictionaryTrie import end_trie, make_trie, prefix_trie
        >>> trie = make_trie({"abc"})
        >>> end_trie(prefix_trie(trie, "abc"))
        True
        >>> end_trie(prefix_trie(trie, "ab"))
        False
    """
    return "_end_" in trie


class Trie(dict):
    """Trie for multiple-word expressions with labels and metadata."""

    LEAF = True

    def __init__(self, strings=None):
        """Initialize the trie and optionally preload string patterns.

        Args:
            strings: Optional list of pattern dictionaries to insert.

        Example:
            >>> from thot.core.DictionaryTrie import Trie
            >>> trie = Trie(
            ...     [
            ...         {
            ...             "pattern": "New York",
            ...             "label": "GPE",
            ...             "in_vocab": True,
            ...             "pos": "PROPN",
            ...             "data": {},
            ...             "weight": 1.0,
            ...         }
            ...     ]
            ... )
            >>> trie["N"]["e"]["w"][" "]["Y"]["o"]["r"]["k"][Trie.LEAF]["in_vocab"]
            True
        """
        super().__init__()
        self.current_string = ""
        if strings:
            for string in strings:
                self.current_string = string["pattern"]
                if self.current_string:
                    self.insert(
                        string["pattern"],
                        string["label"],
                        string["in_vocab"],
                        string["pos"],
                        string["data"],
                        string["weight"],
                    )
                else:
                    ThotLogger.warning("Empty entry")

    def insert(self, string, label, in_vocab, pos, data, weight):
        """Insert a labeled string into the trie.

        Args:
            string: Remaining string fragment to insert.
            label: Entity or lexical label.
            in_vocab: Whether the string exists in the spaCy vocabulary.
            pos: Part of speech associated with the string.
            data: Additional metadata attached to the label.
            weight: Weight associated with the string.

        Example:
            >>> from thot.core.DictionaryTrie import Trie
            >>> trie = Trie()
            >>> trie.insert("ab", "TEST", True, "NN", {"id": 1}, 1.0)
            >>> trie["a"]["b"][Trie.LEAF]["label_info"]["TEST"]["data"]
            [{'id': 1}]
        """
        if len(string):
            self[string[0]].insert(
                string[1:], label, in_vocab, pos, data, weight
            )
        else:
            if Trie.LEAF not in self:
                self[Trie.LEAF] = {"label_info": dict(), "in_vocab": False}
            if label not in self[Trie.LEAF]["label_info"]:
                self[Trie.LEAF]["label_info"][label] = {
                    "pos": pos,
                    "data": [],
                    "weight": weight,
                }
            already_inserted = False
            if (Trie.LEAF in self) and (
                label in self[Trie.LEAF]["label_info"]
            ):
                for label_info_data_i in self[Trie.LEAF]["label_info"][label][
                    "data"
                ]:
                    if label_info_data_i == data:
                        already_inserted = True
                        break
            if not already_inserted:
                self[Trie.LEAF]["label_info"][label]["data"].append(data)
            else:
                ThotLogger.warning(
                    "Data "
                    + str(label_info_data_i)
                    + " already inserted in word '"
                    + str(self.current_string)
                    + "'"
                )
            self[Trie.LEAF]["in_vocab"] = in_vocab

    def __missing__(self, key):
        """Create a child trie node when a prefix is missing.

        Args:
            key: Missing prefix character.

        Returns:
            Newly created child ``Trie`` node.

        Example:
            >>> from thot.core.DictionaryTrie import Trie
            >>> trie = Trie()
            >>> child = trie["x"]
            >>> isinstance(child, Trie)
            True
        """
        self[key] = Trie()
        return self[key]
