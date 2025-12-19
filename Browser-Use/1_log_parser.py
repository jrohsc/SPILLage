import os
import glob
import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ControllerEvent:
    timestamp: str
    event_type: str
    details: str

@dataclass
class BrowserSessionEvent:
    timestamp: str
    session_id: str
    event_type: str
    details: str

@dataclass
class DebugEvent:
    timestamp: str
    debug_type: str
    details: str

@dataclass
class Step:
    step_number: int
    thinking: str
    action: str
    result: str
    evaluation: str
    memory: str
    next_goal: str
    execution_time: str
    controller_events: List[ControllerEvent]
    browser_events: List[BrowserSessionEvent]
    debug_events: List[DebugEvent]

def parse_browser_log(log_content: str) -> tuple[List[Step], dict]:
    """Parse browser-use log into structured steps and extract metadata."""
    
    # Extract task information and timing from the header
    task_info = extract_task_info(log_content)

    # Extract task completion status
    completion_status = extract_completion_status(log_content)
    task_info.update(completion_status)
    
    steps = []
    
    # Split by step boundaries - look for the step evaluation pattern
    step_pattern = r'📍 Step (\d+): Evaluating page.*?on: (.*?)\n'
    step_matches = list(re.finditer(step_pattern, log_content))
    
    for i, match in enumerate(step_matches):
        step_num = int(match.group(1))
        
        # Get content from this step to next step (or end)
        start_pos = match.start()
        end_pos = step_matches[i + 1].start() if i + 1 < len(step_matches) else len(log_content)
        step_content = log_content[start_pos:end_pos]
        
        # Extract components
        thinking = extract_thinking(step_content)
        action = extract_action(step_content)
        result = extract_result(step_content)
        evaluation = extract_evaluation(step_content)
        memory = extract_memory(step_content)
        next_goal = extract_next_goal(step_content)
        execution_time = extract_execution_time(step_content)
        
        # Extract events
        controller_events = extract_controller_events(step_content)
        browser_events = extract_browser_events(step_content)
        debug_events = extract_debug_events(step_content)
        
        step = Step(
            step_number=step_num,
            thinking=thinking,
            action=action,
            result=result,
            evaluation=evaluation,
            memory=memory,
            next_goal=next_goal,
            execution_time=execution_time,
            controller_events=controller_events,
            browser_events=browser_events,
            debug_events=debug_events
        )
        
        steps.append(step)
    
    return steps, task_info

def extract_task_info(log_content: str) -> dict:
    """Extract task information and timing from log header."""
    task_info = {
        'task': 'Not found',
        'test_id': 'Not found',
        'start_time': 'Not found',
        'end_time': 'Not found',
        'total_duration': 'Not found'
    }
    
    # Extract task description
    task_match = re.search(r'📝 Task: (.*?)(?=\n)', log_content)
    if task_match:
        task_info['task'] = task_match.group(1).strip()
    
    # Extract test ID
    test_id_match = re.search(r'🏷️\s+Test ID: (.*?)(?=\n)', log_content)
    if test_id_match:
        task_info['test_id'] = test_id_match.group(1).strip()
    
    # Extract start time
    start_match = re.search(r'⏰ Start time: (.*?)(?=\n)', log_content)
    if start_match:
        task_info['start_time'] = start_match.group(1).strip()
    
    # Extract end time
    end_match = re.search(r'⏰ End time: (.*?)(?=\n)', log_content)
    if end_match:
        task_info['end_time'] = end_match.group(1).strip()
    
    # Calculate total duration if both times are available
    if task_info['start_time'] != 'Not found' and task_info['end_time'] != 'Not found':
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(task_info['start_time'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(task_info['end_time'].replace('Z', '+00:00'))
            duration = end_dt - start_dt
            
            # Format duration nicely
            total_seconds = int(duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            
            if hours > 0:
                task_info['total_duration'] = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                task_info['total_duration'] = f"{minutes}m {seconds}s"
            else:
                task_info['total_duration'] = f"{seconds}s"
        except Exception:
            task_info['total_duration'] = 'Could not calculate'
    
    return task_info

def extract_thinking(content: str) -> str:
    """Extract thinking section."""
    match = re.search(r'💡 Thinking:\n(.*?)(?=\n.*?👍|❔|⚠️)', content, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_action(content: str) -> str:
    """Extract action performed."""
    # Match everything after the 🦾 and ANSI codes, until the end of the action
    match = re.search(
        r'🦾.*?\[(.*?)\]\s*(.*)',  # capture [ACTION ...] and the rest
        content
    )
    if match:
        # group(1) = "ACTION 1/2"
        # group(2) = "input_text(input_text: index: 11, text: ..., clear_existing: True)"
        return f"[{match.group(1)}] {match.group(2).strip()}"
    return ""

def extract_result(content: str) -> str:
    """Extract action result."""
    match = re.search(r'☑️ Executed action.*?: \[(.*?)\] in (.*?)s', content)
    return f"{match.group(1)} (took {match.group(2)}s)" if match else ""

def extract_evaluation(content: str) -> str:
    """Extract evaluation."""
    match = re.search(r'(👍|❔|⚠️) Eval: (.*?)(?=\n.*?🧠)', content, re.DOTALL)
    return match.group(2).strip() if match else ""

def extract_memory(content: str) -> str:
    """Extract memory update."""
    match = re.search(r'🧠 Memory: (.*?)(?=\n.*?🎯)', content, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_next_goal(content: str) -> str:
    """Extract next goal."""
    match = re.search(r'🎯 Next goal: (.*?)(?=\n\nINFO|\nINFO)', content, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_execution_time(content: str) -> str:
    """Extract step execution time."""
    match = re.search(r'📍 Step \d+: Ran \d+ actions in (.*?): ✅', content)
    return match.group(1).strip() if match else ""

def extract_controller_events(content: str) -> List[ControllerEvent]:
    """Extract controller.service events."""
    events = []
    pattern = r'INFO\s+\[browser_use\.controller\.service\]\s+(.*?)$'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        details = match.group(1)
        timestamp = ""  # Extract from line if needed
        
        # Determine event type based on icon/content
        if '🔗' in details or 'Navigated to' in details:
            event_type = 'navigation'
        elif '🖱️' in details or 'Clicked' in details:
            event_type = 'click'
        elif '🔍' in details or 'Scrolled' in details:
            event_type = 'scroll'
        elif '📄' in details or 'Extracted' in details:
            event_type = 'extraction'
        elif '🔄' in details or 'Switched' in details:
            event_type = 'tab_switch'
        else:
            event_type = 'other'
        
        events.append(ControllerEvent(
            timestamp=timestamp,
            event_type=event_type,
            details=details.strip()
        ))
    
    return events

def extract_browser_events(content: str) -> List[BrowserSessionEvent]:
    """Extract BrowserSession events."""
    events = []
    pattern = r'INFO\s+\[browser_use\.BrowserSession.*?\]\s+(.*?)$'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        details = match.group(1)
        timestamp = ""  # Extract from line if needed
        
        # Extract session ID if present
        session_match = re.search(r'BrowserSession🆂\s*([a-zA-Z0-9]+)', details)
        session_id = session_match.group(1) if session_match else "unknown"
        
        # Determine event type
        if 'NavigateToUrl' in details:
            event_type = 'navigation'
        elif 'TabCreated' in details:
            event_type = 'tab_creation'
        elif 'CDP' in details:
            event_type = 'cdp_connection'
        elif 'dialog handler' in details:
            event_type = 'dialog_setup'
        elif 'PopupsWatchdog' in details:
            event_type = 'popup_watchdog'
        elif 'permissions' in details:
            event_type = 'permissions'
        else:
            event_type = 'other'
        
        events.append(BrowserSessionEvent(
            timestamp=timestamp,
            session_id=session_id,
            event_type=event_type,
            details=details.strip()
        ))
    
    return events

def extract_debug_events(content: str) -> List[DebugEvent]:
    """Extract DEBUG events."""
    events = []
    pattern = r'INFO\s+\[browser_use\.BrowserSession.*?\]\s+🔍 DEBUG:\s+(.*?)$'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        details = match.group(1)
        timestamp = ""  # Extract from line if needed
        
        # Determine debug type
        if 'Capturing DOM snapshot' in details:
            debug_type = 'dom_capture'
        elif 'Iframe' in details and 'scroll position' in details:
            debug_type = 'iframe_scroll'
        elif 'Snapshot contains' in details:
            debug_type = 'snapshot_info'
        elif 'Document' in details and 'has' in details and 'nodes' in details:
            debug_type = 'document_nodes'
        elif 'HTML frame scroll' in details:
            debug_type = 'frame_scroll'
        else:
            debug_type = 'other'
        
        events.append(DebugEvent(
            timestamp=timestamp,
            debug_type=debug_type,
            details=details.strip()
        ))
    
    return events

def format_steps(steps: List[Step]) -> str:
    """Format steps into readable output."""
    output = []
    
    for step in steps:
        output.append(f"=" * 80)
        output.append(f"STEP {step.step_number}")
        output.append(f"=" * 80)
        
        if step.thinking:
            output.append(f"\n💡 THINKING:")
            output.append(f"{step.thinking}")
        
        if step.action:
            output.append(f"\n🦾 ACTION:")
            output.append(f"{step.action}")
        
        if step.result:
            output.append(f"\n☑️ RESULT:")
            output.append(f"{step.result}")
        
        if step.evaluation:
            output.append(f"\n📊 EVALUATION:")
            output.append(f"{step.evaluation}")
        
        if step.memory:
            output.append(f"\n🧠 MEMORY UPDATE:")
            output.append(f"{step.memory}")
        
        if step.next_goal:
            output.append(f"\n🎯 NEXT GOAL:")
            output.append(f"{step.next_goal}")
        
        if step.execution_time:
            output.append(f"\n⏱️ EXECUTION TIME:")
            output.append(f"{step.execution_time}")
        
        # Controller Events
        if step.controller_events:
            output.append(f"\n🎮 CONTROLLER EVENTS:")
            for event in step.controller_events:
                output.append(f"  [{event.timestamp}] {event.event_type.upper()}: {event.details}")
        
        # Browser Session Events
        if step.browser_events:
            output.append(f"\n🌐 BROWSER SESSION EVENTS:")
            for event in step.browser_events:
                output.append(f"  [{event.timestamp}] Session {event.session_id} - {event.event_type.upper()}: {event.details}")
        
        # Debug Events
        if step.debug_events:
            output.append(f"\n🔍 DEBUG EVENTS:")
            for event in step.debug_events:
                output.append(f"  [{event.timestamp}] {event.debug_type.upper()}: {event.details}")
        
        output.append("")  # Empty line between steps
    
    return "\n".join(output)

def extract_completion_status(log_content: str) -> dict:
    """Extract task completion status from log."""
    status_info = {
        'task_completed': False,
        'completion_message': 'Not found',
        'completion_details': '',
    }
    
    # Check for failure first - prioritize this over success messages
    failure_match = re.search(r'❌ Task completed without success', log_content)
    if failure_match:
        status_info['task_completed'] = False
        status_info['completion_message'] = '❌ Task failed'
        
        # Try to extract more details if available
        result_match = re.search(r'📊 Result: (.*?)(?=\n⏰|$)', log_content, re.DOTALL)
        if result_match:
            status_info['completion_details'] = result_match.group(1).strip()
        
        return status_info
    
    # Check for successful completion
    success_match = re.search(r'✅ Task completed successfully!', log_content)
    if success_match:
        status_info['task_completed'] = True
        status_info['completion_message'] = '✅ Task completed successfully!'
        
        # Try to extract more details if available
        result_match = re.search(r'📊 Result: (.*?)(?=\n⏰|$)', log_content, re.DOTALL)
        if result_match:
            status_info['completion_details'] = result_match.group(1).strip()
        
        return status_info
    
    # Check for other error indicators
    error_match = re.search(r'❌ Stopping due to (.*?)(?=\n|$)', log_content)
    if error_match:
        status_info['task_completed'] = False
        status_info['completion_message'] = f'❌ Stopped due to: {error_match.group(1).strip()}'
        
        # Try to extract more details
        result_match = re.search(r'📊 Result: (.*?)(?=\n⏰|$)', log_content, re.DOTALL)
        if result_match:
            status_info['completion_details'] = result_match.group(1).strip()
        
        return status_info
    
    return status_info

def format_task_header(task_info: dict) -> str:
    """Format task information header."""
    
    # Add completion status to header
    completion_status = "✅ COMPLETED SUCCESSFULLY" if task_info.get('task_completed', False) else "❌ FAILED"
    completion_message = task_info.get('completion_message', 'Not found')
    
    header = [
        "🚀 BROWSER-USE AGENT TASK",
        "=" * 80,
        f"📝 Task: {task_info['task']}",
        f"🏷️ Test ID: {task_info['test_id']}",
        f"⏰ Start Time: {task_info['start_time']}",
        f"⏰ End Time: {task_info['end_time']}",
        f"⏱️ Total Duration: {task_info['total_duration']}",
        f"📊 Status: {completion_status}",
        f"📄 Details: {completion_message}",
        "=" * 80,
        ""
    ]
    return "\n".join(header)

def format_summary(steps: List[Step], task_info: dict = None) -> str:
    """Generate a summary of the parsed log."""
    total_steps = len(steps)
    total_controller_events = sum(len(s.controller_events) for s in steps)
    total_browser_events = sum(len(s.browser_events) for s in steps)
    total_debug_events = sum(len(s.debug_events) for s in steps)
    
    # Count event types
    controller_types = {}
    browser_types = {}
    debug_types = {}
    
    for step in steps:
        for event in step.controller_events:
            controller_types[event.event_type] = controller_types.get(event.event_type, 0) + 1
        for event in step.browser_events:
            browser_types[event.event_type] = browser_types.get(event.event_type, 0) + 1
        for event in step.debug_events:
            debug_types[event.debug_type] = debug_types.get(event.debug_type, 0) + 1
    
    summary = [
        "📊 LOG PARSING SUMMARY",
        "=" * 50,
        f"Total Steps: {total_steps}",
        f"Controller Events: {total_controller_events}",
        f"Browser Events: {total_browser_events}",
        f"Debug Events: {total_debug_events}",
        "",
        "Controller Event Types:",
    ]
    
    for event_type, count in sorted(controller_types.items()):
        summary.append(f"  - {event_type}: {count}")
    
    summary.append("\nBrowser Event Types:")
    for event_type, count in sorted(browser_types.items()):
        summary.append(f"  - {event_type}: {count}")
    
    summary.append("\nDebug Event Types:")
    for event_type, count in sorted(debug_types.items()):
        summary.append(f"  - {event_type}: {count}")
    
    return "\n".join(summary)

# Example usage
if __name__ == "__main__":

    models = ["gpt-4o", "o3", "o4-mini", "gemini-2.5-flash"]
    categories = ["less_sensitive"]

    for model in models:
        print(model)
        for category in categories:
            # results_output/less_sensitive
            root_folder = os.path.join('results_output', category)

            # results_output/less_sensitive/o3
            main_folder = os.path.join(root_folder, model)

            # results_output/less_sensitive/o3_parsed
            output_folder = os.path.join(root_folder, f'{model}_parsed')
            
            # Find all .log files recursively
            log_pattern = f"{main_folder}/**/*.log"
            log_files = glob.glob(log_pattern, recursive=True)

            print(log_files)
            
            print(f"Found {len(log_files)} log files to process...")
            
            for log_file_path in log_files:
                try:
                    print(f"Processing: {log_file_path}")
                    
                    # Create the corresponding output path
                    # Replace main_folder with output_folder in the path
                    relative_path = os.path.relpath(log_file_path, main_folder)
                    
                    # Change extension from .log to _parsed.log
                    name_without_ext = os.path.splitext(relative_path)[0]
                    output_relative_path = f"{name_without_ext}_parsed.log"
                    
                    output_file_path = os.path.join(output_folder, output_relative_path)
                    
                    # Create output directory if it doesn't exist
                    output_dir = os.path.dirname(output_file_path)
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # Read the log file
                    with open(log_file_path, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    
                    # Parse steps and extract task info
                    steps, task_info = parse_browser_log(log_content)
                    
                    if not steps:
                        print(f"  Warning: No steps found in {log_file_path}")
                        continue
                    
                    # Generate all formatted content
                    task_header = format_task_header(task_info)
                    summary = format_summary(steps, task_info)
                    formatted_output = format_steps(steps)
                    
                    # Combine everything with proper separators
                    full_content = (
                        task_header + "\n" +
                        summary + "\n\n" + 
                        "=" * 80 + "\n\n" + 
                        formatted_output
                    )
                    
                    # Save to output file
                    with open(output_file_path, 'w', encoding='utf-8') as f:
                        f.write(full_content)
                    
                    print(f"  ✅ Parsed {len(steps)} steps -> {output_file_path}")
                    print(f"     📝 Task: {task_info['task'][:60]}{'...' if len(task_info['task']) > 60 else ''}")
                    print(f"     ⏱️ Duration: {task_info['total_duration']}")
                    
                except Exception as e:
                    print(f"  ❌ Error processing {log_file_path}: {str(e)}")
                    continue
            
            print(f"\n🎉 Batch processing complete! Check the '{output_folder}' directory for results.")