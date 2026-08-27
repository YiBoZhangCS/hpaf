from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "progprompt_vh"
PROGPROMPT_ROOT = PROJECT_ROOT / "third_party" / "progprompt-vh"
VIRTUALHOME_ROOT = PROJECT_ROOT / "third_party" / "virtualhome"
VIRTUALHOME_SIMULATION = VIRTUALHOME_ROOT / "src" / "virtualhome" / "simulation"
RESULTS_ROOT = EXPERIMENT_ROOT / "results"
PLOTS_ROOT = EXPERIMENT_ROOT / "plots"

