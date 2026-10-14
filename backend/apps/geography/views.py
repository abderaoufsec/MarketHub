from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Commune, Wilaya
from .serializers import CommuneSerializer, WilayaSerializer


class WilayaListView(generics.ListAPIView):
    """Public, cacheable list of the 69 Algerian wilayas (Phase 11).

    Deliberately unpaginated: 69 rows that change once every few years. The
    SPA fetches this once and keeps it in memory, so the response shape stays
    a plain array instead of a pagination envelope.
    """

    serializer_class = WilayaSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    queryset = Wilaya.objects.filter(is_active=True)


class CommuneListView(generics.ListAPIView):
    """Communes of one wilaya: ``/api/v1/geography/wilayas/<code>/communes/``.

    ``?search=`` matches French or Arabic names (icontains) — enough for the
    picker's type-ahead until Phase 15's search work lands. Also unpaginated:
    the largest wilaya has ~70 communes.
    """

    serializer_class = CommuneSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        wilaya = get_object_or_404(Wilaya, code=self.kwargs["code"], is_active=True)
        qs = Commune.objects.filter(wilaya=wilaya, is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name_fr__icontains=search) | qs.filter(name_ar__icontains=search)
        return qs
