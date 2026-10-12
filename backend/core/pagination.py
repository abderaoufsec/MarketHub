"""Cursor (keyset) pagination for the endless feeds (docs/todo.md Phase 10).

Offset pagination makes Postgres walk and discard every row it skips, so
``LIMIT 20 OFFSET 20000`` reads 20 020 rows to return 20 and gets steadily
slower the further someone scrolls. A keyset cursor carries the *position* of
the last row instead: the database seeks straight to it and the page costs
the same at row 100 000 as it does at row 1.

The response shape is unchanged — ``{next, previous, results}``, exactly what
``PageNumberPagination`` produces, minus ``count``, which neither the
frontend nor any documented client reads. Cursor pagination is therefore
opt-in per view rather than a project-wide default: page numbers stay the
default for the endpoints where jumping backwards is a thing people do (an
order history, a seller's audit log).
"""

from rest_framework.pagination import CursorPagination


class FeedCursorPagination(CursorPagination):
    """Newest-first feed, 20 rows a page, client-settable up to 100.

    The ordering always ends in ``-id`` — see :meth:`get_ordering`.
    """

    #: DRF's cursor uses ``ordering[0]`` as the position and the rest only to
    #: make the sort total; without ``-id`` two rows created in the same
    #: second have interchangeable positions and one of them is repeated (or
    #: skipped) at the page boundary.
    ordering = ["-created_at", "-id"]

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_ordering(self, request, queryset, view):
        """``super()``, plus the uniqueness tiebreak the cursor needs.

        Ordering comes from the view's ``OrderingFilter`` when it has one, so
        it is whatever the client asked for (``?ordering=base_price``) and
        only defaults to the class attribute above otherwise.
        """
        ordering = list(super().get_ordering(request, queryset, view))
        if not any(field.lstrip("-") == "id" for field in ordering):
            ordering.append("-id")
        return ordering


class WishlistCursorPagination(FeedCursorPagination):
    """The same endless feed, newest-wishlist-entry first."""

    ordering = ["-added_at", "-id"]


class AuditCursorPagination(FeedCursorPagination):
    """The same endless feed, newest audit entry first."""

    ordering = ["-timestamp", "-id"]
