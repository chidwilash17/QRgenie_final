"""
Pagination Classes
==================
Reusable DRF pagination classes for the QRGenie API.
"""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Default pagination for all list endpoints.

    Clients can control page size via ?page_size=N (up to max_page_size).
    Response shape:
        {
            "count":    <total items>,
            "next":     <next page URL or null>,
            "previous": <prev page URL or null>,
            "results":  [...]
        }
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class LargePagination(PageNumberPagination):
    """
    Larger page size for export-style endpoints (e.g. analytics tables).
    """
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500
