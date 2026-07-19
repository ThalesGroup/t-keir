"""Tests for automatic title generation."""

from thot.tasks.keywords.TitleGenerator import generate_missing_title


def _wikipedia_like_document() -> dict:
    return {
        "title": "",
        "content": [
            "Donate Create account Log in\n\nRob Brown (ice hockey)\n7 languages\n\nArticle\nTalk"
        ],
        "content_morphosyntax": [
            {
                "text": "Donate",
                "lemma": "donate",
                "pos": "VERB",
                "is_sent_start": True,
            },
            {
                "text": "Create",
                "lemma": "create",
                "pos": "VERB",
                "is_sent_start": False,
            },
            {
                "text": "account",
                "lemma": "account",
                "pos": "NOUN",
                "is_sent_start": False,
            },
            {
                "text": "Log",
                "lemma": "log",
                "pos": "VERB",
                "is_sent_start": False,
            },
            {
                "text": "in",
                "lemma": "in",
                "pos": "ADP",
                "is_sent_start": False,
            },
            {
                "text": "Rob",
                "lemma": "Rob",
                "pos": "PROPN",
                "is_sent_start": True,
            },
            {
                "text": "Brown",
                "lemma": "Brown",
                "pos": "PROPN",
                "is_sent_start": False,
            },
            {
                "text": "(",
                "lemma": "(",
                "pos": "PUNCT",
                "is_sent_start": False,
            },
            {
                "text": "ice",
                "lemma": "ice",
                "pos": "NOUN",
                "is_sent_start": False,
            },
            {
                "text": "hockey",
                "lemma": "hockey",
                "pos": "NOUN",
                "is_sent_start": False,
            },
            {
                "text": ")",
                "lemma": ")",
                "pos": "PUNCT",
                "is_sent_start": False,
            },
        ],
        "content_ner": [
            {"start": 5, "end": 7, "label": "person", "text": "Rob Brown"},
        ],
    }


class TestTitleGenerator:
    def test_generate_missing_title_prefers_early_named_entity(self):
        title = generate_missing_title(_wikipedia_like_document())
        assert title == "Rob Brown"

    def test_generate_missing_title_keeps_existing_title(self):
        document = _wikipedia_like_document()
        document["title"] = "Existing title"
        assert generate_missing_title(document) == ""

    def test_generate_missing_title_uses_keywords_when_no_ner(self):
        document = {
            "title": "",
            "content": ["Quarterly revenue growth exceeded expectations."],
            "content_morphosyntax": [
                {
                    "text": "Quarterly",
                    "lemma": "quarterly",
                    "pos": "ADJ",
                    "is_sent_start": True,
                },
                {
                    "text": "revenue",
                    "lemma": "revenue",
                    "pos": "NOUN",
                    "is_sent_start": False,
                },
                {
                    "text": "growth",
                    "lemma": "growth",
                    "pos": "NOUN",
                    "is_sent_start": False,
                },
                {
                    "text": "exceeded",
                    "lemma": "exceed",
                    "pos": "VERB",
                    "is_sent_start": False,
                },
                {
                    "text": "expectations",
                    "lemma": "expectation",
                    "pos": "NOUN",
                    "is_sent_start": False,
                },
            ],
        }
        content_keywords = [
            (12.0, "quarterly revenue growth", []),
        ]
        title = generate_missing_title(
            document,
            content_keywords=content_keywords,
        )
        assert title == "quarterly revenue growth"
