import subprocess
import uuid
import os
from datetime import datetime

LOG_DIR = "logs"

COMMANDS = {
    "lint": "verilator --lint-only top.v",
    "testbench": "iverilog -o simv top.v tb_top.v && vvp simv"
}

def run_command(action, project_path):

    if action not in COMMANDS:
        return {"error": "unknown action"}

    job_id = str(uuid.uuid4())[:8]

    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = f"{LOG_DIR}/job_{job_id}.log"

    cmd = COMMANDS[action]

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=project_path
    )

    with open(log_file, "w") as f:
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)

    return {
        "job_id": job_id,
        "action": action,
        "log_file": log_file,
        "code": result.returncode
    }     
