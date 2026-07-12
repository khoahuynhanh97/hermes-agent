import sys
import os
import json
import glob
from pathlib import Path

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.job_watcher import JobWorker

def main():
    # Read settings
    settings_path = Path("scratch/agent_settings.json")
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                if not settings.get("enabled", True):
                    print("Agent polling is disabled locally.")
                    return
        except Exception:
            pass

    inbox_dir = Path(".agent_jobs/inbox")
    job_files = glob.glob(str(inbox_dir / "*.json"))
    
    if not job_files:
        print("No pending jobs found in inbox.")
        return

    worker = JobWorker()
    processing_dir = Path(".agent_jobs/processing")
    processing_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir = Path(".agent_jobs/outbox")
    outbox_dir.mkdir(parents=True, exist_ok=True)
    failed_dir = Path(".agent_jobs/failed")
    failed_dir.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(job_files)} pending job(s) in inbox.")
    
    for fpath_str in job_files:
        job_file = Path(fpath_str)
        try:
            with open(job_file, "r", encoding="utf-8") as f:
                job = json.load(f)
            
            job_id = job["job_id"]
            print(f"\n--- Processing Job: {job_id} ---")
            
            # Move to processing
            processing_file = processing_dir / job_file.name
            job_file.rename(processing_file)
            
            # Run tasks
            files_created, summary = worker.execute_job_tasks(job)
            print(f"Job {job_id} completed successfully!")
            
            # Write done file in outbox
            done_file = outbox_dir / f"{job_id}.done.json"
            done_data = {
                "job_id": job_id,
                "status": "done",
                "project_slug": job["target"].get("project_slug"),
                "output_dir": job["target"].get("output_dir"),
                "files_created": files_created,
                "summary": summary
            }
            with open(done_file, "w", encoding="utf-8") as out_f:
                json.dump(done_data, out_f, ensure_ascii=False, indent=2)
                
            print(f"Done file written: {done_file}")
            
            # Clean up processing
            if processing_file.exists():
                processing_file.unlink()
                
        except Exception as e:
            print(f"Error processing job {job_file.name}: {e}")
            # Move to failed
            if 'processing_file' in locals() and processing_file.exists():
                processing_file.rename(failed_dir / job_file.name)
            elif job_file.exists():
                job_file.rename(failed_dir / job_file.name)

if __name__ == "__main__":
    main()
