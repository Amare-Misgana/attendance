from django.urls import path
from . import views

urlpatterns = [
    path("create/", views.create_user, name="create-user"),
    path("user/<int:user_id>/", views.user_detail, name="user_detail"),
    path(
        "user/<int:user_id>/edit/",
        views.user_edit,
        name="user_edit",
    ),
    path("user/<int:user_id>/delete/", views.user_delete, name="user_delete"),
]
