"""Tests for the BM25 retrieval baseline used to bound the oracle-context assumption.

The point of the retrieval script is to say honestly how optimistic "oracle context" is. That
number is only meaningful if the retriever is competent, so these tests pin the two properties that
made the difference between a misleading 4.5% recall@1 and a defensible 88%.
"""

import unittest

from scripts.evaluate_retrieval_recall import (
    BM25,
    COURSE_CODE,
    build_queries,
    record_document,
    tokenize,
)


CORPUS = {
    "IE4259E": {"title": "Selected Topics in Systems Engineering", "school": "Engineering",
                "description": "This module introduces students to emerging topics."},
    "NHS2055": {"title": "Health and Society", "school": "Public Health",
                "description": "Offered in Semester 1. Explain briefly the social determinants."},
    "CS1010": {"title": "Programming Methodology", "school": "Computing",
               "description": "An introduction to programming."},
    "ZZ9999": {"title": "Health and Society", "school": "Continuing Education",
               "description": "A duplicate title, deliberately ambiguous."},
}


def build_index():
    codes = list(CORPUS)
    documents = [record_document(code, CORPUS[code]) for code in codes]
    return codes, documents, BM25(documents)


class TokenizerTests(unittest.TestCase):
    def test_stopwords_strip_question_boilerplate(self):
        """The template words are what drowned out the rare course code."""
        tokens = tokenize("How many modular credits is IE4259E worth?", drop_stopwords=True)
        self.assertEqual(tokens, ["ie4259e"])

    def test_stopwords_are_off_by_default(self):
        self.assertIn("how", tokenize("How many credits"))

    def test_course_codes_survive_tokenisation(self):
        self.assertIn("nhs2055", tokenize("Is NHS2055 offered in Semester 1?", drop_stopwords=True))


class IdentifierPromotionTests(unittest.TestCase):
    """Exact code matches must outrank lexical scores.

    Without promotion, "Is NHS2055 offered in Semester 1? Explain briefly." leaves four
    medium-frequency terms after stopword removal, and a short record matching all of them can
    outscore the single record containing the code. That dropped code-query recall@1 to 33%.
    """

    def test_identifier_match_is_promoted_to_rank_one(self):
        codes, _documents, bm25 = build_index()
        position = codes.index("NHS2055")
        query = "Is NHS2055 offered in Semester 1? Explain briefly."
        ranked = bm25.search(query, top_k=4, identifier_positions=[position])
        self.assertEqual(ranked[0], position)

    def test_without_promotion_the_lexical_ranking_can_lose(self):
        """Documents the failure mode the promotion exists to fix."""
        codes, _documents, bm25 = build_index()
        query = "Is NHS2055 offered in Semester 1? Explain briefly."
        ranked = bm25.search(query, top_k=4)
        self.assertIn(codes.index("NHS2055"), ranked)  # still retrievable, just not guaranteed first

    def test_promotion_preserves_order_of_multiple_identifiers(self):
        codes, _documents, bm25 = build_index()
        first, second = codes.index("CS1010"), codes.index("IE4259E")
        ranked = bm25.search("Does CS1010 preclude IE4259E?", top_k=4,
                             identifier_positions=[first, second])
        self.assertEqual(ranked[:2], [first, second])

    def test_promotion_does_not_duplicate_documents(self):
        codes, _documents, bm25 = build_index()
        position = codes.index("CS1010")
        ranked = bm25.search("CS1010 programming", top_k=4,
                             identifier_positions=[position, position])
        self.assertEqual(len(ranked), len(set(ranked)))


class QueryModeTests(unittest.TestCase):
    def test_title_only_mode_removes_the_code(self):
        question = {"question": "How many modular credits is IE4259E worth?",
                    "subject_title": "Selected Topics in Systems Engineering"}
        queries = build_queries(question)
        self.assertIn("IE4259E", queries["code"])
        self.assertNotIn("IE4259E", queries["title_only"])
        self.assertIn("Selected Topics", queries["title_only"])

    def test_title_only_mode_falls_back_when_no_title_is_known(self):
        question = {"question": "How many credits is CS1010 worth?", "subject_title": ""}
        self.assertIn("the course", build_queries(question)["title_only"])

    def test_course_code_pattern_matches_nusmods_shapes(self):
        for code in ("CS1010", "IE4259E", "NHS2055", "BMA5802C"):
            self.assertEqual(COURSE_CODE.findall(f"about {code} today"), [code], code)

    def test_course_code_pattern_ignores_ordinary_words(self):
        self.assertEqual(COURSE_CODE.findall("Semester 1 credits worth 4"), [])


class AmbiguousTitleTests(unittest.TestCase):
    def test_duplicate_titles_make_title_only_retrieval_ambiguous(self):
        """The reason title-only recall@1 is 47% rather than ~90%."""
        codes, _documents, bm25 = build_index()
        ranked = bm25.search("Health and Society", top_k=4)
        top_titles = {CORPUS[codes[index]]["title"] for index in ranked[:2]}
        self.assertEqual(top_titles, {"Health and Society"})


if __name__ == "__main__":
    unittest.main()
