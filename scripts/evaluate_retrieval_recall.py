"""Measure how optimistic the study's oracle-context assumption is.

What the oracle-context arm assumes
-----------------------------------
Every flat-context result in this study hands the verifier the exact graph record it needs, selected
directly from the known expected triple. In retrieval terms that is **recall@1 = 100% with perfect
relation selection**. No deployed system achieves that, so every oracle-context number is an upper
bound. This script quantifies the gap instead of leaving it as a caveat.

What it measures
----------------
A real retriever over the 11,647 NUSMods module records: Okapi BM25 for lexical matching, optionally
followed by an `all-MiniLM-L6-v2` dense rerank of the BM25 candidates. For each question we ask
whether the record the verifier actually needs appears in the top *k*.

Two query modes, because they behave completely differently:

``code``
    The question as generated. NUSMods questions embed the course code ("How many modular credits is
    IE4259E worth?"), so this is the easy case and models the student who already knows the code.

``title_only``
    The same question with the code stripped and the course title substituted. This models the
    student who knows what a course is called but not its identifier, and it is the case that
    matters — the existing NIL stress test already showed title-only linking tops out at 57.2%
    accuracy because course titles are frequently ambiguous or duplicated.

Reporting the two modes separately keeps the conclusion honest: retrieval is close to free when an
identifier is present and expensive when it is not, so an institutional deployment should preserve
identifiers rather than assume retrieval quality is a solved problem.

No LLM calls. BM25 is implemented here rather than pulled in as a dependency.
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

TOKEN = re.compile(r"[a-z0-9]+")
COURSE_CODE = re.compile(r"\b[A-Z]{2,4}\d{4}[A-Z]?\b")

# Question templates are mostly function words plus catalogue boilerplate ("how many modular credits
# is X worth"). Without filtering, a short record that happens to repeat "modular", "credits" and
# "worth" outscores the one record containing the rare course code, and BM25 recall@1 collapses to
# 4.5% — a property of the query template, not of retrieval difficulty. Any competent retrieval
# baseline removes these, so the comparison uses one that does.
STOPWORDS = frozenset("""
a an and are as at be been but by can do does for from has have how i if in into is it its many
much of on or such that the their then there these they this to was what when where which who whose
will with would you your module modules course courses credit credits modular offered offer take
taken taking need needs needed require requires required worth carry carries list lists
""".split())


def tokenize(text, drop_stopwords=False):
    tokens = TOKEN.findall(str(text).lower())
    if drop_stopwords:
        return [token for token in tokens if token not in STOPWORDS]
    return tokens


def record_document(code, record):
    """Serialise a module record the way a retrieval index would store it."""
    parts = [code, str(record.get("title") or "")]
    if record.get("school"):
        parts.append(str(record["school"]))
    if record.get("department"):
        parts.append(str(record["department"]))
    if record.get("description"):
        parts.append(str(record["description"])[:600])
    return " ".join(parts)


class BM25:
    """Okapi BM25 over a fixed document collection."""

    def __init__(self, documents, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(document, drop_stopwords=True) for document in documents]
        self.doc_len = [len(tokens) for tokens in self.doc_tokens]
        self.avg_len = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        self.postings = defaultdict(list)
        for index, tokens in enumerate(self.doc_tokens):
            for term, count in Counter(tokens).items():
                self.postings[term].append((index, count))
        n_docs = len(documents)
        self.idf = {}
        for term, entries in self.postings.items():
            df = len(entries)
            # Standard BM25 idf with the +1 guard so common terms never go negative.
            self.idf[term] = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))

    def search(self, query, top_k, identifier_positions=()):
        """Rank documents for ``query``.

        ``identifier_positions`` are documents whose primary key appears verbatim in the query.
        They are promoted above the lexical ranking, which is what any real catalogue search does:
        an exact course-code match is a near-certain intent signal, not just another matching term.

        Without this, plain BM25 is misleading on identifier-bearing queries. "Is NHS2055 offered in
        Semester 1? Explain briefly." leaves four medium-frequency terms after stopword removal
        ("semester", "1", "explain", "briefly"), and a short record matching all four can outscore
        the single record containing the rare code. That is textbook BM25 behaviour rather than a
        bug, but scoring a retriever that ignores identifiers would understate what a competent
        deployment achieves and overstate the gap this script is trying to measure.
        """
        promoted = list(dict.fromkeys(identifier_positions))
        scores = defaultdict(float)
        for term in tokenize(query, drop_stopwords=True):
            if term not in self.postings:
                continue
            idf = self.idf[term]
            for index, count in self.postings[term]:
                norm = 1 - self.b + self.b * (self.doc_len[index] / self.avg_len or 0.0)
                scores[index] += idf * (count * (self.k1 + 1)) / (count + self.k1 * norm)
        ranked = [index for index, _score in
                  sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
        if promoted:
            promoted_set = set(promoted)
            ranked = promoted + [index for index in ranked if index not in promoted_set]
        return ranked[:top_k]


def build_queries(question):
    """Return the code-bearing and title-only forms of a question."""
    text = question["question"]
    title = question.get("subject_title") or ""
    stripped = COURSE_CODE.sub(title if title else "the course", text).strip()
    stripped = re.sub(r"\s+", " ", stripped)
    return {"code": text, "title_only": stripped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/nusmods_questions_200.jsonl")
    parser.add_argument("--graph", default="data/nusmods_graph.json")
    parser.add_argument("--cutoffs", type=int, nargs="+", default=[1, 3, 5, 10, 20, 50])
    parser.add_argument("--rerank_candidates", type=int, default=50,
                        help="BM25 candidates passed to the dense reranker; 0 disables reranking.")
    parser.add_argument("--output",
                        default="output/experiments/retrieval_recall_20260803/nusmods_retrieval_recall.json")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    questions = [json.loads(line) for line in
                 Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]

    codes = list(graph)
    documents = [record_document(code, graph[code]) for code in codes]
    code_index = {code: position for position, code in enumerate(codes)}
    bm25 = BM25(documents)

    reranker = None
    if args.rerank_candidates:
        try:
            from sentence_transformers import SentenceTransformer
            reranker = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"dense rerank unavailable ({exc}); reporting BM25 only")

    max_k = max(args.cutoffs)
    depth = max(max_k, args.rerank_candidates or 0)

    results = {}
    per_question = []
    for mode in ("code", "title_only"):
        hits = {k: 0 for k in args.cutoffs}
        rerank_hits = {k: 0 for k in args.cutoffs}
        ranks = []
        by_type = defaultdict(lambda: {"n": 0, "hit_at_1": 0, "hit_at_10": 0})
        for question in questions:
            target = str(question["subject"])
            if target not in code_index:
                continue
            query = build_queries(question)[mode]
            # Any course code appearing verbatim in the query and present in the corpus.
            identifier_positions = [
                code_index[code] for code in COURSE_CODE.findall(query) if code in code_index
            ]
            candidates = bm25.search(query, depth, identifier_positions)
            target_position = code_index[target]

            rank = candidates.index(target_position) + 1 if target_position in candidates else None
            for k in args.cutoffs:
                if rank is not None and rank <= k:
                    hits[k] += 1
            ranks.append(rank)

            reranked_rank = rank
            if reranker is not None and candidates:
                pool = candidates[: args.rerank_candidates]
                embeddings = reranker.encode(
                    [query] + [documents[index] for index in pool],
                    convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
                )
                similarity = embeddings[1:] @ embeddings[0]
                order = sorted(range(len(pool)), key=lambda i: -similarity[i])
                reordered = [pool[i] for i in order]
                # The reranker must not undo identifier promotion. Semantic similarity between a
                # question and a course record is a weak signal next to an exact code match, and
                # letting the dense stage outrank it dropped code-query recall@1 from 88% to 41%.
                if identifier_positions:
                    promoted = [index for index in identifier_positions if index in set(pool)]
                    reordered = promoted + [i for i in reordered if i not in set(promoted)]
                reranked_rank = (
                    reordered.index(target_position) + 1
                    if target_position in reordered else None
                )
            for k in args.cutoffs:
                if reranked_rank is not None and reranked_rank <= k:
                    rerank_hits[k] += 1

            bucket = by_type[question["question_type"]]
            bucket["n"] += 1
            bucket["hit_at_1"] += int((reranked_rank or 10**9) <= 1)
            bucket["hit_at_10"] += int((reranked_rank or 10**9) <= 10)
            per_question.append({
                "question_id": question["id"],
                "question_type": question["question_type"],
                "mode": mode,
                "subject": target,
                "query": query,
                "bm25_rank": rank,
                "reranked_rank": reranked_rank,
            })

        total = sum(1 for q in questions if str(q["subject"]) in code_index)
        results[mode] = {
            "n_questions": total,
            "bm25_recall_at_k": {str(k): hits[k] / total for k in args.cutoffs},
            "bm25_plus_dense_recall_at_k": (
                {str(k): rerank_hits[k] / total for k in args.cutoffs} if reranker else None
            ),
            "by_question_type_reranked": {
                name: {
                    "n": stats["n"],
                    "recall_at_1": stats["hit_at_1"] / stats["n"],
                    "recall_at_10": stats["hit_at_10"] / stats["n"],
                }
                for name, stats in sorted(by_type.items())
            },
        }

    output = {
        "protocol": {
            "corpus_size": len(codes),
            "questions": args.questions,
            "graph": args.graph,
            "retriever": "Okapi BM25 (k1=1.5, b=0.75)"
            + (" + all-MiniLM-L6-v2 dense rerank" if reranker else ""),
            "rerank_candidates": args.rerank_candidates if reranker else 0,
            "query_modes": {
                "code": "question as generated; contains the course code",
                "title_only": "course code replaced by the course title",
            },
            "comparison_point": (
                "The study's flat-context arm uses oracle selection, equivalent to recall@1 = 1.0 "
                "with perfect relation selection. Every oracle-context result is therefore an upper "
                "bound on retrieval-based deployment."
            ),
        },
        "results": results,
        "per_question": per_question,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"corpus: {len(codes)} records | retriever: {output['protocol']['retriever']}")
    for mode, payload in results.items():
        print(f"\n--- {mode} ---")
        print("  k     BM25    +dense")
        for k in args.cutoffs:
            bm = payload["bm25_recall_at_k"][str(k)]
            dense = payload["bm25_plus_dense_recall_at_k"]
            dense_value = f"{dense[str(k)]*100:6.1f}%" if dense else "     -"
            print(f"  {k:<5} {bm*100:6.1f}%  {dense_value}")
    print(f"\nsaved {output_path}")


if __name__ == "__main__":
    main()
