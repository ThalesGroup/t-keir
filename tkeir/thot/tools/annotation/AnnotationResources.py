"""Title: Annotation resources

It reads a configuration file in JSON format. This file contains link to resources (like list, syntactic dictionary ..)

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os
import pickle
import string
import tempfile
import traceback
import zipfile

import pandas as pd
import requests
from fold_to_ascii import fold

from thot.core.DictionaryTrie import Trie
from thot.core.ThotLogger import ThotLogger
from thot.tools.annotation import __date_annotation__, __version_annotation__


class AnnotationResources:
    """Create an annotation Trie structure from a configuration file.

    Example:
        >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
        >>> callable(AnnotationResources.createModel)
        True
    """

    @staticmethod
    def _pattern_text(value):
        """Normalize a lexicon cell value into a stripped string or ``None``.

        Args:
            value: Raw CSV/list cell value.

        Returns:
            Stripped string when non-empty, otherwise ``None``.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._pattern_text("  Hello  ")
            'Hello'
            >>> AnnotationResources._pattern_text(None) is None
            True
            >>> AnnotationResources._pattern_text("   ") is None
            True
        """
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if not isinstance(value, str):
            value = str(value)
        value = value.strip()
        return value or None

    @staticmethod
    def _validate_create_model_inputs(configuration, output):
        """Validate required arguments for :meth:`createModel`.

        Args:
            configuration: Annotation JSON configuration dict.
            output: Destination pickle path.

        Raises:
            ValueError: When ``configuration`` or ``output`` is missing.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> try:
            ...     AnnotationResources._validate_create_model_inputs(None, "out.pkl")
            ... except ValueError as err:
            ...     "mandatory" in str(err)
            ... else:
            ...     False
            True
        """
        if not configuration:
            raise ValueError("Annotation description is mandatory")
        if not output:
            raise ValueError("Output file is mandatory")

    @staticmethod
    def _download_list_resource(list_item, resources_base_path):
        """Download and extract a remote list resource when configured.

        Args:
            list_item: List resource entry from annotation configuration.
            resources_base_path: Local directory for extracted files.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._download_list_resource({}, "/tmp")  # doctest: +SKIP
        """
        if "download" not in list_item:
            return
        if "url" not in list_item["download"]:
            ThotLogger.error("With download option you must give url")
            return
        try:
            r = requests.get(list_item["download"]["url"])
            tmpzip = os.path.join(tempfile.gettempdir(), "tmp.zip")
            with open(tmpzip, "wb") as fzip:
                fzip.write(r.content)
                fzip.close()
            z = zipfile.ZipFile(tmpzip)
            ThotLogger.info("Extract to [" + resources_base_path + "]")
            z.extractall(path=resources_base_path)
            z.close()
            os.remove(tmpzip)
        except Exception as e:
            ThotLogger.error(
                "Cannot download '"
                + list_item["download"]["url"]
                + "' exception:"
                + str(e)
                + ", trace:"
                + str(traceback.format_exc())
            )

    @staticmethod
    def _load_pattern_exceptions(list_item, basepath):
        """Load exception patterns that suppress list entries.

        Args:
            list_item: List resource entry with optional ``exceptions`` paths.
            basepath: Base directory for exception list files.

        Returns:
            Set of raw exception strings.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     exc = os.path.join(td, "skip.txt")
            ...     _ = open(exc, "w").write("bad\\n")
            ...     out = AnnotationResources._load_pattern_exceptions(
            ...         {"exceptions": ["skip.txt"]}, td)
            ...     "bad" in out
            True
        """
        pattern_exception = set()
        if "exceptions" not in list_item:
            return pattern_exception
        if not isinstance(list_item["exceptions"], list):
            list_item["exceptions"] = [list_item["exceptions"]]
        for except_i in list_item["exceptions"]:
            try:
                with open(os.path.join(basepath, except_i)) as exc_f:
                    pattern_exception = set(exc_f.read().split("\n"))
                    exc_f.close()
            except Exception:
                ThotLogger.error("Cannot open file '" + except_i + "'")
        return pattern_exception

    @staticmethod
    def _read_list_metadata(list_item):
        """Read label, POS, and weight metadata from a list entry.

        Args:
            list_item: List resource configuration dict.

        Returns:
            Tuple ``(label, pos, weight)``.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._read_list_metadata(
            ...     {"label": "ORG", "pos": "NOUN", "weight": 2})
            ('ORG', 'NOUN', 2)
        """
        label = None
        pos = "NOUN"
        weight = 1
        if "label" in list_item:
            label = list_item["label"]
        else:
            ThotLogger.error("Label must be set")
        if "pos" in list_item:
            pos = list_item["pos"]
        else:
            ThotLogger.warning("POS should be set, default is NOUN")
        if "weight" in list_item:
            weight = list_item["weight"]
        return label, pos, weight

    @staticmethod
    def _extract_csv_zip(list_item, basepath):
        """Extract a ``csv-zip`` list archive beside its source path.

        Args:
            list_item: List entry whose ``path`` ends with ``.zip``.
            basepath: Directory containing the zip file.

        Example:
            >>> import io, os, tempfile, zipfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     zpath = os.path.join(td, "items.zip")
            ...     with zipfile.ZipFile(zpath, "w") as zf:
            ...         zf.writestr("items.csv", "term\\n")
            ...     item = {"path": "items.zip"}
            ...     AnnotationResources._extract_csv_zip(item, td)
            ...     item["path"]
            'items'
        """
        z = zipfile.ZipFile(os.path.join(basepath, list_item["path"]))
        ThotLogger.info("Extract to [" + basepath + "]")
        z.extractall(path=basepath)
        z.close()
        list_item["path"] = list_item["path"].replace(".zip", "")

    @staticmethod
    def _read_csv_dataframe(list_item, basepath):
        """Read a CSV list resource into a pandas DataFrame.

        Args:
            list_item: List entry with ``path`` and ``format`` metadata.
            basepath: Directory containing the CSV file.

        Returns:
            Parsed CSV dataframe.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     csv_path = os.path.join(td, "items.csv")
            ...     _ = open(csv_path, "w").write("term\\nAlpha\\n")
            ...     df = AnnotationResources._read_csv_dataframe(
            ...         {"path": "items.csv", "format": {"sep": ",", "header": True}},
            ...         td,
            ...     )
            ...     list(df.iloc[:, 0].values)
            ['Alpha']
        """
        sep = ","
        if "sep" in list_item["format"]:
            sep = list_item["format"]["sep"]
        csv_path = os.path.join(basepath, list_item["path"])
        if ("headers" in list_item["format"]) and (
            not list_item["format"]["header"]
        ):
            return pd.read_csv(csv_path, sep=sep, header=None)
        return pd.read_csv(csv_path, sep=sep, low_memory=False)

    @staticmethod
    def _parse_csv_columns(list_item, df):
        """Parse CSV column metadata from a list configuration entry.

        Args:
            list_item: List entry with optional ``format.columns`` specs.
            df: Loaded CSV dataframe.

        Returns:
            Tuple ``(columns, concept_type, concept_parent_col)``.

        Example:
            >>> import pandas as pd
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> df = pd.DataFrame([["Alpha", "Parent"]])
            >>> cols, concepts, parent = AnnotationResources._parse_csv_columns(
            ...     {"format": {"columns": [
            ...         {"id": "0", "concept-type": "instance"},
            ...         {"id": "1", "concept-type": "parent-instance"},
            ...     ]}},
            ...     df,
            ... )
            >>> parent
            1
        """
        columns = dict()
        concept_type = dict()
        concept_parent_col = -1
        if "columns" in list_item["format"]:
            for column_i in list_item["format"]["columns"]:
                if "id" not in column_i:
                    ThotLogger.error("CSV column id undefined")
                    continue
                spliton = ""
                if "split-on" in column_i:
                    spliton = column_i["split-on"]
                columns[int(column_i["id"])] = spliton
                if "concept-type" in column_i:
                    concept_type[int(column_i["id"])] = column_i[
                        "concept-type"
                    ]
                    if column_i["concept-type"] == "parent-instance":
                        concept_parent_col = int(column_i["id"])
                columns[int(column_i["id"])] = spliton
        else:
            for col_i in range(len(df.columns)):
                columns[col_i] = ""
        return columns, concept_type, concept_parent_col

    @staticmethod
    def _append_column_patterns(
        df, col_i, columns, concept_parent_col, concept_col_list
    ):
        """Extract patterns and optional concept ids from one CSV column.

        Args:
            df: Source CSV dataframe.
            col_i: Column index to read.
            columns: Parsed column split metadata.
            concept_parent_col: Parent concept column index, or ``-1``.
            concept_col_list: Parent concept values aligned to dataframe rows.

        Returns:
            Tuple ``(patterns, concepts)``.

        Example:
            >>> import pandas as pd
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> df = pd.DataFrame([["Alpha"], ["Beta"]])
            >>> patterns, concepts = AnnotationResources._append_column_patterns(
            ...     df, 0, {0: ""}, -1, [])
            >>> patterns
            ['Alpha', 'Beta']
        """
        list_patterns = []
        list_concepts = []
        if not columns[col_i]:
            term_list = list(df.iloc[:, col_i].values)
            for term in term_list:
                pattern_text = AnnotationResources._pattern_text(term)
                if pattern_text:
                    list_patterns.append(pattern_text)
            if concept_parent_col != -1:
                list_concepts = list_concepts + concept_col_list
            return list_patterns, list_concepts

        rows_to_split = list(df.iloc[:, col_i].values)
        for ri_id in range(len(rows_to_split)):
            ri = rows_to_split[ri_id]
            pattern_text = AnnotationResources._pattern_text(ri)
            if not pattern_text:
                continue
            multiple_pattern = pattern_text.split(columns[col_i])
            for mpi in multiple_pattern:
                mpi_text = AnnotationResources._pattern_text(mpi)
                if mpi_text:
                    list_patterns.append(mpi_text)
            if concept_parent_col != -1:
                list_concepts.append(concept_col_list[ri_id])
        return list_patterns, list_concepts

    @staticmethod
    def _load_patterns_from_csv(list_item, basepath):
        """Load lexicon patterns from a CSV or csv-zip list resource.

        Args:
            list_item: List entry describing CSV format and path.
            basepath: Directory containing list files.

        Returns:
            Tuple ``(patterns, concepts, concept_type)``.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     _ = open(os.path.join(td, "items.csv"), "w").write("term\\nAlpha\\n")
            ...     patterns, concepts, concept_type = AnnotationResources._load_patterns_from_csv(
            ...         {"path": "items.csv", "format": {"type": "csv", "sep": ",", "header": True}},
            ...         td,
            ...     )
            ...     patterns
            ['Alpha']
        """
        list_patterns = []
        list_concepts = []
        concept_type = dict()
        try:
            if list_item["format"]["type"] == "csv-zip":
                AnnotationResources._extract_csv_zip(list_item, basepath)
            df = AnnotationResources._read_csv_dataframe(list_item, basepath)
            columns, concept_type, concept_parent_col = (
                AnnotationResources._parse_csv_columns(list_item, df)
            )
            concept_col_list = []
            if concept_parent_col != -1:
                concept_col_list = list(df.iloc[:, concept_parent_col].values)
            for col_i in columns:
                try:
                    col_patterns, col_concepts = (
                        AnnotationResources._append_column_patterns(
                            df,
                            col_i,
                            columns,
                            concept_parent_col,
                            concept_col_list,
                        )
                    )
                    list_patterns.extend(col_patterns)
                    list_concepts.extend(col_concepts)
                except Exception as e:
                    ThotLogger.error(
                        "Error int file '"
                        + list_item["path"]
                        + "' Exception:"
                        + str(e)
                        + ", Trace:"
                        + str(traceback.format_exc())
                    )
        except Exception as e:
            ThotLogger.error(
                "Error int file '"
                + list_item["path"]
                + "' Exception:"
                + str(e)
                + ", Trace:"
                + str(traceback.format_exc())
            )
        return list_patterns, list_concepts, concept_type

    @staticmethod
    def _load_patterns_from_list_file(list_item, basepath):
        """Load newline-separated patterns from a plain list file.

        Args:
            list_item: List entry with ``path`` to a text file.
            basepath: Directory containing the list file.

        Returns:
            Tuple ``(patterns, [], {})`` for downstream registration.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     _ = open(os.path.join(td, "items.txt"), "w").write("Alpha\\nBeta\\n")
            ...     patterns, _, _ = AnnotationResources._load_patterns_from_list_file(
            ...         {"path": "items.txt"}, td)
            ...     patterns[:2]
            ['Alpha', 'Beta']
        """
        with open(os.path.join(basepath, list_item["path"])) as list_f:
            list_patterns = list_f.read().split("\n")
            list_f.close()
        return list_patterns, [], dict()

    @staticmethod
    def _load_list_patterns(list_item, basepath):
        """Dispatch pattern loading based on list ``format.type``.

        Args:
            list_item: List resource configuration entry.
            basepath: Directory containing list files.

        Returns:
            Tuple ``(patterns, concepts, concept_type)``.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     _ = open(os.path.join(td, "items.txt"), "w").write("Alpha\\n")
            ...     patterns, _, _ = AnnotationResources._load_list_patterns(
            ...         {"path": "items.txt", "format": {"type": "list"}}, td)
            ...     patterns[0]
            'Alpha'
        """
        list_patterns = []
        list_concepts = []
        concept_type = dict()
        if "format" not in list_item:
            ThotLogger.error("Format is not defined.")
            return list_patterns, list_concepts, concept_type
        if "type" not in list_item["format"]:
            ThotLogger.error("Format is not defined, not type.")
            return list_patterns, list_concepts, concept_type
        format_loaders = {
            "csv": AnnotationResources._load_patterns_from_csv,
            "csv-zip": AnnotationResources._load_patterns_from_csv,
            "list": AnnotationResources._load_patterns_from_list_file,
        }
        loader = format_loaders.get(list_item["format"]["type"])
        if loader is None:
            return list_patterns, list_concepts, concept_type
        return loader(list_item, basepath)

    @staticmethod
    def _is_punctuation_only_pattern(pattern_i):
        """Return whether a pattern contains only punctuation, digits, or spaces.

        Args:
            pattern_i: Lowercased pattern string.

        Returns:
            ``True`` when every character is punctuation, digit, or space.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._is_punctuation_only_pattern("!!!")
            True
            >>> AnnotationResources._is_punctuation_only_pattern("alpha")
            False
        """
        word_with_punct = set(pattern_i) & set(
            string.punctuation + "0123456789 "
        )
        pattern_set_len = len(set(pattern_i))
        return len(word_with_punct) == pattern_set_len

    @staticmethod
    def _append_pattern_entry(
        patterns,
        remove_duplicate,
        pattern_i,
        label,
        pos,
        data_type,
        weight,
        concept_type,
        list_concepts,
        e_i,
    ):
        """Append one lexicon pattern unless it was already registered.

        Args:
            patterns: Mutable pattern list being built.
            remove_duplicate: Set of ``pattern#label#pos`` keys already seen.
            pattern_i: Lowercased pattern text.
            label: Entity label for the pattern.
            pos: Part-of-speech tag.
            data_type: Annotation data type string.
            weight: Pattern weight.
            concept_type: Parsed concept-type metadata for the source column.
            list_concepts: Parallel concept ids for CSV rows.
            e_i: Index into ``list_concepts`` for this pattern.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns, seen = [], set()
            >>> AnnotationResources._append_pattern_entry(
            ...     patterns, seen, "acme", "ORG", "NOUN", "named-entity", 1, {}, [], 0)
            >>> patterns[0]["label"]
            'ORG'
        """
        duplicate_id = pattern_i + "#" + label + "#" + pos
        if duplicate_id in remove_duplicate:
            return
        entry = {
            "pattern": pattern_i,
            "label": label,
            "pos": pos,
            "data": {"type": data_type},
            "weight": weight,
        }
        if concept_type:
            entry["data"]["concept"] = list_concepts[e_i]
        patterns.append(entry)
        remove_duplicate.add(duplicate_id)

    @staticmethod
    def _append_ascii_folded_pattern(
        patterns,
        remove_duplicate,
        pattern_i,
        label,
        pos,
        data_type,
        weight,
    ):
        """Append an ASCII-folded duplicate of a pattern when it differs.

        Args:
            patterns: Mutable pattern list being built.
            remove_duplicate: Set of folded ``pattern#label#pos`` keys seen.
            pattern_i: Lowercased source pattern text.
            label: Entity label for the pattern.
            pos: Part-of-speech tag.
            data_type: Annotation data type string.
            weight: Pattern weight.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns, seen = [], set()
            >>> AnnotationResources._append_ascii_folded_pattern(
            ...     patterns, seen, "café", "ORG", "NOUN", "named-entity", 1)
            >>> patterns[0]["pattern"]
            'cafe'
        """
        duplicate_id = fold(pattern_i) + "#" + label + "#" + pos
        if duplicate_id in remove_duplicate:
            return
        fold_pattern = fold(pattern_i)
        if len(fold_pattern) == len(pattern_i):
            patterns.append(
                {
                    "pattern": fold_pattern,
                    "label": label,
                    "pos": pos,
                    "data": {"type": data_type},
                    "weight": weight,
                }
            )
        remove_duplicate.add(duplicate_id)

    @staticmethod
    def _register_list_patterns(
        list_patterns,
        list_item,
        label,
        pos,
        weight,
        pattern_exception,
        concept_type,
        list_concepts,
        remove_duplicate,
        patterns,
    ):
        """Normalize and register all patterns from one list resource.

        Args:
            list_patterns: Raw pattern strings loaded from a list file.
            list_item: Source list configuration entry.
            label: Entity label applied to every pattern.
            pos: Part-of-speech tag.
            weight: Pattern weight.
            pattern_exception: Set of raw patterns to skip.
            concept_type: Parsed concept-type metadata.
            list_concepts: Parallel concept ids for CSV rows.
            remove_duplicate: Set of duplicate keys already registered.
            patterns: Mutable output pattern list.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns, seen = [], set()
            >>> AnnotationResources._register_list_patterns(
            ...     ["Acme"], {"type": "named-entity"}, "ORG", "NOUN", 1,
            ...     set(), {}, [], seen, patterns)
            >>> patterns[0]["pattern"]
            'acme'
        """
        for e_i in range(len(list_patterns)):
            pattern_text = AnnotationResources._pattern_text(
                list_patterns[e_i]
            )
            if not pattern_text:
                continue
            pattern_i = pattern_text.lower()
            if AnnotationResources._is_punctuation_only_pattern(pattern_i):
                continue
            data_type = "named-entity"
            add_ascii_folding = list_item.get("add-ascii-folding", False)
            if "type" in list_item:
                data_type = list_item["type"]
            if pattern_text in pattern_exception:
                continue
            AnnotationResources._append_pattern_entry(
                patterns,
                remove_duplicate,
                pattern_i,
                label,
                pos,
                data_type,
                weight,
                concept_type,
                list_concepts,
                e_i,
            )
            if add_ascii_folding:
                AnnotationResources._append_ascii_folded_pattern(
                    patterns,
                    remove_duplicate,
                    pattern_i,
                    label,
                    pos,
                    data_type,
                    weight,
                )

    @staticmethod
    def _process_list_item(list_item, basepath, remove_duplicate, patterns):
        """Load one configured list resource and append its patterns.

        Args:
            list_item: List resource configuration entry.
            basepath: Directory containing list files.
            remove_duplicate: Set of duplicate keys already registered.
            patterns: Mutable output pattern list.

        Example:
            >>> import os, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> with tempfile.TemporaryDirectory() as td:
            ...     _ = open(os.path.join(td, "items.txt"), "w").write("Acme\\n")
            ...     patterns, seen = [], set()
            ...     AnnotationResources._process_list_item(
            ...         {"path": "items.txt", "label": "ORG",
            ...          "format": {"type": "list"}},
            ...         td, seen, patterns)
            ...     patterns[0]["label"]
            'ORG'
        """
        AnnotationResources._download_list_resource(list_item, basepath)
        if "name" in list_item:
            ThotLogger.info("Load '" + list_item["name"] + "'")
        pattern_exception = AnnotationResources._load_pattern_exceptions(
            list_item, basepath
        )
        list_patterns = []
        list_concepts = []
        concept_type = dict()
        label = None
        pos = "NOUN"
        weight = 1
        if ("path" in list_item) and os.path.isfile(
            os.path.join(basepath, list_item["path"])
        ):
            label, pos, weight = AnnotationResources._read_list_metadata(
                list_item
            )
            if label and ("format" in list_item):
                list_patterns, list_concepts, concept_type = (
                    AnnotationResources._load_list_patterns(
                        list_item, basepath
                    )
                )
            else:
                ThotLogger.error("Format is not defined.")
        else:
            ThotLogger.error("Resource file problem")
        ThotLogger.info(
            "Add ["
            + str(len(list_patterns))
            + "] items from ["
            + list_item["path"]
            + "]"
        )
        AnnotationResources._register_list_patterns(
            list_patterns,
            list_item,
            label,
            pos,
            weight,
            pattern_exception,
            concept_type,
            list_concepts,
            remove_duplicate,
            patterns,
        )

    @staticmethod
    def _maybe_add_punctuated_word(patterns, p_i, words_hash):
        """Track single-token patterns containing punctuation for later lookup.

        Args:
            patterns: Pattern list being normalized.
            p_i: Index of the current pattern in ``patterns``.
            words_hash: Mutable set of punctuated single-word forms.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns = [{"pattern": "u.s.a."}]
            >>> words = set()
            >>> AnnotationResources._maybe_add_punctuated_word(patterns, 0, words)
            >>> "u.s.a." in words
            True
        """
        word_with_punct = set(patterns[p_i]["pattern"]) & set(
            string.punctuation + "0123456789"
        )
        pattern_set_len = len(set(patterns[p_i]["pattern"]))
        pattern_len = len(patterns[p_i]["pattern"])
        if (
            (pattern_len < 512)
            and len(word_with_punct)
            and (len(word_with_punct) != pattern_set_len)
        ):
            words_hash.add(patterns[p_i]["pattern"].lower())

    @staticmethod
    def _hyphen_split_tokens(entity_items, hyphen_letter):
        """Split hyphenated entity tokens while preserving delimiter tokens.

        Args:
            entity_items: Whitespace-separated entity token list.
            hyphen_letter: Delimiter character, ``-`` or ``&``.

        Returns:
            Lowercased token list with delimiter tokens preserved.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._hyphen_split_tokens(["New-York"], "-")
            ['new', '-', 'york']
        """
        lower_pattern = []
        for e_i in entity_items:
            if hyphen_letter in e_i:
                toks = e_i.split(hyphen_letter)
                for ti in range(len(toks)):
                    lower_pattern.append(toks[ti].lower())
                    if ti != (len(toks) - 1):
                        lower_pattern.append(hyphen_letter)
            else:
                lower_pattern.append(e_i.lower())
        return lower_pattern

    @staticmethod
    def _expand_hyphen_patterns(patterns):
        """Normalize patterns to token tuples and expand hyphen variants.

        Args:
            patterns: Mutable pattern dict list with string ``pattern`` keys.

        Returns:
            Tuple ``(words_hash, delete_pattern)`` for downstream pruning.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns = [{
            ...     "label": "ORG", "pattern": "New-York", "pos": "NOUN",
            ...     "data": {"type": "named-entity"}, "weight": 1,
            ... }]
            >>> words, deleted = AnnotationResources._expand_hyphen_patterns(patterns)
            >>> patterns[0]["pattern"]
            ('New-York',)
        """
        words_hash = set()
        delete_pattern = set()
        count_patterns = len(patterns)
        for p_i in range(count_patterns):
            if len(patterns[p_i]["pattern"]) > 2048:
                ThotLogger.error(
                    "Sequence '" + patterns[p_i]["pattern"] + "' too long"
                )
                delete_pattern.add(p_i)
                continue
            asHyphen = ("-" in patterns[p_i]["pattern"]) or (
                "&" in patterns[p_i]["pattern"]
            )
            hyphen_letter = "&" if "&" in patterns[p_i]["pattern"] else "-"
            entity_items = patterns[p_i]["pattern"].split(" ")
            if len(entity_items) == 1:
                AnnotationResources._maybe_add_punctuated_word(
                    patterns, p_i, words_hash
                )
            patterns[p_i]["pattern"] = tuple(entity_items)
            patterns[p_i]["in_vocab"] = True
            if asHyphen:
                lower_pattern = AnnotationResources._hyphen_split_tokens(
                    entity_items, hyphen_letter
                )
                patterns.append(
                    {
                        "label": patterns[p_i]["label"],
                        "pattern": tuple(lower_pattern),
                        "pos": patterns[p_i]["pos"],
                        "data": patterns[p_i]["data"],
                        "weight": patterns[p_i]["weight"],
                        "in_vocab": True,
                    }
                )
        return words_hash, delete_pattern

    @staticmethod
    def _compute_max_lengths(patterns, words_hash):
        """Compute maximum pattern and punctuated-word lengths.

        Args:
            patterns: Normalized pattern dict list with tuple ``pattern`` keys.
            words_hash: Set of punctuated single-word forms.

        Returns:
            Tuple ``(max_pattern_length, max_word_len)``.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources._compute_max_lengths([], {"ab"})[1]
            2
        """
        max_pattern_length = 0
        max_word_len = 0
        for pi in patterns:
            if len(pi) > max_pattern_length:
                max_pattern_length = len(pi)
        for w in words_hash:
            if len(w) > max_word_len:
                max_word_len = len(w)
        return max_pattern_length, max_word_len

    @staticmethod
    def _finalize_and_persist_model(patterns, output):
        """Prune, build the trie, and pickle the compiled annotation model.

        Args:
            patterns: Raw pattern dict list collected from list resources.
            output: Destination pickle path.

        Example:
            >>> import os, pickle, tempfile
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> patterns = [{
            ...     "label": "ORG", "pattern": "Acme", "pos": "NOUN",
            ...     "data": {"type": "named-entity"}, "weight": 1,
            ... }]
            >>> with tempfile.TemporaryDirectory() as td:
            ...     out = os.path.join(td, "model.pkl")
            ...     AnnotationResources._finalize_and_persist_model(patterns, out)
            ...     "trie" in pickle.load(open(out, "rb"))
            True
        """
        words_hash, delete_pattern = (
            AnnotationResources._expand_hyphen_patterns(patterns)
        )
        max_pattern_length, max_word_len = (
            AnnotationResources._compute_max_lengths(patterns, words_hash)
        )
        pruned_patterns = []
        for pi in range(len(patterns)):
            if pi not in delete_pattern:
                pruned_patterns.append(patterns[pi])

        mwes = Trie(pruned_patterns)
        mwes_data = {
            "punctuated-words": list(words_hash),
            "trie": mwes,
            "max-pattern-length": max_pattern_length,
            "max-word-length": max_word_len,
            "version": __version_annotation__,
            "date": __date_annotation__,
        }
        ThotLogger.info(
            "Save '"
            + output
            + "' with '"
            + str(len(patterns))
            + "' patterns and a max size of '"
            + str(max_pattern_length)
            + "'"
            + " and '"
            + str(len(words_hash))
            + "' simple words with a size max of '"
            + str(max_word_len)
            + "'. "
        )
        with open(output, "wb") as pd_f:
            pickle.dump(mwes_data, pd_f)
            pd_f.close()

    @staticmethod
    def createModel(configuration=None, output=None):
        """Build and persist an MWE trie from annotation configuration.

        Args:
            configuration: Annotation JSON configuration with ``data`` and
                ``resources-base-path`` entries.
            output: Destination pickle path for the compiled trie.

        Raises:
            ValueError: When ``configuration`` or ``output`` is missing.

        Example:
            >>> from thot.tools.annotation.AnnotationResources import AnnotationResources
            >>> AnnotationResources.createModel({"data": []}, "/tmp/out.pkl")  # doctest: +SKIP
        """
        AnnotationResources._validate_create_model_inputs(
            configuration, output
        )

        if "data" not in configuration:
            return

        for data_i in configuration["data"]:
            patterns = []
            basepath = configuration["resources-base-path"]
            if "lists" not in data_i:
                continue
            remove_duplicate = set()
            for list_item in data_i["lists"]:
                AnnotationResources._process_list_item(
                    list_item, basepath, remove_duplicate, patterns
                )
            AnnotationResources._finalize_and_persist_model(patterns, output)
