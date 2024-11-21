import numpy as np
from tensorflow.keras.models import Sequential, load_model, Model
from tensorflow.keras.layers import Dense, Input
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.losses import MeanSquaredError
import random
import os
from django.conf import settings

class DQNTaskPrioritizer:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = []
        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.01
        self.learning_rate = 0.001
        
        # Create models directory if it doesn't exist
        self.model_dir = os.path.join(settings.BASE_DIR, 'models')
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = os.path.join(self.model_dir, 'dqn_model.keras')
        
        # Load existing model or create new one
        if os.path.exists(self.model_path):
            self.model = self._load_model()
        else:
            self.model = self._build_model()

    def _build_model(self):
        # Create model using functional API
        inputs = Input(shape=(self.state_size,))
        x = Dense(64, activation='relu')(inputs)
        x = Dense(64, activation='relu')(x)
        outputs = Dense(self.action_size, activation='linear')(x)
        
        model = Model(inputs=inputs, outputs=outputs)
        model.compile(
            optimizer=Adam(learning_rate=self.learning_rate), 
            loss=MeanSquaredError()
        )
        return model

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)
        return np.argmax(self.model.predict(state.reshape(1, -1), verbose=0)[0])

    def replay(self, batch_size=32):
        if len(self.memory) < batch_size:
            return
            
        batch = random.sample(self.memory, batch_size)
        for state, action, reward, next_state, done in batch:
            next_state = np.array(next_state)
            state = np.array(state)
            target = reward if done else reward + self.gamma * np.amax(self.model.predict(next_state.reshape(1, -1), verbose=0)[0])
            target_f = self.model.predict(state.reshape(1, -1), verbose=0)
            target_f[0][action] = target
            self.model.fit(state.reshape(1, -1), target_f, epochs=1, verbose=0)

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            
        # Save model after training
        self._save_model()

    def _save_model(self):
        """Internal method to save the model to disk"""
        try:
            self.model.save(self.model_path, save_format='keras')
        except Exception as e:
            print(f"Error saving model: {e}")

    def _load_model(self):
        """Internal method to load the model from disk"""
        try:
            return load_model(self.model_path)
        except Exception as e:
            print(f"Error loading model: {e}")
            return self._build_model()
            
    def save(self, filepath):
        """Public method to save the model to a specific filepath"""
        try:
            # Ensure filepath ends with .keras
            if not filepath.endswith('.keras'):
                filepath = filepath.rsplit('.', 1)[0] + '.keras'
            self.model.save(filepath, save_format='keras')
            print(f"Model successfully saved to {filepath}")
        except Exception as e:
            print(f"Error saving model to {filepath}: {e}")
            
    def load(self, filepath):
        """Public method to load the model from a specific filepath"""
        try:
            self.model = load_model(filepath)
            print(f"Model successfully loaded from {filepath}")
        except Exception as e:
            print(f"Error loading model from {filepath}: {e}")
            print("Initializing new model instead")
            self.model = self._build_model()