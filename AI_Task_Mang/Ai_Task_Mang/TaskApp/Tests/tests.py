import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Task_Mang.settings')

import django
django.setup()



from django.test import TestCase
import unittest
from datetime import datetime, timedelta
import pytz
from TaskApp.dqn_prioritizer import DQNPrioritizer
from TaskApp.reinforcement_learning import DQNTaskPrioritizer
from TaskApp.utils import normalize_task, prioritize_tasks_with_dqn, rule_based_prioritization
from TaskApp.views import schedule, add_task
from django.test import RequestFactory
from django.contrib.auth.models import User
from TaskApp.models import Task  # Assuming Task model exists

# Create your tests here.
class TestTaskScheduling(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='Yo', password='Yo')

        Task.objects.bulk_create([
            Task(
                title='Task 1',
                due_date=datetime.now(pytz.UTC) + timedelta(hours=4),
                estimated_time=2,
                importance=5,
                urgency=4,
                user=self.user
            ),
            Task(
                title='Task 2',
                due_date=datetime.now(pytz.UTC) + timedelta(hours=2),
                estimated_time=3,
                importance=3,
                urgency=5,
                user=self.user
            )
        ])

    def test_schedule_view(self):
        request = self.factory.get('/schedule/')
        request.user = self.user
        response = schedule(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Task 2', response.content)  # Task 2 should be scheduled first
