import re
import os
import json
from typing import List, Dict, Any
import glob

class WebAgentActionParser:
    def __init__(self):
        # Pattern to identify TextMessage sections
        self.textmessage_pattern = re.compile(r'--- TextMessage ---\s*(.*?)(?=(?:--- TextMessage ---|--- MultiModalMessage ---|$))', re.DOTALL)
        
        # Original pattern for MultiModalMessage sections (keeping for reference)
        self.multimodal_pattern = re.compile(r'--- MultiModalMessage ---\s*(\[.*?<autogen_core\._image\.Image object at.*?\])', re.DOTALL)
        
    def parse_log_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse the log content and extract actions from TextMessage sections"""
        # Find all TextMessage sections
        textmessage_sections = self.textmessage_pattern.findall(content)
        
        actions = []
        for section in textmessage_sections:
            try:
                # Clean up the text content
                action_text = section.strip()
                
                # Add the cleaned action to our list if it's not empty
                if action_text:
                    actions.append({
                        "action": action_text
                    })
            except Exception as e:
                print(f"Error parsing section: {str(e)}")
                continue
            
        return actions
    
    def parse_log_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse a log file and extract TextMessage actions"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self.parse_log_content(content)
        except UnicodeDecodeError:
            # Try with a different encoding if utf-8 fails
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
            
            return self.parse_log_content(content)
    
    def save_actions(self, actions: List[Dict[str, Any]], output_file_path: str):
        """Save the extracted actions to a JSON file"""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        # Format the actions as a JSON object where each step is keyed by its position
        steps_dict = {}
        for i, action in enumerate(actions, start=1):
            # Store the full action text
            steps_dict[f"step_{i}"] = action["action"]
        
        # Save the JSON file
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(steps_dict, f, indent=2, ensure_ascii=False)
            
        return output_file_path

def process_all_logs(input_dir: str, output_dir: str):
    """Process all log files in the given directory and save results in a new directory structure"""
    parser = WebAgentActionParser()
    
    # Find all log files
    log_pattern = os.path.join(input_dir, "**", "*.log")
    log_files = glob.glob(log_pattern, recursive=True)
    
    print(f"Found {len(log_files)} log files to process")
    
    for log_file in log_files:
        try:
            # Determine the output path
            # Replace .log with _eval.json while keeping the same directory structure
            output_file = log_file.replace('.log', '_eval.json')
            output_file = output_file.replace(input_dir, output_dir)
            
            # Parse the log file
            actions = parser.parse_log_file(log_file)
            
            if actions:
                # Save the actions
                parser.save_actions(actions, output_file)
                print(f"Processed {log_file} → {output_file} ({len(actions)} actions)")
            else:
                print(f"No actions found in {log_file}")
                
        except Exception as e:
            print(f"Error processing {log_file}: {str(e)}")
    
    print("Processing complete")

def main():
    # Define input directory
    input_dir = "results_output_be_careful/less_sensitive"  # Path to your log files
    output_dir = "results_output_be_careful_TextMessage/less_sensitive"

    os.makedirs(output_dir, exist_ok=True)
    
    process_all_logs(input_dir, output_dir)

if __name__ == "__main__":
    main()