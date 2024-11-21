"""
URL configuration for Ai_Task_Mang project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home, name='home'),  # Home page
    path('index/', views.index, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('', views.login_view, name='login'), 
    path('add-task/', views.add_task, name='add_task'),
    path('schedule/', views.schedule, name='schedule'),
    path('task_prioritization/', views.task_prioritization_view, name='task_prioritization'),
    #path('logout/', views.logout_view, name='logout'),
    #path('feedback/', views.give_feedback, name='give_feedback'),
    path('feedback/thank-you/', views.feedback_thank_you, name='feedback_thank_you'),
    path('submit-feedback/<int:task_id>/', views.submit_task_feedback, name='submit_task_feedback'),
    path('analytics/', views.task_analytics, name='task_analytics'),
    path('check-notifications/', views.check_task_notifications, name='check_notifications'),

]
