import numpy as np
from datetime import timedelta
import pytz
from django.utils.timezone import now
from .dqn_prioritizer import DQNPrioritizer
from .models import Task, UserFeedback, TaskFeedback,TaskSchedule
import logging  # Import the DQNPrioritizer class
logger = logging.getLogger(__name__)

# Initialize the DQN task prioritizer
state_size = 3  # Attributes: importance, urgency, estimated_time
action_size = 5  # Number of actions (should dynamically adjust)
prioritizer = DQNPrioritizer(state_size, action_size)

# Normalize task attributes for DQN model
def normalize_task(task):
    """
    Normalize task attributes for model input.
    Assumes `importance`, `urgency`, and `estimated_time` are present in task.
    """
    max_importance = 5
    max_urgency = 5
    max_estimated_time = 8  # Assuming 8 hours as max time for a task

    return np.array([
        task['importance'] / max_importance,
        task['urgency'] / max_urgency,
        min(task['estimated_time'] / max_estimated_time, 1.0)  # Cap at 1.0
    ])

# DQN-Based Task Prioritization
def prioritize_tasks_with_dqn(tasks):
    timezone = pytz.timezone('Asia/Kolkata')
    current_time = now().astimezone(timezone)
    daily_schedule = []

    # Initialize DQN prioritizer
    state_size = 3  # importance, urgency, estimated_time
    action_size = 5
    prioritizer = DQNPrioritizer(state_size, action_size)

    for task in tasks:
        if not task.due_date or not task.estimated_time:
            continue

        # Calculate priority using DQN
        task_state = np.array([
            task.importance / 5,
            task.urgency / 5,
            min(task.estimated_time / 8, 1.0)
        ])
        priority_score = prioritizer.prioritizer.act(task_state)

        # Update task's predicted priority in database
        task.predicted_priority = float(priority_score)
        task.save()

        if task.due_date.tzinfo is None:
            task.due_date = timezone.localize(task.due_date)

        time_remaining = (task.due_date - current_time).total_seconds() / 3600
        if time_remaining <= 0:
            continue

        estimated_time = task.estimated_time
        if estimated_time <= time_remaining:
            start_time = current_time
            end_time = current_time + timedelta(hours=estimated_time)
        else:
            start_time = current_time
            end_time = task.due_date

        daily_schedule.append({
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'importance': task.importance,
            'urgency': task.urgency,
            'start_time': start_time,
            'end_time': end_time,
            'predicted_priority': float(priority_score),  # Add priority score here
            'score': float(priority_score)  # Add this as well for backwards compatibility
        })

        current_time = end_time

    # Sort tasks by priority
    daily_schedule.sort(key=lambda x: x['predicted_priority'], reverse=True)
    return daily_schedule

# Rule-Based Prioritization (Fallback)
def rule_based_prioritization(tasks, energy_levels):
    prioritized_tasks = []

    for task in tasks:
        importance = getattr(task, 'importance', 3)
        urgency = getattr(task, 'urgency', 3)
        estimated_time = getattr(task, 'estimated_time', 1)
        start_time = getattr(task, 'start_time', None)
        end_time = getattr(task, 'end_time', None)

        if estimated_time <= 2:
            energy_level = energy_levels['morning']
        elif estimated_time <= 4:
            energy_level = energy_levels['afternoon']
        else:
            energy_level = energy_levels['evening']

        energy_level = energy_level / 5

        task_score = (
            (0.4 * (importance / 5)) +
            (0.4 * (urgency / 5)) +
            (0.2 * energy_level) -
            (0.1 * estimated_time)
        )

        prioritized_tasks.append({
            'title': task.title,
            'score': task_score,
            'importance': importance,
            'urgency': urgency,
            'estimated_time': estimated_time,
            'start_time': start_time,
            'end_time': end_time,
        })

    prioritized_tasks.sort(key=lambda x: x['score'], reverse=True)

    return prioritized_tasks

def create_task_schedule(task):
    """
    Creates a TaskSchedule entry for a given task using DQN-based scheduling.
    """
    try:
        # Initialize scheduler
        from .scheduler import DQNTaskScheduler
        scheduler = DQNTaskScheduler()

        # Create a list with the single task for scheduling
        scheduled_tasks = scheduler.schedule_tasks([task])

        # If a schedule was created
        if scheduled_tasks:
            schedule = scheduled_tasks[0]
            return schedule
        
        # Fallback if no schedule created
        priority_score = (task.importance + task.urgency) / 2
        scheduled_start = task.due_date
        scheduled_end = scheduled_start + timedelta(hours=task.estimated_time)
        
        schedule, created = TaskSchedule.objects.update_or_create(
            task=task,
            defaults={
                'scheduled_start': scheduled_start,
                'scheduled_end': scheduled_end,
                'priority_score': priority_score
            }
        )
        
        return schedule
    
    except Exception as e:
        logger.error(f"Error creating schedule for task {task.id}: {str(e)}")
        return None