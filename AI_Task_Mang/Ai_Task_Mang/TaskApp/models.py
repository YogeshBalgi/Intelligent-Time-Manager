from django.db import models
from django.contrib.auth.models import User

class TaskSchedule(models.Model):
    task = models.OneToOneField('Task', on_delete=models.CASCADE, related_name='schedule')
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    priority_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-priority_score']

    def __str__(self):
        return f"Schedule for {self.task.title}"
    

class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    due_date = models.DateTimeField()  # Start time
    end_time = models.DateTimeField(null=True, blank=True)  # End time (add this field)
    estimated_time = models.FloatField()
    importance = models.IntegerField()
    urgency = models.IntegerField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    predicted_priority = models.FloatField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    has_feedback = models.BooleanField(default=False)
    
    @property
    def current_schedule(self):
        return self.schedule if hasattr(self, 'schedule') else None

    def __str__(self):
        return self.title


class UserFeedback(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    morning_energy = models.IntegerField(default=5)  # Energy level in the morning (1-5 scale)
    afternoon_energy = models.IntegerField(default=5)  # Energy level in the afternoon (1-5 scale)
    evening_energy = models.IntegerField(default=5)  # Energy level in the evening (1-5 scale)

    def __str__(self):
        return f"Feedback for {self.user.username}"


class TaskFeedback(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.CharField(max_length=11, choices=[('Effective', 'Effective'), ('Neutral', 'Neutral'), ('Ineffective', 'Ineffective')])
    completed_on_time = models.BooleanField(default=False)
    feedback_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.task.title} by {self.user.username}"


class TaskHistory(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    old_priority = models.FloatField()  # Store the old priority
    new_priority = models.FloatField()  # Store the new priority
    change_date = models.DateTimeField(auto_now_add=True)  # Track when the change occurred

    def __str__(self):
        return f"Priority change for {self.task.title} on {self.change_date}"

from django.db import models
from django.contrib.auth.models import User

class TaskNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notification_time = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']