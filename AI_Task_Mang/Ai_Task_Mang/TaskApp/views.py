from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils.timezone import localtime
from datetime import datetime
import pytz
import numpy as np
from django.utils import timezone
from .models import Task, UserFeedback, TaskFeedback,TaskSchedule
from .utils import rule_based_prioritization,prioritize_tasks_with_dqn,normalize_task
from .dqn_prioritizer import DQNPrioritizer
from django.db import transaction
from .notification import check_and_send_task_end_notifications


# Initialize DQN model
STATE_SIZE = 3  # Example: importance, urgency, estimated_time
ACTION_SIZE = 10  # Adjust according to your tasks
dqn_model = DQNPrioritizer(state_size=STATE_SIZE, action_size=ACTION_SIZE)


def home(request):
    # Check if the user is authenticated
    if request.user.is_authenticated:
        return redirect('index')  # Redirect to the `index.html` page
    else:
        return render(request, 'home.html')  # Render the `home.html` page
    
def index(request):
    return render(request, 'index.html')

@login_required
def add_task(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        due_date = request.POST.get('due_date')
        estimated_time = request.POST.get('estimated_time')
        importance = request.POST.get('importance')
        urgency = request.POST.get('urgency')

        try:
            due_date_obj = datetime.strptime(due_date, '%Y-%m-%dT%H:%M')
            ist_timezone = pytz.timezone('Asia/Kolkata')
            localized_due_date = ist_timezone.localize(due_date_obj)
        except ValueError:
            messages.error(request, 'Invalid date format. Please use YYYY-MM-DDTHH:MM format.')
            return redirect('add_task')

        # Create task
        task = Task.objects.create(
            title=title,
            description=description,
            due_date=localized_due_date,
            estimated_time=float(estimated_time),
            importance=int(importance),
            urgency=int(urgency),
            user=request.user
        )

        # Create task schedule using DQN-based scheduling
        from .utils import create_task_schedule
        create_task_schedule(task)

        messages.success(request, 'Task added successfully!')
        return redirect('/schedule/')

    return render(request, 'add_task.html')

def get_task_states(tasks):
    """
    Extracts the state representation for each task.
    Modifies priority to use predicted_priority or a calculation based on task fields.
    """
    task_states = []
    for task in tasks:
        # Example state representation
        state = {
            'predicted_priority': task.predicted_priority if task.predicted_priority is not None else (task.importance + task.urgency) / 2,  # Calculate if missing
            'due_in_days': (task.due_date - timezone.now()).days if task.due_date else float('inf'),  # Days until due
            'estimated_time': task.estimated_time,  # Time required
            'completed': task.completed,  # Task completion status
        }
        task_states.append(state)
    return task_states

@login_required
def check_task_notifications(request):
    # Manually trigger notifications
    notifications = check_and_send_task_end_notifications(request.user)
    messages.info(request, f'Checked and sent {len(notifications)} notifications')
    return redirect('schedule')


import logging
import traceback
import os

logger = logging.getLogger(__name__)

from .scheduler import DQNTaskScheduler

@login_required
@login_required
def schedule(request):
    try:
        # Get IST timezone and current date
        india_timezone = pytz.timezone('Asia/Kolkata')
        current_datetime = datetime.now(india_timezone)
        current_date = current_datetime.date()

        # Get tasks for today
        active_tasks = Task.objects.filter(
            user=request.user,
            completed=False,
            is_active=True,
            due_date__date=current_date
        )

        # Initialize empty daily schedule
        daily_schedule = []

        # Process each task
        for task in active_tasks:
            # Check for notification for tasks nearing end time
            #check_task_notification(task)

            task_schedule = TaskSchedule.objects.filter(task=task).first()

            if task_schedule:
                # Add scheduled task with schedule times
                daily_schedule.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'importance': task.importance,
                    'urgency': task.urgency,
                    'start_time': task_schedule.scheduled_start,
                    'end_time': task_schedule.scheduled_end,
                    'predicted_priority': task_schedule.priority_score,
                    'score': task_schedule.priority_score,
                    'has_feedback': task.has_feedback
                })
            else:
                # Add unscheduled task with default priority
                daily_schedule.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'importance': task.importance,
                    'urgency': task.urgency,
                    'start_time': task.due_date,
                    'end_time': task.end_time,
                    'predicted_priority': (task.importance + task.urgency) / 2,
                    'score': (task.importance + task.urgency) / 2,
                    'has_feedback': task.has_feedback
                })

        # Sort by priority
        daily_schedule.sort(key=lambda x: x['predicted_priority'], reverse=True)

        context = {
            'daily_schedule': daily_schedule,
            'current_time': current_datetime
        }

        return render(request, 'schedule_and_feedback.html', context)

    except Exception as e:
        logger.error(f"Error in scheduling tasks: {str(e)}", exc_info=True)
        messages.error(request, f"Error generating schedule: {str(e)}")
        return render(request, 'schedule_and_feedback.html', {'daily_schedule': [], 'error': str(e)})

@login_required
def submit_task_feedback(request, task_id):
    if request.method == 'POST':
        task = Task.objects.get(id=task_id, user=request.user)
        
        if task.has_feedback:
            messages.warning(request, 'Feedback already submitted for this task.')
            return redirect('schedule')
            
        try:
            with transaction.atomic():
                # Create feedback
                feedback = TaskFeedback.objects.create(
                    task=task,
                    user=request.user,
                    rating=request.POST.get('rating'),
                    completed_on_time=request.POST.get('completed_on_time') == 'true'
                )
                
                # Update DQN model with feedback
                scheduler = DQNTaskScheduler()
                scheduler.update_model(feedback)
                
                # Mark task as having feedback
                task.has_feedback = True
                task.save()
                
            messages.success(request, 'Thank you for your feedback!')
            
        except Exception as e:
            messages.error(request, f'Error submitting feedback: {str(e)}')
            
    return redirect('schedule')

@login_required
def task_prioritization_view(request):
    tasks = Task.objects.filter(user=request.user)

    if request.method == 'POST':
        morning_energy = int(request.POST.get('morning_energy', 5))
        afternoon_energy = int(request.POST.get('afternoon_energy', 5))
        evening_energy = int(request.POST.get('evening_energy', 5))

        user_feedback, created = UserFeedback.objects.get_or_create(user=request.user)
        user_feedback.morning_energy = morning_energy
        user_feedback.afternoon_energy = afternoon_energy
        user_feedback.evening_energy = evening_energy
        user_feedback.save()

    try:
        user_feedback = UserFeedback.objects.get(user=request.user)
    except UserFeedback.DoesNotExist:
        user_feedback = None

    energy_levels = {
        'morning': user_feedback.morning_energy if user_feedback else 5,
        'afternoon': user_feedback.afternoon_energy if user_feedback else 5,
        'evening': user_feedback.evening_energy if user_feedback else 5,
    }

    prioritized_tasks = rule_based_prioritization(tasks, energy_levels)

    return render(request, 'task_prioritization.html', {
        'prioritized_tasks': prioritized_tasks,
        'energy_levels': energy_levels,
    })


def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return redirect('signup')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already in use.')
            return redirect('signup')

        user = User.objects.create_user(username=username, email=email, password=password)

        user.save()
        login(request, user)
        messages.success(request, 'Account created successfully!')
        return redirect('index')

    return render(request, 'signup.html')


def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, "Invalid username or password")
            return render(request, 'login.html')
    else:
        return render(request, 'login.html')


def feedback_thank_you(request):
    return render(request, 'feedback_thank_you.html')



######################################

from django.db.models import Count, Avg,Q
from django.db.models import Case, When, Value, FloatField
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.db.models import F, ExpressionWrapper, DecimalField
from .models import Task, TaskFeedback
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
import plotly.offline as pyo

@login_required
def task_analytics(request):
    # Get IST timezone and current date
    ist_timezone = pytz.timezone('Asia/Kolkata')
    current_date = timezone.now().astimezone(ist_timezone).date()

    # Get all tasks for the user (not just today)
    all_tasks = Task.objects.filter(
        user=request.user,
        due_date__date=current_date,
        )
    
    # Analyze task completions using TaskFeedback
    task_completions = []
    completed_tasks = 0
    total_tasks = all_tasks.count()

    for task in all_tasks:
        # Check task feedback
        task_feedback = TaskFeedback.objects.filter(task=task).first()
        
        is_completed = False
        if task_feedback:
            is_completed = task_feedback.completed_on_time
            completed_tasks += 1 if is_completed else 0

        task_completions.append({
            'task_title': task.title,
            'is_completed': is_completed,
            'importance': task.importance,
            'urgency': task.urgency,
            'due_date': task.due_date
        })

    # Calculate completion rate
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Monthly Performance Analysis
    monthly_performance = analyze_monthly_performance(request.user)

    # Aggregate task insights
    insights = generate_comprehensive_insights(task_completions)

    # Prepare visualizations
    completion_chart_data = prepare_comprehensive_completion_chart(task_completions)
    task_type_distribution = prepare_task_type_distribution(task_completions)

    context = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'completion_rate': round(completion_rate, 2),
        'task_completions': task_completions,
        'insights': insights,
        'completion_chart': completion_chart_data,
        'monthly_performance': monthly_performance,
        'task_type_distribution': task_type_distribution,
        'current_date': current_date
    }

    return render(request, 'task_analytics.html', context)

def analyze_monthly_performance(user):
    """
    Analyze task performance by month
    """
    # Group tasks by month and calculate completion rates
    monthly_tasks = Task.objects.filter(user=user).annotate(
        month=TruncMonth('due_date')
    ).values('month').annotate(
        total_tasks=Count('id'),
        completed_tasks=Count(
            Case(
                When(taskfeedback__completed_on_time=True, then=Value(1)),
                output_field=FloatField()
            )
        )
    ).order_by('month')

    # Calculate monthly completion rates
    for month in monthly_tasks:
        month['completion_rate'] = (month['completed_tasks'] / month['total_tasks'] * 100) if month['total_tasks'] > 0 else 0

    return list(monthly_tasks)

def generate_comprehensive_insights(task_completions):
    """
    Generate comprehensive insights across all tasks
    """
    insights = []

    # Overall Completion Analysis
    total_tasks = len(task_completions)
    completed_tasks = sum(1 for task in task_completions if task['is_completed'])
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Completion Rate Insights
    if completion_rate < 30:
        insights.append("Your overall task completion rate is low. Consider improving your task management strategies.")
    elif completion_rate < 60:
        insights.append("You're making progress, but there's significant room for improvement in task completion.")
    elif completion_rate < 80:
        insights.append("Good job! You're completing most of your tasks. Keep refining your approach.")
    else:
        insights.append("Excellent performance! You're consistently completing your tasks.")

    # Importance and Urgency Insights
    high_importance_tasks = [t for t in task_completions if t['importance'] >= 4]
    high_urgency_tasks = [t for t in task_completions if t['urgency'] >= 4]
    
    uncompleted_important_tasks = [t for t in high_importance_tasks if not t['is_completed']]
    uncompleted_urgent_tasks = [t for t in high_urgency_tasks if not t['is_completed']]

    if uncompleted_important_tasks:
        insights.append(f"{len(uncompleted_important_tasks)} high-importance tasks were not completed. Prioritize these in future planning.")

    if uncompleted_urgent_tasks:
        insights.append(f"{len(uncompleted_urgent_tasks)} urgent tasks were left unfinished. Immediate attention is needed.")

    return insights

def prepare_comprehensive_completion_chart(task_completions):
    """
    Prepare comprehensive completion chart
    """
    import plotly.graph_objs as go
    import plotly.offline as pyo

    # Prepare data for monthly and overall completion
    completed = sum(1 for task in task_completions if task['is_completed'])
    not_completed = len(task_completions) - completed

    # Pie chart for overall completion
    labels = ['Completed', 'Not Completed']
    values = [completed, not_completed]
    colors = ['#2ecc71', '#e74c3c']

    fig = go.Figure(data=[go.Pie(
        labels=labels, 
        values=values, 
        marker_colors=colors,
        hole=0.3  # Create a donut chart
    )])

    fig.update_layout(
        title='Overall Task Completion',
        height=400,
        width=400
    )

    return pyo.plot(fig, output_type='div', include_plotlyjs=True)

def prepare_task_type_distribution(task_completions):
    """
    Prepare task distribution by importance and urgency
    """
    import plotly.graph_objs as go
    import plotly.offline as pyo

    # Categorize tasks by importance and urgency
    importance_distribution = {
        'Low (1-2)': sum(1 for t in task_completions if t['importance'] <= 2),
        'Medium (3-4)': sum(1 for t in task_completions if 3 <= t['importance'] <= 4),
        'High (5)': sum(1 for t in task_completions if t['importance'] == 5)
    }

    urgency_distribution = {
        'Low (1-2)': sum(1 for t in task_completions if t['urgency'] <= 2),
        'Medium (3-4)': sum(1 for t in task_completions if 3 <= t['urgency'] <= 4),
        'High (5)': sum(1 for t in task_completions if t['urgency'] == 5)
    }

    # Create bar chart
    fig = go.Figure(data=[
        go.Bar(name='Importance', x=list(importance_distribution.keys()), y=list(importance_distribution.values())),
        go.Bar(name='Urgency', x=list(urgency_distribution.keys()), y=list(urgency_distribution.values()))
    ])

    fig.update_layout(
        title='Task Distribution by Importance and Urgency',
        xaxis_title='Category',
        yaxis_title='Number of Tasks',
        barmode='group',
        height=400,
        width=600
    )

    return pyo.plot(fig, output_type='div', include_plotlyjs=True)


