from django.utils import timezone
import pytz
from datetime import datetime, timedelta
from .models import Task, TaskSchedule
import numpy as np
from .reinforcement_learning import DQNTaskPrioritizer

class DQNTaskScheduler:
    def __init__(self, state_size=4, action_size=24):
        self.state_size = state_size
        self.action_size = action_size
        self.dqn_prioritizer = DQNTaskPrioritizer(state_size, action_size)
        self.ist_timezone = pytz.timezone('Asia/Kolkata')

    def schedule_tasks(self, tasks):
        """Schedule tasks using DQN while respecting sleep time constraints"""
        current_time = timezone.now()
        end_time = current_time + timedelta(days=7)
        scheduled_tasks = []
        
        # Sort tasks by initial DQN priority
        task_priorities = []
        for task in tasks:
            if task.completed or not task.is_active:
                continue
                
            state = self.normalize_task_state(task, current_time)
            priority = self.dqn_prioritizer.act(state)
            task_priorities.append((task, priority))
        
        # Sort by priority (highest first)
        task_priorities.sort(key=lambda x: x[1], reverse=True)
        
        # Schedule each task
        current_schedule_time = current_time
        for task, priority in task_priorities:
            if task.due_date < current_time:
                continue
            
            available_slots = self.get_available_time_slots(
                current_schedule_time,
                min(task.due_date, end_time)
            )
            
            if not available_slots:
                continue
                
            best_start_time = None
            best_score = float('-inf')
            
            for slot in available_slots:
                state = self.normalize_task_state(task, slot)
                score = self.dqn_prioritizer.act(state)
                
                if score > best_score:
                    best_score = score
                    best_start_time = slot
            
            if best_start_time:
                task_end_time = best_start_time + timedelta(hours=task.estimated_time)
                
                while self.is_sleep_time(task_end_time):
                    task_end_time += timedelta(hours=1)
                
                schedule, created = TaskSchedule.objects.update_or_create(
                    task=task,
                    defaults={
                        'scheduled_start': best_start_time,
                        'scheduled_end': task_end_time,
                        'priority_score': best_score
                    }
                )
                
                scheduled_tasks.append(schedule)
                current_schedule_time = task_end_time
        
        return scheduled_tasks

    def normalize_task_state(self, task, current_time):
        """Create normalized state vector for DQN input"""
        time_until_due = (task.due_date - current_time).total_seconds() / 3600
        max_time_horizon = 168
        
        return np.array([
            task.importance / 5,
            task.urgency / 5,
            min(task.estimated_time / 8, 1.0),
            min(time_until_due / max_time_horizon, 1.0)
        ])

    def is_sleep_time(self, time):
        """Check if given time falls in sleep hours (1 AM to 6 AM IST)"""
        hour = time.astimezone(self.ist_timezone).hour
        return 1 <= hour < 6

    def get_available_time_slots(self, start_time, end_time):
        """Get available time slots excluding sleep hours"""
        current_time = start_time
        available_slots = []
        
        while current_time < end_time:
            if not self.is_sleep_time(current_time):
                available_slots.append(current_time)
            current_time += timedelta(hours=1)
            
        return available_slots

    def update_model(self, task_feedback):
        """Update DQN model based on task feedback"""
        task = task_feedback.task
        
        reward_mapping = {
            'Effective': 1.0,
            'Neutral': 0.0,
            'Ineffective': -0.5
        }
        
        base_reward = reward_mapping.get(task_feedback.rating, 0.0)
        completion_bonus = 0.5 if task_feedback.completed_on_time else -0.3
        total_reward = base_reward + completion_bonus
        
        current_state = self.normalize_task_state(task, task.schedule.scheduled_start)
        next_state = self.normalize_task_state(task, task.schedule.scheduled_end)
        
        self.dqn_prioritizer.remember(
            current_state,
            self.dqn_prioritizer.act(current_state),
            total_reward,
            next_state,
            True
        )
        
        self.dqn_prioritizer.replay(batch_size=32)