from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Profile(models.Model):
    FIELD_CHOICE = [
        ("frontend", "Frontend"),
        ("backend", "Backend"),
        ("ai", "AI"),
        ("embadded", "Embadded"),
        ("cyber", "Cyber"),
        ("other", "Other"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    grade = models.CharField(max_length=20)
    section = models.CharField(max_length=20)
    field = models.CharField(max_length=50, choices=FIELD_CHOICE, default="frontend")
    account = models.CharField(max_length=100, default="N/A")
    phone_number = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.user.username} - {self.grade}"
