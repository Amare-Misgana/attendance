from django.contrib.auth.decorators import user_passes_test
from users.models import Profile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from .models import AttendanceSession, Attendance
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, F
import pandas as pd
import io
import json

User = get_user_model()

admin_required = user_passes_test(lambda u: u.is_superuser, login_url="/login/")


@admin_required
def dashboard(request):
    profiles = Profile.objects.select_related("user").all()
    attendance_sessions = AttendanceSession.objects.all().count()
    users = profiles.count()
    context = {
        "profiles": profiles,
        "users": users,
        "attendance_sessions": attendance_sessions,
    }
    return render(request, "attendance/dashboard.html", context)


@admin_required
@transaction.atomic
def create_attendance_session(request):
    """
    Renders the page with filterable profiles and handles AJAX POST to create the session.
    """
    if request.method == "POST":

        try:
            data = json.loads(request.body)
            title = data.get("title")
            target_ids = data.get("targets", [])  # These are User IDs
        except json.JSONDecodeError:
            messages.error(request, "Invalid data received.")
            return redirect("create_attendance_session")

        if not title or title.strip() == "":
            messages.error(request, "Session title is required.")
            return redirect("create_attendance_session")

        if not target_ids:
            messages.warning(request, "No users were selected for this session.")
            return redirect("create_attendance_session")

        session = AttendanceSession.objects.create(title=title)

        # Targets are User objects, but they are filtered using Profile in the UI.
        # We still use User.objects.filter(id__in=target_ids) to link them to the session.
        targets = User.objects.filter(id__in=target_ids)
        session.targets.set(targets)

        messages.success(
            request,
            f"Session '{session.title}' created successfully with {targets.count()} targets.",
        )

        return JsonResponse(
            {
                "success": True,
                "redirect_url": redirect(
                    "attendance_session_detail", session_id=session.id
                ).url,
            }
        )

    # --- Handle GET Request (Render Page) ---

    # 1. Get all non-staff profiles, ordered by grade and section
    all_profiles = (
        Profile.objects.select_related("user")
        .filter(user__is_staff=False)  # Exclude staff/admins
        .order_by("grade", "section", "user__username")
    )

    # 2. Get unique grades and sections for dropdown filters
    unique_grades = (
        Profile.objects.values_list("grade", flat=True).distinct().order_by("grade")
    )
    unique_sections = (
        Profile.objects.values_list("section", flat=True).distinct().order_by("section")
    )

    return render(
        request,
        "attendance/create_session.html",
        {
            "all_profiles": all_profiles,
            "unique_grades": unique_grades,
            "unique_sections": unique_sections,
        },
    )


@admin_required
def attendance_session_detail(request, session_id):
    """
    Displays the session status and handles marking attendance for a single user via POST.
    """
    session = get_object_or_404(AttendanceSession, id=session_id)

    # Handle manual marking (POST request from the status buttons)
    if request.method == "POST" and not session.is_ended:
        user_id = request.POST.get("user_id")
        status = request.POST.get("status")

        if user_id and status in ["present", "late", "absent"]:
            # Find the user and ensure they are a target
            user = get_object_or_404(User, id=user_id)
            if not session.targets.filter(id=user.id).exists():
                # Should not happen if the UI is correct, but safe check
                messages.warning(
                    request, f"{user.username} is not a target for this session."
                )
                return redirect("attendance_session_detail", session_id=session.id)

            # Update or Create Attendance record
            Attendance.objects.update_or_create(
                session=session,
                user=user,
                defaults={"status": status, "attended_at": timezone.now()},
            )
            messages.success(request, f"Marked {user.username} as {status}.")
            return redirect("attendance_session_detail", session_id=session.id)

    # --- Prepare Data for GET Request (Rendering) ---

    # Get all targets (Users) and their associated profiles for sorting and display
    targets_with_profiles = (
        User.objects.filter(attendance_sessions=session)
        .select_related("profile")
        .order_by("profile__grade", "profile__section", "username")
    )

    # Get existing attendance records to create a status map
    existing_records = Attendance.objects.filter(session=session)
    attendance_map = {record.user_id: record.status for record in existing_records}

    # Compile the final list for the template
    attendance_list = []
    for user in targets_with_profiles:
        # Get the profile data
        profile = getattr(user, "profile", None)

        attendance_list.append(
            {
                "user": user,
                "profile": profile,
                "status": attendance_map.get(
                    user.id, "unmarked"
                ),  # Default to 'unmarked'
            }
        )

    return render(
        request,
        "attendance/session_detail.html",
        {"session": session, "attendance_list": attendance_list},
    )


@admin_required
@transaction.atomic
def close_attendance_session(request, session_id):
    """
    Finalizes the attendance session. It finds all target users who do not have
    an Attendance record yet and sets their status to 'absent'.
    """
    session = get_object_or_404(AttendanceSession, id=session_id)

    # We require a POST request for this irreversible action
    if request.method == "POST":

        if session.is_ended:
            messages.warning(request, "This session is already closed.")
            return redirect("attendance_session_detail", session_id=session.id)

        # 1. Get IDs of users who have ALREADY been marked (present/late/absent)
        marked_user_ids = Attendance.objects.filter(session=session).values_list(
            "user_id", flat=True
        )

        # 2. Identify users from the session's targets who are MISSING an attendance record
        # Note: session.targets is a ManyToMany field, so we query it directly.
        missing_users = session.targets.exclude(id__in=marked_user_ids)

        # 3. Prepare 'Absent' records for bulk insertion
        to_create = [
            Attendance(session=session, user=user, status="absent")
            for user in missing_users
        ]

        # Bulk create is highly efficient for inserting many rows
        Attendance.objects.bulk_create(to_create)

        # 4. Mark the session as ended
        session.is_ended = True
        session.save()

        count = len(to_create)
        messages.success(
            request,
            f"Session finalized! {count} unmarked users were automatically set to Absent.",
        )

    # Always redirect back to the session detail page to show the final state
    return redirect("attendance_session_detail", session_id=session.id)


@admin_required
def attendance_session_list(request):
    """
    Displays a list of all attendance sessions with summary statistics.
    FIX: Changed 'attendance' to 'attendances' in annotation filters.
    """

    sessions = AttendanceSession.objects.annotate(
        # Count of all targets linked via the ManyToMany field
        target_count=Count("targets", distinct=True),
        # Count of specific statuses (using the correct related name: 'attendances')
        present_count=Count(
            "attendances",  # <--- CORRECTED from 'attendance'
            filter=Q(
                attendances__status="present"
            ),  # <--- CORRECTED from 'attendance__status'
            distinct=True,
        ),
        late_count=Count(
            "attendances",  # <--- CORRECTED from 'attendance'
            filter=Q(
                attendances__status="late"
            ),  # <--- CORRECTED from 'attendance__status'
            distinct=True,
        ),
        absent_count=Count(
            "attendances",  # <--- CORRECTED from 'attendance'
            filter=Q(
                attendances__status="absent"
            ),  # <--- CORRECTED from 'attendance__status'
            distinct=True,
        ),
        # Unmarked count calculation remains correct
        unmarked_count=F("target_count")
        - F("present_count")
        - F("late_count")
        - F("absent_count"),
    ).order_by("-created_at")

    return render(request, "attendance/session_list.html", {"sessions": sessions})


@admin_required
def export_users_excel(request):
    """Generates an Excel file with User and Profile data."""

    # 1. Fetch Data
    users_with_profile = (
        User.objects.select_related("profile").all().order_by("username")
    )

    user_profile_data = []
    for user in users_with_profile:
        # Check if the user has a profile
        profile = getattr(user, "profile", None)

        data = {
            "Username": user.username,
            "Email": user.email,
            # Use data from Profile, checking for existence
            "Grade": profile.grade if profile else "",
            "Section": profile.section if profile else "",
            "Account": profile.account if profile else "",
            "Phone Number": profile.phone_number if profile else "",
        }
        user_profile_data.append(data)

    # 2. Create DataFrame
    df_profile = pd.DataFrame(user_profile_data)

    # 3. Write to Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_profile.to_excel(writer, sheet_name="User_Profiles", index=False)

        # Optional: Auto-adjust column widths
        workbook = writer.book
        worksheet = workbook["User_Profiles"]
        for column in worksheet.columns:
            max_length = 0
            column_name = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = max_length + 2
            worksheet.column_dimensions[column_name].width = adjusted_width

    # 4. Prepare Response
    excel_data = output.getvalue()
    response = HttpResponse(
        excel_data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="users_report.xlsx"'

    return response


@admin_required
def export_attendance_matrix_excel(request):
    """Generates an Excel file with the Attendance Matrix."""

    all_students = (
        User.objects.filter(profile__isnull=False).order_by("username").only("username")
    )

    all_sessions = AttendanceSession.objects.all().order_by("created_at")

    attendance_records = Attendance.objects.select_related("session", "user").all()

    attendance_lookup = {
        (record.user_id, record.session_id): record.status
        for record in attendance_records
    }

    attendance_matrix_data = []
    session_titles = [session.title for session in all_sessions]

    columns = ["User"] + session_titles

    for student in all_students:
        row = {"User": student.username}

        for session in all_sessions:

            status = attendance_lookup.get((student.id, session.id), "N/A")
            row[session.title] = status

        attendance_matrix_data.append(row)

    df_attendance = pd.DataFrame(attendance_matrix_data, columns=columns)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_attendance.to_excel(writer, sheet_name="Attendance_Matrix", index=False)

        workbook = writer.book
        worksheet = workbook["Attendance_Matrix"]
        for column in worksheet.columns:
            max_length = 0
            column_name = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = max_length + 2
            worksheet.column_dimensions[column_name].width = adjusted_width

    excel_data = output.getvalue()
    response = HttpResponse(
        excel_data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="attendance_matrix_report.xlsx"'
    )

    return response
