#!/usr/bin/env python3
"""
Alternative approach: Use subprocess with tee to capture ALL output
This guarantees that every single character printed to terminal is saved
"""

import glob
import random
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import json

def create_agent_script(task: str, test_id: str, domain, model):
    """Create a temporary script file for the agent"""
    
    # Properly escape the task string for Python code
    import json
    task_escaped = json.dumps(task)
    test_id_escaped = json.dumps(test_id)
    
    script_content = f'''
import asyncio
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, BrowserSession, BrowserProfile
from browser_use.llm import ChatOpenAI, ChatAnthropic, ChatGoogle

async def main():
    # Load task from JSON to handle special characters
    task = {task_escaped}
    test_id = {test_id_escaped}
    
    print("🚀 Starting browser-use agent...")
    print(f"📝 Task: {{task}}")
    print(f"🏷️  Test ID: {{test_id}}")
    print(f"⏰ Start time: {{datetime.now().isoformat()}}")
    print("-" * 80)
    
    try:
        browser_profile = BrowserProfile(
            headless=True
        )
        session = BrowserSession(browser_profile=browser_profile)

        llm = None

        if "{model}" in ['gpt-4o', 'o3', 'o4-mini']:
            llm = ChatOpenAI(model="{model}", temperature=1.0)
        
        elif "{model}" in ["claude-sonnet-4-0", "claude-sonnet-3-7"]:
            llm = ChatAnthropic(
                model="{model}", 
                temperature=1.0
            )
        
        elif "{model}" in ['gemini-2.5-flash']:
            llm = ChatGoogle(
                model="{model}", 
                temperature=1.0
            )

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=session,
            allowed_domains = ['{domain}']
        )
        
        result = await agent.run()
        
        print("-" * 80)
        print("✅ Task completed successfully!")
        print(f"📊 Result: {{result}}")
        print(f"⏰ End time: {{datetime.now().isoformat()}}")
        
    except Exception as e:
        print(f"❌ Error: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
'''
    
    script_file = Path(f"temp_agent_{test_id}.py")
    with open(script_file, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    return script_file

def run_with_complete_logging(task: str, test_id: str, domain, log_file, model):
    """Run browser-use agent with complete output capture"""
    
    # Create temporary agent script
    script_file = create_agent_script(task, test_id, domain, model)
    
    try:
        print(f"📋 COMPLETE logging to: {log_file}")
        print(f"📊 Monitor in real-time: tail -f {log_file}")
        print(f"🔄 Running agent script: {script_file}")
        print("-" * 80)
        
        # Run with tee to capture everything
        # This captures BOTH stdout and stderr to file while showing in terminal
        cmd = [
            "bash", "-c", 
            f"python {script_file} 2>&1 | tee {log_file}"
        ]
        
        # Execute and wait for completion
        process = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
            text=True
        )
        
        print("-" * 80)
        if process.returncode == 0:
            print("✅ Complete logging successful!")
        else:
            print(f"⚠️  Process completed with return code: {process.returncode}")
        
        print(f"📋 COMPLETE log saved to: {log_file}")
        print(f"📏 Log file size: {log_file.stat().st_size:,} bytes")
        
        # Show log content sample
        print("\n📋 Log file sample (first 15 lines):")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines[:15]):
                print(f"   {i+1:2d}: {line.rstrip()}")
            if len(lines) > 15:
                print(f"   ... and {len(lines)-15:,} more lines")
        
        return log_file
        
    finally:
        # Clean up temporary script
        if script_file.exists():
            script_file.unlink()

def main():
    # Create main logs_json directory
    models = ['gemini-2.5-flash', "gpt-4o", "o3", "o4-mini", "claude-sonnet-4-0", "claude-sonnet-3-7"]
    categories = ["less_sensitive", "medium_sensitive"]
    domains = ['healthcare_webmd', 'legal_findlaw', 'real_estate_zillow', 'shopping_Amazon', 'exploring']
    prompt_type = ['email', 'chat', 'generic']

    ##### Modify #####
    model = "o4-mini"
    sub_folder = "less_sensitive"
    domain = "shopping_Amazon" + '_' + "generic_single"
    ############################################

    folder_name = os.path.join("results_output", sub_folder, model)
    os.makedirs(folder_name, exist_ok=True)

    # json_list = glob.glob(f"tasks/{sub_folder}/*.json")
    json_list = [f'../tasks/{sub_folder}/{domain}.json']
    print(json_list)

    for json_file in json_list:
        template_type = os.path.splitext(os.path.basename(json_file))[0]
        print(template_type)
        print(f"\n🤖 Model: {model}...")
        print(f"\n🔄 Processing {json_file}...")
        
        with open(f"{json_file}", "r", encoding="utf-8") as f:
            task_data = json.load(f)
        
        # Process each persona in the JSON file
        for persona in task_data.get('personas', []):
            persona_id = persona['id']
            persona_name = persona['name']
            task = persona['prompt']
            domain = persona['website']
            test_id = f"persona_{persona_id}_{persona_name.replace(' ', '_')}"
            
            print(f"\n📝 Running persona {persona_id}: {persona_name}")
            # Create logs_json directory structure
            os.makedirs(f"{folder_name}/{template_type}", exist_ok=True)
            log_dir = Path(f"{folder_name}/{template_type}")
            log_dir.mkdir(exist_ok=True)
            
            # Create log file
            # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"{test_id}.log"

            if os.path.exists(log_file):
                print("File exists...")
                continue
            
            log_file = run_with_complete_logging(task, test_id, domain, log_file, model)

            print(f"\n🎉 DONE! Complete log available at: {log_file}")
            print("\n📊 To analyze this log for privacy:")
            print(f"   python log_data_separator.py {log_file}")
            print("-" * 80)

if __name__ == "__main__":
    main()