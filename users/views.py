from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from .models import Profile
from django.contrib.auth.decorators import user_passes_test


User = get_user_model()

admin_required = user_passes_test(lambda u: u.is_superuser, login_url="/login/")


@admin_required
def create_user(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        grade = request.POST.get("grade")
        section = request.POST.get("section")
        account = request.POST.get("account")
        phone_number = request.POST.get("phone_number")

        # Basic validation
        if not all(
            [username, email, password, confirm_password, grade, section, phone_number]
        ):
            messages.error(request, "All fields except account are required!")
            return redirect("create-user")

        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect("create-user")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists!")
            return redirect("create-user")

        # Create user
        user = User.objects.create(username=username, email=email)
        user.set_password(password)
        user.save()

        # Create profile
        Profile.objects.create(
            user=user,
            grade=grade,
            section=section,
            account=account or None,
            phone_number=phone_number,
        )

        messages.success(request, "User created successfully!")
        return redirect("create-user")

    return render(request, "users/create_user.html")


@admin_required
def users_list(request):
    profiles = Profile.objects.select_related("user").all()
    return render(request, "users/users_list.html", {"profiles": profiles})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from .models import User, Profile  # Ensure models are imported
from attendance.models import Attendance, AttendanceSession


# Helper function to ensure only staff/admins can access this view
def is_staff_or_admin(user):
    return user.is_staff or user.is_superuser


@transaction.atomic
def user_detail(request, user_id):
    """
    Displays comprehensive details, profile, and attendance analytics for a single user.
    """
    user_data = get_object_or_404(User, id=user_id)
    profile, created = Profile.objects.get_or_create(user=user_data)

    # 1. Fetch Total Session Count (Total possible attendances)
    total_sessions = AttendanceSession.objects.filter(targets=user_data).count()

    # 2. Fetch Attendance Counts
    attendance_counts = Attendance.objects.filter(user=user_data).aggregate(
        present_count=Count("status", filter=Q(status="present")),
        late_count=Count("status", filter=Q(status="late")),
        absent_count=Count("status", filter=Q(status="absent")),
    )

    present = attendance_counts["present_count"]
    late = attendance_counts["late_count"]
    absent = attendance_counts["absent_count"]

    marked_total = present + late + absent
    unmarked = total_sessions - marked_total

    # 3. Calculate Percentage (Avoid division by zero)
    if total_sessions > 0:
        present_percent = round((present / total_sessions) * 100, 1)
        late_percent = round((late / total_sessions) * 100, 1)
        absent_percent = round((absent / total_sessions) * 100, 1)
        unmarked_percent = round((unmarked / total_sessions) * 100, 1)

        # Overall Attendance Percentage (Present + Late)
        attendance_rate = round(((present + late) / total_sessions) * 100, 1)
    else:
        present_percent, late_percent, absent_percent, unmarked_percent = 0, 0, 0, 0
        attendance_rate = 0

    context = {
        "user_data": user_data,
        "profile_data": profile,
        "total_sessions": total_sessions,
        "attendance_rate": attendance_rate,
        "analytics": {
            "present": {"count": present, "percent": present_percent},
            "late": {"count": late, "percent": late_percent},
            "absent": {"count": absent, "percent": absent_percent},
            "unmarked": {"count": unmarked, "percent": unmarked_percent},
        },
        # Data formatted for Chart.js Pie Chart
        "chart_data": [present, late, absent, unmarked],
    }

    return render(request, "users/user_detail.html", context)


@transaction.atomic
def user_delete(request, user_id):
    """Handles the actual deletion of a user via POST request."""
    if request.method == "POST":
        user_to_delete = get_object_or_404(User, id=user_id)

        if user_to_delete.is_superuser and not request.user.is_superuser:
            messages.error(request, "You do not have permission to delete a superuser.")
            return redirect("user_detail", user_id=user_id)

        username = user_to_delete.username
        user_to_delete.delete()
        messages.success(
            request,
            f"User '{username}' and their profile have been successfully deleted.",
        )

        # Redirect to the main user list page or dashboard after deletion
        return redirect(
            "attendance_session_list"
        )  # Assuming this is your dashboard or user list page

    # If accessed via GET, redirect back to the detail page or another safe place
    return redirect("user_detail", user_id=user_id)


@transaction.atomic
def user_edit(request, user_id):
    user_to_edit = get_object_or_404(User, id=user_id)
    profile, created = Profile.objects.get_or_create(user=user_to_edit)

    if request.method == "POST":
        new_username = request.POST.get("username")

        if not new_username or new_username.strip() == "":
            messages.error(request, "Username cannot be empty.")
            return redirect("user_edit", user_id=user_id)

        grade = request.POST.get("grade", "")
        section = request.POST.get("section", "").upper()
        account = request.POST.get("account", "")
        phone_number = request.POST.get("phone_number", "")

        old = grade + section + account + phone_number + new_username
        new = (
            profile.grade
            + profile.section
            + profile.account
            + profile.phone_number
            + user_to_edit.username
        )

        if new == old:
            messages.warning(request, "Nothing change.")
            return redirect("user_detail", user_id=user_id)

        user_to_edit.username = new_username
        user_to_edit.save()

        profile.grade = grade
        profile.section = section
        profile.account = account
        profile.phone_number = phone_number
        profile.save()

        messages.success(
            request, f"User '{user_to_edit.username}' details updated successfully."
        )
        return redirect("user_detail", user_id=user_id)

    return render(
        request,
        "users/user_edit.html",
        {"user_data": user_to_edit, "profile_data": profile},
    )
