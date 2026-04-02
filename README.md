# sarray

Merge multiple independent Slurm job arrays into a single `sbatch` submission.

Instead of flooding the scheduler with N separate job arrays, `sarray` combines them into one array job where each task is routed to the right script with the right arguments. This reduces scheduler overhead and makes queue management easier.

## How it works

Given two scripts:

```
# train.slurm  →  --array=0-2  (3 tasks)
# eval.slurm   →  --array=0-4  (5 tasks)
```

`sarray` generates a single array job with `--array=0-7` (8 tasks) and a dispatcher that maps each global task ID back to the right script and local task ID:

```
global 0,1,2     → train.slurm  with SLURM_ARRAY_TASK_ID = 0,1,2
global 3,4,5,6,7 → eval.slurm   with SLURM_ARRAY_TASK_ID = 0,1,2,3,4
```

All `SLURM_ARRAY_TASK_*` environment variables are set correctly in each task.

**Constraint:** all merged jobs must have identical `#SBATCH` options (same resources, partition, etc.) — only `--array` can differ.

---

## Installation

```bash
pip install sarray
# or
uv add sarray
```

---

## Usage

### Interactive mode (recommended)

Start a listen session — this spawns a subshell where `sbatch` is intercepted:

```bash
sarray listen
```

Your prompt changes to **`[sarray]`** (bold yellow) to indicate you're in a session.

Inside the session, call `sbatch` normally. Every call is queued instead of submitted:

```bash
sbatch --array=0-4 train.slurm model_a
sbatch --array=0-4 train.slurm model_b
sbatch eval.slurm
```

When ready, submit everything as one merged array:

```bash
sarray submit
```

Or discard and exit without submitting:

```bash
sarray cancel
```

Both commands exit the subshell automatically.

---

### Standalone mode

Pass a queue file directly — no subshell needed:

```bash
sarray submit jobs.conf
```

Where `jobs.conf` contains one `sbatch` call per line:

```
sbatch --array=0-2 train.slurm lr=0.01
sbatch --array=0-2 train.slurm lr=0.001
sbatch --array=0-2 train.slurm lr=0.0001
```

Read from stdin:

```bash
echo "sbatch job.slurm" | sarray submit -
```

---

## Commands

### `sarray listen`

Spawns an interactive subshell with a fake `sbatch` that queues calls into a temporary file. The real `sbatch` is shadowed only inside this subshell — your parent shell is unaffected.

Exit the session with `sarray submit` or `sarray cancel`.

---

### `sarray submit [FILE|-]`

Generate and submit the merged job array.

| Argument / Flag | Description |
|---|---|
| `FILE` | Queue file to read (one `sbatch ...` line per job). Omit to use the active listen session. |
| `-` | Read queue from stdin. |
| `-o`, `--output FILE` | Save the generated script to this file (default: `sarray.slurm` in the current directory). |
| `-n`, `--dry-run` | Print the generated script to stdout (syntax-highlighted) without submitting. |
| `-t`, `--throttle N` | Limit the number of simultaneously running tasks (`%N` appended to `--array`). |

The generated script is always written to disk before submission — `sarray.slurm` by default — so you can always inspect what was submitted.

**CLI flags override `#SBATCH` directives.** For example:

```bash
sbatch --mem=8GB job.slurm    # overrides #SBATCH --mem in job.slurm
sbatch --array=0-9 job.slurm  # overrides #SBATCH --array in job.slurm
```

`--wrap` is also supported (no script file needed):

```bash
sbatch --wrap "python train.py" --array=0-4 --mem=16GB
```

---

### `sarray cancel`

Discard the current listen session queue and exit the subshell.

---

### `sarray throttle JOBID --throttle N [--kill]`

Update the concurrent task limit of a running job array without cancelling it.

| Argument / Flag | Description |
|---|---|
| `JOBID` | ID of the running job array. |
| `-t`, `--throttle N` | New maximum number of simultaneously running tasks. |
| `-k`, `--kill` | Requeue tasks currently running above the new limit. |

```bash
# Slow down a running array to 2 concurrent tasks
sarray throttle 123456 --throttle 2

# Slow down and immediately requeue the excess running tasks
sarray throttle 123456 --throttle 2 --kill
```

The command checks that the job exists, belongs to you, and is a job array before updating.

---

## Example workflow

```bash
$ sarray listen
[sarray] $ sbatch --array=0-9 experiments/baseline.slurm
[sarray] $ sbatch --array=0-9 experiments/ablation.slurm
[sarray] $ sbatch --array=0-9 experiments/ablation2.slurm
[sarray] $ sarray submit --dry-run   # preview the merged script
[sarray] $ sarray submit             # submit and exit the session
Submitted batch job 42137
$
```

Result: one job array with 30 tasks instead of 3 separate submissions.
