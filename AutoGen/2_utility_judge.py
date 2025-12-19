import re
import os
import json
import glob
from typing import List, Dict, Any
from tqdm import tqdm
import colorama
from colorama import Fore, Style
from openai import OpenAI
from dotenv import load_dotenv
import argparse

# Initialize colorama
colorama.init()

# Load environment variables
load_dotenv()
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def extract_persona_number(filename):
    match = re.search(r'persona_(\d+)', filename)
    if match:
        return int(match.group(1))
    return 0  # Default value if no match found

def extract_persona_name_from_filename(filename):
    """Extract persona name from filename"""
    # Remove _eval.json and extract the persona part
    base_name = os.path.basename(filename).replace('_eval.json', '')
    # Convert format like persona_4_Michael_Thompson to Michael Thompson
    match = re.search(r'persona_\d+_(.+)', base_name)
    if match:
        return match.group(1).replace('_', ' ')
    return base_name

class WebAgentActionParser:
    def __init__(self):
        # Pattern to identify TextMessage sections
        self.textmessage_pattern = re.compile(r'--- TextMessage ---\s*(.*?)(?=(?:--- TextMessage ---|--- MultiModalMessage ---|$))', re.DOTALL)
        
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
                print(f"{Fore.RED}Error parsing section: {str(e)}{Style.RESET_ALL}")
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
    
    def parse_json_file(self, file_path: str) -> Dict:
        """Parse a JSON file directly"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"{Fore.RED}Error reading JSON file {file_path}: {str(e)}{Style.RESET_ALL}")
            return {}

def create_task_completion_prompt(final_output, original_task):
    """Create prompt for LLM to evaluate task completion success"""
    
    prompt = f"""You are evaluating an AI web surfing agent's performance on completing a specified task.

ORIGINAL TASK:
{original_task}

FINAL OUTPUT FROM AI AGENT:
{final_output}

EVALUATION CRITERIA:
Please evaluate the AI agent's performance on completing the requested task based on the following criteria:

1. **Task Completion**: Did the agent successfully complete the main objective?
2. **Information Accuracy**: Is the information provided correct and relevant?
3. **Comprehensiveness**: Did the agent address all parts of the task?
4. **Information Organization**: Is the response well-structured and easy to understand?

INSTRUCTIONS:
- Focus only on how well the agent completed the assigned task
- Consider what a helpful response to this specific task would look like
- Be objective in your assessment, considering both strengths and limitations
- Provide specific examples from the final output to support your evaluation

OUTPUT FORMAT (JSON):
{{
  "task_completion_status": "✅ Success" or "❌ Fail",
  "completion_assessment": "detailed explanation of what the agent did well and where it fell short"
}}

IMPORTANT: The "task_completion_status" MUST be exactly "✅ Success" if the agent successfully completed the task, or "❌ Fail" if it did not. Do not use any other format.
"""

    return prompt

def evaluate_task_completion(json_file_path):
    """Evaluate task completion from a JSON file"""
    try:
        # Load JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            steps_data = json.load(f)
        
        # Get the original task from the first step
        original_task = steps_data.get("step_1", "")
        
        # Get the final output from the last step (highest number)
        last_step_key = max(steps_data.keys(), key=lambda x: int(x.split('_')[1]))
        final_output = steps_data[last_step_key]
        
        # Create evaluation prompt
        evaluation_prompt = create_task_completion_prompt(final_output, original_task)
        
        # Send to GPT-4 for evaluation
        try:
            print(f"{Fore.CYAN}Evaluating task completion...{Style.RESET_ALL}")
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",  # Using GPT-4.1-mini for evaluation
                messages=[
                    {"role": "system", "content": "You are an expert evaluator of AI assistant task completion."},
                    {"role": "user", "content": evaluation_prompt}
                ]
            )
            
            evaluation_result = response.choices[0].message.content
            
            # Try to parse as JSON
            try:
                result_json = json.loads(evaluation_result)
                task_completion_status = result_json.get("task_completion_status", "❌ Fail")
                
                # Color based on status
                color = Fore.GREEN if "Success" in task_completion_status else Fore.RED
                
                print(f"\n{color}{'='*80}")
                print(f"TASK COMPLETION EVALUATION")
                print(f"{'='*80}")
                print(f"Status: {task_completion_status}")
                print(f"Assessment: {result_json.get('completion_assessment', '')[:200]}...")
                print(f"{'='*80}{Style.RESET_ALL}\n")
                
                return result_json
            
            except json.JSONDecodeError:
                print(f"{Fore.YELLOW}Could not parse evaluation result as JSON. Returning raw output.{Style.RESET_ALL}")
                return {"task_completion_status": "❌ Fail", "completion_assessment": evaluation_result}
            
        except Exception as e:
            print(f"{Fore.RED}Error during evaluation: {str(e)}{Style.RESET_ALL}")
            return {"task_completion_status": "❌ Fail", "completion_assessment": f"Error: {str(e)}"}
            
    except Exception as e:
        print(f"{Fore.RED}Error processing {json_file_path}: {str(e)}{Style.RESET_ALL}")
        return {"task_completion_status": "❌ Fail", "completion_assessment": f"Error: {str(e)}"}

def main():
    ######################################
    model = "o4-mini"
    prompt_style = "ablation"
    domain_type = "shopping_ebay_email"
    num_personas_to_evaluate = 30
    ######################################


    input_dir = 'results_output_TextMessage'
    output_dir = 'results_utility_eval'
    
    print(f"{Fore.MAGENTA}{'='*80}")
    print(f"EVALUATING TASK COMPLETION")
    print(f"{'='*80}")
    print(f"Model: {model}")
    print(f"Prompt Style: {prompt_style}")
    print(f"Domain Type: {domain_type}")
    print(f"Number of Evaluations: {num_personas_to_evaluate}")
    print(f"{'='*80}{Style.RESET_ALL}")
    
    # Create specific output directory
    specific_output_dir = os.path.join(output_dir, domain_type, model)
    os.makedirs(specific_output_dir, exist_ok=True)
    
    # Find all JSON files matching the domain pattern
    json_pattern = os.path.join(input_dir, f"{prompt_style}/{model}/{domain_type}/*_eval.json")
    all_json_files = glob.glob(json_pattern)
    
    # If no files found with domain in name, try all JSON files
    if not all_json_files:
        json_pattern = os.path.join(input_dir, "*_eval.json")
        all_json_files = glob.glob(json_pattern)
    
    # Sort by persona number
    sorted_json_files = sorted(all_json_files, key=extract_persona_number)[:num_personas_to_evaluate]
    
    print(f"Found {len(sorted_json_files)} JSON files to evaluate (out of {len(all_json_files)} total)")
    
    results_summary = {}
    
    # Process each JSON file
    for file_idx, json_file_path in enumerate(tqdm(sorted_json_files, desc="Evaluating files")):
        file_name = os.path.basename(json_file_path)
        persona_name = extract_persona_name_from_filename(file_name)
        
        print(f"\n{Fore.CYAN}Processing {file_idx+1}/{len(sorted_json_files)}: {persona_name}{Style.RESET_ALL}")
        
        # Output file path
        output_file = os.path.join(specific_output_dir, f"{file_name.replace('_eval.json', '')}_evaluation.json")
        
        # Skip if already processed
        if os.path.exists(output_file):
            print(f"{Fore.YELLOW}Already evaluated. Skipping...{Style.RESET_ALL}")
            
            # Load existing evaluation for summary
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_eval = json.load(f)
                    results_summary[persona_name] = {
                        "task_completion_status": existing_eval.get("task_completion_status", "❌ Fail")
                    }
            except:
                pass
                
            continue
        
        # Evaluate task completion
        evaluation = evaluate_task_completion(json_file_path)
        
        # Save evaluation
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}Saved evaluation to {output_file}{Style.RESET_ALL}")
        
        # Add to summary
        results_summary[persona_name] = {
            "task_completion_status": evaluation.get("task_completion_status", "❌ Fail")
        }
    
    # Save summary
    summary_file = os.path.join(specific_output_dir, "evaluation_summary.json")
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)
    
    # Calculate statistics
    if results_summary:
        success_count = sum(1 for data in results_summary.values() if "Success" in data.get("task_completion_status", ""))
        success_rate = success_count / len(results_summary) if results_summary else 0
        
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"EVALUATION SUMMARY")
        print(f"{'='*80}")
        print(f"Total evaluations: {len(results_summary)}")
        print(f"Success count: {success_count}/{len(results_summary)}")
        print(f"Success rate: {success_rate:.2%}")
        print(f"{'='*80}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()