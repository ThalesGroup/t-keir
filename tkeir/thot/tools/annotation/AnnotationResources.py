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
    """Create an annotation Trie structure according the configuration file"""

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
        if not configuration:
            raise ValueError("Annotation description is mandatory")
        if not output:
            raise ValueError("Output file is mandatory")

    @staticmethod
    def _download_list_resource(list_item, resources_base_path):
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
        z = zipfile.ZipFile(os.path.join(basepath, list_item["path"]))
        ThotLogger.info("Extract to [" + basepath + "]")
        z.extractall(path=basepath)
        z.close()
        list_item["path"] = list_item["path"].replace(".zip", "")

    @staticmethod
    def _read_csv_dataframe(list_item, basepath):
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
        with open(os.path.join(basepath, list_item["path"])) as list_f:
            list_patterns = list_f.read().split("\n")
            list_f.close()
        return list_patterns, [], dict()

    @staticmethod
    def _load_list_patterns(list_item, basepath):
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
