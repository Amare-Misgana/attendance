from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AttendanceSession(models.Model):
    title = models.CharField(max_length=150)
    targets = models.ManyToManyField(
        User, related_name="attendance_sessions", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_ended = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("present", "Present"),
        ("late", "Late"),
        ("absent", "Absent"),
    ]
    session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="attendances"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendances")
    attended_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="absent")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"], name="unique_session_user_attendance"
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.session}"
