import re
import os
import json
from typing import List, Dict, Any
import glob

class WebAgentActionParser:
    def __init__(self):
        # Pattern to identify complete MultiModalMessage sections
        self.multimodal_pattern = re.compile(r'--- MultiModalMessage ---\s*(\[.*?<autogen_core\._image\.Image object at.*?\])', re.DOTALL)
        
    def parse_log_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse the log content and extract actions from MultiModalMessage sections"""
        # Find all MultiModalMessage sections
        multimodal_sections = self.multimodal_pattern.findall(content)
        
        actions = []
        for section in multimodal_sections:
            try:
                # Extract the text part (everything before the image object reference)
                if "<autogen_core._image.Image object at" in section:
                    # Find the position of the image object reference
                    img_pos = section.find("<autogen_core._image.Image object at")
                    
                    # Extract text up to that position
                    action_text = section[:img_pos].strip()
                    
                    # Remove surrounding brackets and quotes if present
                    if action_text.startswith('['):
                        action_text = action_text[1:]
                    if action_text.startswith("'") and action_text.endswith("'"):
                        action_text = action_text[1:-1]
                    elif action_text.startswith('"') and action_text.endswith('"'):
                        action_text = action_text[1:-1]
                    
                    # Add the cleaned action to our list
                    if action_text:
                        actions.append({
                            "action": action_text
                        })
            except Exception as e:
                print(f"Error parsing section: {str(e)}")
                continue
            
        return actions
    
    def parse_log_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse a log file and extract MultiModalMessage actions"""
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
    output_dir = "results_output_processed_be_careful/less_sensitive"

    os.makedirs(output_dir, exist_ok=True)
    
    process_all_logs(input_dir, output_dir)

if __name__ == "__main__":
    main()