from django.contrib import admin
from .models import Attendance, AttendanceSession


admin.site.register([AttendanceSession, Attendance])
# Register your models here.
