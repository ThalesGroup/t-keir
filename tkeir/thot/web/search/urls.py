from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("status", views.status, name="status"),
    path("querying", views.querying, name="querying"),
    path("query_with_doc", views.query_with_doc, name="query_with_doc"),
    path("doc", views.querying, name="doc"),
    path("suggester", views.suggester, name="suggester"),
]
