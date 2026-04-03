import re
import shlex
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from sarray.sbatch_parser import parse_sbatch_argv


def quote_shell(value):
    return shlex.quote(str(value))


@dataclass
class SlurmJob:
    shebang: str
    slurm_options: dict[str, str | bool]
    script: str
    args: list[str]

    @classmethod
    def from_sbatch_call(
        cls,
        slurm_file: Path | None,
        cli_opts: dict[str, str | bool] | None = None,
        *args: str,
    ) -> "SlurmJob":
        cli_opts = dict(cli_opts) if cli_opts else {}
        wrap = cli_opts.pop("wrap", None)

        if slurm_file is not None and wrap is not None:
            raise ValueError("--wrap and a script file are mutually exclusive")
        if slurm_file is None and wrap is None:
            raise ValueError("sbatch requires either a script file or --wrap")

        options = {}
        shebang = "#!/bin/bash"

        if wrap is not None:
            # CLI options override nothing (no file to read #SBATCH from)
            options.update(cli_opts)
            return cls(
                shebang=shebang,
                slurm_options=options,
                script=str(wrap),
                args=list(args),
            )

        assert slurm_file is not None
        if not slurm_file.exists():
            raise FileNotFoundError(f"File not found: {slurm_file}")

        script_lines = []
        with slurm_file.open("r") as f:
            lines = f.readlines()
        if not lines:
            return cls(shebang, {}, "", list(args))

        if lines[0].startswith("#!"):
            shebang = lines[0].strip()
            body = lines[1:]
        else:
            body = lines

        sbatch_args = []
        for line in body:
            if line.lstrip().startswith("#SBATCH "):
                # ignore end of line comments and accumulate SBATCH args
                opt_str = re.sub(r"\s+#.*$", "", line.lstrip()[8:]).strip()
                sbatch_args.extend(shlex.split(opt_str))
            else:
                script_lines.append(line)
        if sbatch_args:
            opts, _, _ = parse_sbatch_argv(sbatch_args)
            options.update(opts)

        # CLI options override #SBATCH directives from the file
        if cli_opts:
            options.update(cli_opts)

        return cls(
            shebang=shebang,
            slurm_options=options,
            script="".join(script_lines).strip(),
            args=list(args),
        )

    @property
    def tasks(self) -> list[int]:
        array_arg = str(self.slurm_options.get("array", "0"))

        if "%" in array_arg:  # ignore throttle
            array_arg = array_arg.split("%")[0]

        tasks_groups = array_arg.split(",")
        all_tasks = []

        for group in tasks_groups:
            if "-" in group:
                match = re.match(r"(\d+)-(\d+)(?::(\d+))?", group)
                if match:
                    start = int(match.group(1))
                    stop = int(match.group(2))
                    step = int(match.group(3)) if match.group(3) else 1
                    all_tasks.extend(range(start, stop + 1, step))
            else:
                all_tasks.append(int(group))

        return all_tasks

    def get_script(self) -> str:
        script = self.script
        script = script.replace("$@", " ".join(self.args))
        for i in range(len(self.args), 0, -1):
            value = self.args[i - 1]
            pattern = rf"\$(\{{{i}\}}|{i})(?!\d)"
            script = re.sub(pattern, value, script)
        return script


@dataclass
class SlurmJobList:
    jobs: list[SlurmJob]
    offsets: list[int]
    total_tasks: int

    @staticmethod
    def check_compatible(jobs: list[SlurmJob]) -> None:
        if len(jobs) < 2:
            return
        ref = {k: v for k, v in jobs[0].slurm_options.items() if k != "array"}
        for job in jobs[1:]:
            other = {k: v for k, v in job.slurm_options.items() if k != "array"}
            if other != ref:
                diff_keys = set(ref) ^ set(other) | {
                    k for k in ref if ref.get(k) != other.get(k)
                }
                raise ValueError(
                    "Incompatible SBATCH options across jobs "
                    f"(differing keys: {', '.join(sorted(diff_keys))})"
                )

    @classmethod
    def from_slurm_jobs(cls, jobs: list[SlurmJob]) -> "SlurmJobList":
        cls.check_compatible(jobs)
        offsets = []
        current_offset = 0

        for job in jobs:
            offsets.append(current_offset)
            current_offset += len(job.tasks)

        return cls(
            jobs=jobs,
            offsets=offsets,
            total_tasks=current_offset,
        )

    def get_job_info(self, global_id: int) -> tuple[SlurmJob, int]:
        if not (0 <= global_id < self.total_tasks):
            raise IndexError(f"Global ID {global_id} out of bounds.")

        job_index = bisect_right(self.offsets, global_id) - 1
        target_job = self.jobs[job_index]
        relative_index = global_id - self.offsets[job_index]
        slurm_task_id = target_job.tasks[relative_index]
        return target_job, slurm_task_id

    def make_slurm_job_array(
        self,
        throttle: int | None = None,
        overrides: dict[str, str | bool] | None = None,
    ) -> str:
        template_dir = Path(__file__).parent
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["quote_shell"] = quote_shell

        template = env.get_template("template.jinja")

        slurm_options = {**self.jobs[0].slurm_options, **(overrides or {})}

        return template.render(
            jobs=self.jobs,
            slurm_options=slurm_options,
            offsets=self.offsets,
            total_tasks=self.total_tasks,
            throttle=throttle,
        )
