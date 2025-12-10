from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages


def home(request):
    try:
        if request.user:
            is_authenticated = True
    except Exception as e:
        is_authenticated = False
    context = {"is_authenticated": is_authenticated}
    return render(request, "public/home.html", context)


def login_page(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        next_url = request.POST.get("next") or request.GET.get("next") or None
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Logged in successfully!")
            if next_url:
                return redirect(next_url)
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password")
            return render(request, "public/login.html")

    return render(request, "public/login.html")
