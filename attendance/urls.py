from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path(
        "export/attendance",
        views.export_attendance_matrix_excel,
        name="export_attendance",
    ),
    path("export/users", views.export_users_excel, name="export_users"),
    path(
        "session/create/",
        views.create_attendance_session,
        name="create_attendance_session",
    ),
    path("sessions/", views.attendance_session_list, name="attendance_session_list"),
    path(
        "session/<int:session_id>/",
        views.attendance_session_detail,
        name="attendance_session_detail",  # <--- This name must match the one used in the redirect() function
    ),
    path(
        "session/<int:session_id>/close/",
        views.close_attendance_session,
        name="close_attendance_session",  # The name used in the detail template's form action
    ),
]
