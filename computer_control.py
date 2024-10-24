import asyncio
import base64
import os
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict, List, Dict, cast
from datetime import datetime
import anthropic
from anthropic.types import MessageParam
import pyautogui
from io import BytesIO
import win32gui
import win32con
import keyboard
from PIL import Image
import platform

print("""NOTE: Please be very careful running this script!! this runs locally on your machine(NO SANDBOX) There is an artificial delay in script before each action so you can review them(default 5 seconds). KEEP A WATCHFUL EYE ON IT! AND STOP THE SCRIPT DURING WAIT TIME IF IT TRIES TO DO SOMETHING YOU DONT WANT. BY RUNNING THIS SCRIPT YOU ASSUME THE RESPONSIBILITY OF THE OUTCOMES""")

# This is to allow the user to confirm or abort actions with some time to think
WAIT_BEFORE_ACTION: Optional[float] = None # Set to None to disable waiting

# Configure PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

# Actions defined in the official repository
Action = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]

class Resolution(TypedDict):
    width: int
    height: int

MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),  # 4:3
    "WXGA": Resolution(width=1280, height=800),  # 16:10
    "FWXGA": Resolution(width=1366, height=768),  # ~16:9
}

@dataclass(frozen=True)
class ToolResult:
    """Base result type for all tools"""
    output: Optional[str] = None
    error: Optional[str] = None
    base64_image: Optional[str] = None
    system: Optional[str] = None

    def __bool__(self):
        return any(getattr(self, field.name) for field in fields(self))
    
    def replace(self, **kwargs):
        return replace(self, **kwargs)

class ToolError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class ComputerTool:
    """Windows-compatible computer interaction tool"""
    name = "computer"
    api_type = "computer_20241022"
    _screenshot_delay = 1.0
    
    def __init__(self):
        self.screen_width, self.screen_height = pyautogui.size()
        target_res = MAX_SCALING_TARGETS["XGA"]
        self.width = target_res["width"]
        self.height = target_res["height"]
        
    def to_params(self):
        return {
            "type": self.api_type,
            "name": self.name,
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": 1,
        }

    async def __call__(self, action: Action, text: Optional[str] = None,
                       coordinate: Optional[tuple[int, int] | List[int]] = None, **kwargs):
        try:
            # Get action description
            action_desc = self._get_action_description(action, text, coordinate)
            print(f"\nPending Action: {action_desc}")
            
            # Wait if WAIT_BEFORE_ACTION is set
            if WAIT_BEFORE_ACTION is not None:
                print(f"Waiting {WAIT_BEFORE_ACTION} seconds before executing...")
                await asyncio.sleep(WAIT_BEFORE_ACTION)

            # Convert list coordinates to tuple if necessary
            if isinstance(coordinate, list) and len(coordinate) == 2:
                coordinate = tuple(coordinate)

            # Scale coordinates if provided
            if coordinate:
                if not isinstance(coordinate, tuple) or len(coordinate) != 2:
                    raise ToolError(f"Invalid coordinate format: {coordinate}")
                try:
                    x, y = int(coordinate[0]), int(coordinate[1])
                    x, y = self._scale_coordinates(x, y)
                    coordinate = (x, y)
                except (ValueError, TypeError):
                    raise ToolError(f"Invalid coordinate values: {coordinate}")

            # Execute action
            if action in ("mouse_move", "left_click_drag"):
                if not coordinate:
                    raise ToolError(f"coordinate required for {action}")
                x, y = coordinate
                print(f"Moving to scaled coordinates: ({x}, {y})")
                if action == "mouse_move":
                    pyautogui.moveTo(x, y)
                else:
                    pyautogui.dragTo(x, y, button='left')
                
            elif action in ("key", "type"):
                if not text:
                    raise ToolError(f"text required for {action}")
                print(f"Sending text: {text}")
                if action == "key":
                    keyboard.send(text)
                else:
                    pyautogui.write(text, interval=0.01)
                
            elif action in ("left_click", "right_click", "middle_click", "double_click"):
                print(f"Performing {action}")
                click_map = {
                    "left_click": lambda: pyautogui.click(button='left'),
                    "right_click": lambda: pyautogui.click(button='right'),
                    "middle_click": lambda: pyautogui.click(button='middle'),
                    "double_click": lambda: pyautogui.doubleClick()
                }
                click_map[action]()
                
            elif action == "cursor_position":
                x, y = pyautogui.position()
                scaled_x, scaled_y = self._inverse_scale_coordinates(x, y)
                return ToolResult(output=f"X={scaled_x},Y={scaled_y}")
            
            elif action == "screenshot":
                return await self._take_screenshot()

            # Always take a screenshot after any action (except cursor_position)
            if action != "cursor_position":
                await asyncio.sleep(self._screenshot_delay)
                result = await self._take_screenshot()
                if result.error:
                    raise ToolError(result.error)
                return result
            
        except Exception as e:
            error_msg = f"Action failed: {str(e)}"
            print(f"\nError: {error_msg}")
            return ToolResult(error=error_msg)

    def _scale_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """Scale coordinates from XGA to actual screen resolution"""
        scaled_x = int(x * (self.screen_width / self.width))
        scaled_y = int(y * (self.screen_height / self.height))
        return scaled_x, scaled_y

    def _inverse_scale_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """Scale coordinates from actual screen resolution to XGA"""
        scaled_x = int(x * (self.width / self.screen_width))
        scaled_y = int(y * (self.height / self.screen_height))
        return scaled_x, scaled_y

    async def _take_screenshot(self) -> ToolResult:
        try:
            screenshot = pyautogui.screenshot()
            if screenshot.size != (self.width, self.height):
                screenshot = screenshot.resize(
                    (self.width, self.height), 
                    Image.Resampling.LANCZOS
                )
            
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG", optimize=True)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return ToolResult(base64_image=img_str)
        except Exception as e:
            return ToolResult(error=f"Screenshot failed: {str(e)}")

    def _get_action_description(self, action: Action, text: Optional[str],
                              coordinate: Optional[tuple[int, int] | List[int]]) -> str:
        if action in ("mouse_move", "left_click_drag"):
            return f"{action.replace('_', ' ').title()} to coordinates: {coordinate}"
        elif action in ("key", "type"):
            return f"{action.title()} text: '{text}'"
        elif action in ("left_click", "right_click", "middle_click", "double_click"):
            return f"Perform {action.replace('_', ' ')}"
        elif action == "screenshot":
            return "Take a screenshot"
        elif action == "cursor_position":
            return "Get current cursor position"
        return f"Unknown action: {action}"

# Global settings
DEBUG = False  # Set to True for detailed error messages

if __name__ == "__main__":
    print("This is a support module. Please run task_recorder.py instead.")
