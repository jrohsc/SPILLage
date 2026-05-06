import re
import json
from typing import Dict, List, Any
from datetime import datetime

class BrowserLogParser:
    def __init__(self):
        self.step_pattern = re.compile(r'^STEP (\d+)$')
        self.section_patterns = {
            'thinking': re.compile(r'^💡 THINKING:$'),
            'action': re.compile(r'^🦾 ACTION:$'),
            'evaluation': re.compile(r'^📊 EVALUATION:$'),
            'memory_update': re.compile(r'^🧠 MEMORY UPDATE:$'),
            'next_goal': re.compile(r'^🎯 NEXT GOAL:$'),
            'execution_time': re.compile(r'^⏱️ EXECUTION TIME:$'),
            'controller_events': re.compile(r'^🎮 CONTROLLER EVENTS:$'),
            'browser_events': re.compile(r'^🌐 BROWSER SESSION EVENTS:$'),
            'debug_events': re.compile(r'^🔍 DEBUG EVENTS:$')
        }
        
    def parse_header(self, lines: List[str]) -> Dict[str, Any]:
        """Parse the header section with task metadata"""
        header = {}
        
        for line in lines:
            if line.startswith('🚀 BROWSER-USE AGENT TASK'):
                continue
            elif line.startswith('📝 Task:'):
                header['task_description'] = line.replace('📝 Task:', '').strip()
            elif line.startswith('🏷️ Test ID:'):
                header['test_id'] = line.replace('🏷️ Test ID:', '').strip()
            elif line.startswith('⏰ Start Time:'):
                header['start_time'] = line.replace('⏰ Start Time:', '').strip()
            elif line.startswith('⏰ End Time:'):
                header['end_time'] = line.replace('⏰ End Time:', '').strip()
            elif line.startswith('⏱️ Total Duration:'):
                header['total_duration'] = line.replace('⏱️ Total Duration:', '').strip()
            elif line.startswith('📄 Details:'):
                header['completion_status'] = line.replace('📄 Details:', '').strip()
                
        return header
    
    def parse_summary(self, lines: List[str]) -> Dict[str, Any]:
        """Parse the log parsing summary section"""
        summary = {}
        current_section = None
        
        for line in lines:
            if line.startswith('📊 LOG PARSING SUMMARY'):
                continue
            elif line.startswith('Total Steps:'):
                summary['total_steps'] = int(line.split(':')[1].strip())
            elif line.startswith('Controller Events:'):
                summary['controller_events_total'] = int(line.split(':')[1].strip())
            elif line.startswith('Browser Events:'):
                summary['browser_events_total'] = int(line.split(':')[1].strip())
            elif line.startswith('Debug Events:'):
                summary['debug_events_total'] = int(line.split(':')[1].strip())
            elif 'Event Types:' in line:
                current_section = line.replace('Event Types:', '').strip().lower().replace(' ', '_')
                summary[current_section] = {}
            elif line.startswith('  - ') and current_section:
                parts = line.strip('- ').split(':')
                if len(parts) == 2:
                    event_type = parts[0].strip()
                    count = int(parts[1].strip())
                    summary[current_section][event_type] = count
                    
        return summary
    
    def parse_event_list(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse a list of events (controller, browser, or debug)"""
        events = []
        
        for line in lines:
            if line.startswith('  [] '):
                # Parse event line
                event_line = line[5:]  # Remove '  [] '
                
                if ':' in event_line:
                    event_type, description = event_line.split(':', 1)
                    events.append({
                        'type': event_type.strip(),
                        'description': description.strip()
                    })
                else:
                    events.append({
                        'type': 'OTHER',
                        'description': event_line.strip()
                    })
                    
        return events
    
    def parse_step(self, step_lines: List[str]) -> Dict[str, Any]:
        """Parse a single step"""
        step_data = {
            'step_number': None,
            'thinking': '',
            'action': '',
            'evaluation': '',
            'memory_update': '',
            'next_goal': '',
            'execution_time': '',
            'controller_events': [],
            'browser_events': [],
            'debug_events': []
        }
        
        current_section = None
        section_lines = []
        
        for line in step_lines:
            # Check for step number
            step_match = self.step_pattern.match(line)
            if step_match:
                step_data['step_number'] = int(step_match.group(1))
                continue
            
            # Check for section headers
            section_found = False
            for section_name, pattern in self.section_patterns.items():
                if pattern.match(line):
                    # Save previous section
                    if current_section and section_lines:
                        if current_section in ['controller_events', 'browser_events', 'debug_events']:
                            step_data[current_section] = self.parse_event_list(section_lines)
                        else:
                            step_data[current_section] = '\n'.join(section_lines).strip()
                    
                    current_section = section_name
                    section_lines = []
                    section_found = True
                    break
            
            if not section_found and current_section:
                section_lines.append(line)
        
        # Handle the last section
        if current_section and section_lines:
            if current_section in ['controller_events', 'browser_events', 'debug_events']:
                step_data[current_section] = self.parse_event_list(section_lines)
            else:
                step_data[current_section] = '\n'.join(section_lines).strip()
        
        # Parse execution time to extract numeric value
        if step_data['execution_time']:
            time_match = re.search(r'(\d+\.?\d*)s', step_data['execution_time'])
            if time_match:
                step_data['execution_time_seconds'] = float(time_match.group(1))
        
        return step_data
    
    def parse_log_file(self, file_path: str) -> Dict[str, Any]:
        """Parse the entire log file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.parse_log_content(content)
    
    def parse_log_content(self, content: str) -> Dict[str, Any]:
        """Parse log content string"""
        lines = content.split('\n')
        
        result = {
            'header': {},
            'summary': {},
            'steps': []
        }
        
        # Find section boundaries
        header_end = 0
        summary_start = 0
        summary_end = 0
        steps_start = 0
        
        for i, line in enumerate(lines):
            if line.startswith('📊 LOG PARSING SUMMARY'):
                header_end = i
                summary_start = i
            elif line.startswith('STEP 1'):
                summary_end = i
                steps_start = i
                break
        
        # Parse header
        if header_end > 0:
            result['header'] = self.parse_header(lines[:header_end])
        
        # Parse summary
        if summary_start > 0 and summary_end > summary_start:
            result['summary'] = self.parse_summary(lines[summary_start:summary_end])
        
        # Parse steps
        if steps_start > 0:
            steps_lines = lines[steps_start:]
            current_step_lines = []
            
            for line in steps_lines:
                if self.step_pattern.match(line) and current_step_lines:
                    # Process previous step
                    step_data = self.parse_step(current_step_lines)
                    if step_data['step_number'] is not None:
                        result['steps'].append(step_data)
                    current_step_lines = [line]
                else:
                    current_step_lines.append(line)
            
            # Process last step
            if current_step_lines:
                step_data = self.parse_step(current_step_lines)
                if step_data['step_number'] is not None:
                    result['steps'].append(step_data)
        
        return result


# ---------------------------------------------------------------------------
# CLI driver (Table 8 reproduction)
# ---------------------------------------------------------------------------
import argparse
import os
import glob
import sys


def parse_one_model(model: str, category: str, root: str) -> None:
    parser = BrowserLogParser()

    parsed_dir = os.path.join(root, category, f"{model}_parsed")
    output_dir = os.path.join(root, category, f"{model}_parsed_json_format")
    os.makedirs(output_dir, exist_ok=True)

    log_files = glob.glob(f"{parsed_dir}/*/*.log")
    print(f"\n[{model}] {len(log_files)} parsed logs under {parsed_dir}")

    for log_full_path in log_files:
        try:
            path_parts = log_full_path.split(os.sep)
            domain_index = path_parts.index(f"{model}_parsed") + 1
            domain = path_parts[domain_index] if domain_index < len(path_parts) else "unknown"

            file_name = os.path.basename(log_full_path).split(".log")[0]
            domain_output_dir = os.path.join(output_dir, domain)
            os.makedirs(domain_output_dir, exist_ok=True)

            result = parser.parse_log_file(log_full_path)
            final_path = os.path.join(domain_output_dir, f"{file_name}.json")
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"  ✅ {domain}/{file_name}.json")
        except Exception as e:
            print(f"  ❌ {log_full_path}: {e}")


def main() -> int:
    cli = argparse.ArgumentParser(
        description="Convert {model}_parsed/<domain>/*.log into per-task JSON for compute_success_rate.py.",
    )
    cli.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Backbone slugs to convert.",
    )
    cli.add_argument(
        "--categories",
        nargs="+",
        default=["less_sensitive"],
        help="Sensitivity sub-folders. Defaults to less_sensitive.",
    )
    cli.add_argument(
        "--root",
        default="results_output",
        help="Root directory containing <category>/<model>_parsed/ runs.",
    )
    args = cli.parse_args()

    for model in args.models:
        for category in args.categories:
            parse_one_model(model, category, args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
