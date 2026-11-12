"""Postgres full-text search + trigram fallback (Phase 15).

The engine decision in docs/todo.md is "Postgres FTS + ``pg_trgm`` first,
Meilisearch/Typesense if that is not enough". This module is the whole of the
first half:

* exact matching uses ``to_tsvector('french', search_document)``;
* French stemming makes *voiture*/*voitures* one lexeme, and it leaves Arabic
  words intact (the Arabic work is done in ``normalization``);
* when the exact query finds nothing, a *per-token* trigram word-similarity
  pass catches typos (``samsug`` → ``samsung``) and mixed queries
  (``galaxy samsug``) without ever falling back to "return everything".

The ``SEARCH_BACKEND`` setting names a service class, not this module, so a
future external engine can implement the same interface.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramWordSimilarity,
)
from django.db.models import FloatField, Q, Value
from django.db.models.functions import Greatest

from .normalization import tokenize
from .synonyms import expand_query

#: PostgreSQL text-search configuration. ``french`` gives stemming and
#: stopwords for the language most listings are written in; Arabic tokens
#: pass through unchanged because PostgreSQL has no Arabic stemmer.
SEARCH_CONFIG = "french"

#: A synonym group can be wide; 12 OR-ed spellings is already far beyond
#: what a person types, and keeps the tsquery readable in logs.
MAX_TERMS_PER_GROUP = 12

#: PostgreSQL returns a tiny non-zero rank (``1e-20``) for an *empty* tsquery
#: produced entirely by stopwords. Treating ``rank > 0`` as a match therefore
#: turns nonsense queries into "return the whole catalogue"; real matches rank
#: orders of magnitude higher.
MIN_SEARCH_RANK = 1e-10


def build_tsquery(text: str):
    """AND over synonym groups, OR inside each group; ``None`` if empty."""
    combined = None
    for group in expand_query(text):
        group_query = None
        for term in sorted(group)[:MAX_TERMS_PER_GROUP]:
            query = SearchQuery(term, config=SEARCH_CONFIG, search_type="plain")
            group_query = query if group_query is None else group_query | query
        if group_query is None:
            continue
        combined = group_query if combined is None else combined & group_query
    return combined


def _vector():
    return SearchVector("search_document", config=SEARCH_CONFIG)


def _ranked(queryset, tsquery):
    return queryset.annotate(
        search_rank=SearchRank(_vector(), tsquery),
        fuzzy_score=Value(0.0, output_field=FloatField()),
    )


def _fuzzy_queryset(queryset, text: str, threshold: float):
    """Every query token must match by FTS *or* by trigram similarity.

    That keeps a two-word typo query precise ("galaxy samsug" does not
    degrade into "any product called Galaxy"). ``word_similarity`` compares
    the token to the best word in the document, which is exactly what an
    indexed trigram on a short token should do.
    """
    tokens = [token for token in tokenize(text) if len(token) >= 4 and not token.isdigit()]
    if not tokens:
        return None
    tokens = tokens[:5]
    vector = _vector()
    annotations = {}
    condition = None
    similarities = []
    for index, token in enumerate(tokens):
        rank_alias = f"token_rank_{index}"
        sim_alias = f"token_similarity_{index}"
        annotations[rank_alias] = SearchRank(
            vector, SearchQuery(token, config=SEARCH_CONFIG, search_type="plain")
        )
        annotations[sim_alias] = TrigramWordSimilarity(token, "search_document")
        token_condition = Q(**{f"{rank_alias}__gt": MIN_SEARCH_RANK}) | Q(
            **{f"{sim_alias}__gte": threshold}
        )
        condition = token_condition if condition is None else condition & token_condition
        similarities.append(sim_alias)

    queryset = queryset.annotate(**annotations).filter(condition)
    return queryset.annotate(
        fuzzy_score=Greatest(*similarities, Value(0.0, output_field=FloatField())),
        search_rank=Value(0.0, output_field=FloatField()),
    )


def apply_text_search(queryset, text: str):
    """Return ``(queryset, used_fuzzy)`` for a free-text query.

    Both returned querysets carry ``search_rank`` and ``fuzzy_score``
    annotations, so the caller can order by relevance without knowing which
    branch ran. An empty/stopword-only query is a no-op.
    """
    tsquery = build_tsquery(text or "")
    if tsquery is None:
        return queryset, False

    exact = _ranked(queryset, tsquery).filter(search_rank__gt=MIN_SEARCH_RANK)
    if exact.exists():
        return exact, False

    threshold = float(getattr(settings, "SEARCH_FUZZY_THRESHOLD", 0.45))
    fuzzy = _fuzzy_queryset(queryset, text, threshold)
    if fuzzy is not None and fuzzy.exists():
        return fuzzy, True
    return exact, False


def queryset_matches(queryset, text: str):
    """``queryset`` filtered by the same exact-or-fuzzy rules as the API."""
    return apply_text_search(queryset, text)[0]


__all__ = [
    "SEARCH_CONFIG",
    "apply_text_search",
    "build_tsquery",
    "queryset_matches",
]
