import asyncio
import json
from dataclasses import dataclass
from typing import List, Dict, Any
from pathlib import Path
import os
import keyboard
import time
from threading import Thread
import pyautogui
from pynput import mouse as pynput_mouse
from pynput import keyboard as pynput_keyboard
from computer_control import ComputerTool, WAIT_BEFORE_ACTION

# Set your API key
os.environ["ANTHROPIC_API_KEY"] = "api-key"  # Replace with your actual key

# Create tasks directory
tasks_dir = Path("tasks")
tasks_dir.mkdir(exist_ok=True)

@dataclass
class TaskAction:
    timestamp: float
    action_type: str
    x: int = None
    y: int = None
    button: str = None
    key: str = None
    text: str = None

class TaskRecorder:
    def __init__(self, base_dir: str = "tasks"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.computer_tool = ComputerTool()
        self.recording = False
        self.actions: List[TaskAction] = []
        self.start_time = 0
        
        # Initialize input listeners
        self.mouse_listener = pynput_mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click
        )
        self.keyboard_listener = pynput_keyboard.Listener(
            on_press=self._on_key_press,
            on_type=self._on_type
        )
        
        # Buffer for building text strings
        self.text_buffer = []
        self.last_key_time = 0
        self.TEXT_TIMEOUT = 1.0  # seconds
        
    def _on_mouse_move(self, x, y):
        if self.recording:
            # Scale coordinates from actual screen to XGA
            scaled_x, scaled_y = self.computer_tool._inverse_scale_coordinates(x, y)
            # Only record significant movements (reduce noise)
            if not self.actions or \
               (self.actions[-1].action_type != 'mouse_move') or \
               (abs(self.actions[-1].x - scaled_x) > 10) or \
               (abs(self.actions[-1].y - scaled_y) > 10):
                self.actions.append(TaskAction(
                    timestamp=time.time() - self.start_time,
                    action_type='mouse_move',
                    x=scaled_x,
                    y=scaled_y
                ))
    
    def _on_mouse_click(self, x, y, button, pressed):
        if self.recording and pressed:
            scaled_x, scaled_y = self.computer_tool._inverse_scale_coordinates(x, y)
            button_name = 'left_click' if button == pynput_mouse.Button.left else 'right_click'
            self.actions.append(TaskAction(
                timestamp=time.time() - self.start_time,
                action_type=button_name,
                x=scaled_x,
                y=scaled_y
            ))
    
    def _on_key_press(self, key):
        if not self.recording:
            return
            
        current_time = time.time()
        
        # Handle special keys
        try:
            if hasattr(key, 'char'):
                # Regular character key
                if current_time - self.last_key_time > self.TEXT_TIMEOUT:
                    # Start new text buffer if timeout exceeded
                    self._flush_text_buffer()
                self.text_buffer.append(key.char)
            else:
                # Special key
                self._flush_text_buffer()  # Flush any pending text
                key_name = str(key).replace('Key.', '')
                self.actions.append(TaskAction(
                    timestamp=current_time - self.start_time,
                    action_type='key',
                    key=key_name
                ))
        except AttributeError:
            pass
            
        self.last_key_time = current_time
    
    def _on_type(self, char):
        if self.recording:
            current_time = time.time()
            if current_time - self.last_key_time > self.TEXT_TIMEOUT:
                self._flush_text_buffer()
            self.text_buffer.append(char)
            self.last_key_time = current_time
    
    def _flush_text_buffer(self):
        if self.text_buffer:
            text = ''.join(self.text_buffer)
            self.actions.append(TaskAction(
                timestamp=time.time() - self.start_time,
                action_type='type',
                text=text
            ))
            self.text_buffer = []
    
    def start_recording(self):
        """Start recording user actions"""
        print("\nRecording started. Press 'Esc' to stop recording...")
        self.recording = True
        self.actions = []
        self.start_time = time.time()
        self.mouse_listener.start()
        self.keyboard_listener.start()
        
        # Wait for Esc key
        keyboard.wait('esc')
        self.stop_recording()
    
    def stop_recording(self):
        """Stop recording user actions"""
        self._flush_text_buffer()  # Flush any remaining text
        self.recording = False
        self.mouse_listener.stop()
        self.keyboard_listener.stop()
        print("\nRecording stopped.")
    
    def save_task(self, name: str, description: str):
        """Save recorded actions as a task"""
        task_data = {
            "name": name,
            "description": description,
            "actions": [
                {
                    "timestamp": action.timestamp,
                    "action_type": action.action_type,
                    "x": action.x,
                    "y": action.y,
                    "button": action.button,
                    "key": action.key,
                    "text": action.text
                }
                for action in self.actions
            ]
        }
        
        file_path = self.base_dir / f"{name.lower().replace(' ', '_')}.json"
        with open(file_path, 'w') as f:
            json.dump(task_data, f, indent=2)
            print(f"\nTask saved to {file_path}")
    
    async def execute_task(self, task_name: str):
        """Execute a saved task"""
        file_path = self.base_dir / f"{task_name.lower().replace(' ', '_')}.json"
        
        try:
            with open(file_path, 'r') as f:
                task_data = json.load(f)
            
            print(f"\nExecuting task: {task_data['name']}")
            print(task_data['description'])
            
            for action in task_data['actions']:
                print(f"\nExecuting: {action['action_type']}")
                
                if WAIT_BEFORE_ACTION is not None:
                    print(f"Waiting {WAIT_BEFORE_ACTION} seconds...")
                    await asyncio.sleep(WAIT_BEFORE_ACTION)
                
                if action['action_type'] == 'mouse_move':
                    await self.computer_tool('mouse_move', coordinate=(action['x'], action['y']))
                elif action['action_type'] in ['left_click', 'right_click']:
                    await self.computer_tool(action['action_type'])
                elif action['action_type'] == 'type':
                    await self.computer_tool('type', text=action['text'])
                elif action['action_type'] == 'key':
                    await self.computer_tool('key', text=action['key'])
                
                # Take screenshot after each action
                await self.computer_tool('screenshot')
                
            print("\nTask completed successfully!")
            
        except Exception as e:
            print(f"Error executing task: {str(e)}")

async def main():
    recorder = TaskRecorder()
    
    while True:
        print("\nTask Automation System")
        print("1. Record new task")
        print("2. Execute task")
        print("3. List tasks")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            name = input("Enter task name: ").strip()
            description = input("Enter task description: ").strip()
            print("\nPress Enter to start recording...")
            input()
            recorder.start_recording()  # This will block until Esc is pressed
            recorder.save_task(name, description)
            
        elif choice == '2':
            tasks = [f.stem for f in recorder.base_dir.glob('*.json')]
            if not tasks:
                print("No tasks available")
                continue
                
            print("\nAvailable tasks:")
            for i, task in enumerate(tasks, 1):
                print(f"{i}. {task}")
                
            task_num = input("\nEnter task number: ").strip()
            try:
                task_name = tasks[int(task_num) - 1]
                await recorder.execute_task(task_name)
            except (ValueError, IndexError):
                print("Invalid task number")
                
        elif choice == '3':
            tasks = [f.stem for f in recorder.base_dir.glob('*.json')]
            if not tasks:
                print("No tasks available")
            else:
                print("\nAvailable tasks:")
                for task in tasks:
                    print(f"- {task}")
                    
        elif choice == '4':
            break
            
        else:
            print("Invalid choice")

if __name__ == "__main__":
    # Set up basic configuration
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1  # 100ms pause between actions
    
    # Run the main async loop
    asyncio.run(main())