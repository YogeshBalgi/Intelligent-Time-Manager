import numpy as np
from datetime import timedelta
import pytz
from django.utils.timezone import now

from TaskApp.reinforcement_learning import DQNTaskPrioritizer

class DQNPrioritizer:
    def __init__(self, state_size, action_size):
        self.prioritizer = DQNTaskPrioritizer(state_size, action_size)

    def normalize_task(self, task):
        return np.array([
            task.importance / 5,
            task.urgency / 5,
            min(task.estimated_time / 8, 1.0)
        ])

    def prioritize_tasks(self, tasks):
        timezone = pytz.timezone('Asia/Kolkata')
        current_time = now().astimezone(timezone)

        task_states = np.array([self.normalize_task(task) for task in tasks])
        predicted_priorities = [self.prioritizer.act(state) for state in task_states]

        sorted_tasks = sorted(
            zip(tasks, predicted_priorities), key=lambda x: x[1], reverse=True
        )
        return [task[0] for task in sorted_tasks]
