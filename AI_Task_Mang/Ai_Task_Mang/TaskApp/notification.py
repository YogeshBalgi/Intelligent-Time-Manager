from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Task, TaskSchedule, TaskNotification

def check_and_send_task_end_notifications(user):
    """
    Check tasks nearing their end time and send email notifications
    
    :param user: Django User object
    :return: List of notifications sent
    """
    # Get current time
    now = timezone.now()
    
    # Look for tasks within the next 30 minutes of their scheduled end time
    near_end_tasks = Task.objects.filter(
        user=user,
        completed=False,
        is_active=True,
        schedule__isnull=False,
        schedule__scheduled_end__lte=now + timedelta(minutes=30),
        schedule__scheduled_end__gt=now
    )
    
    notifications_sent = []
    
    for task in near_end_tasks:
        # Get the task schedule
        task_schedule = TaskSchedule.objects.get(task=task)
        
        # Check if notification already sent
        existing_notification = TaskNotification.objects.filter(
            user=user, 
            task=task, 
            is_read=False
        ).exists()
        
        if not existing_notification:
            # Prepare email content
            subject = f"Task Ending Soon: {task.title}"
            message = f"""
            Dear {user.username},

            This is a reminder that your task "{task.title}" is nearing its end time.

            Task Details:
            - Description: {task.description}
            - Scheduled End Time: {task_schedule.scheduled_end.strftime('%Y-%m-%d %H:%M %Z')}
            - Priority Score: {task_schedule.priority_score}

            Please ensure you complete or take necessary action for this task.

            Best regards,
            Your Task Management System
            """
            
            # Send email
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                
                # Create notification record
                TaskNotification.objects.create(
                    user=user,
                    task=task,
                    message=subject,
                    notification_time=now,
                    is_read=False
                )
                
                notifications_sent.append(task)
            
            except Exception as e:
                # Log the error (you might want to use Django's logging)
                print(f"Failed to send notification for task {task.title}: {str(e)}")
    
    return notifications_sent

# Optional: Management Command to run periodically
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Send task end time notifications to users'

    def handle(self, *args, **options):
        # Iterate through all active users
        for user in User.objects.filter(is_active=True):
            notifications = check_and_send_task_end_notifications(user)
            if notifications:
                self.stdout.write(self.style.SUCCESS(
                    f'Sent {len(notifications)} notifications to {user.username}'
                ))

# Middleware or Periodic Task Integration
def task_notification_middleware(get_response):
    def middleware(request):
        # If user is authenticated, check for task notifications
        if request.user.is_authenticated:
            check_and_send_task_end_notifications(request.user)
        
        response = get_response(request)
        return response
    return middleware