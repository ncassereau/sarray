import simple_parsing

from sarray.cancel import cmd_cancel
from sarray.listen import cmd_listen
from sarray.submit import SubmitConfig, cmd_submit
from sarray.throttle import ThrottleConfig, cmd_throttle


def main():
    parser = simple_parsing.ArgumentParser(
        prog="sarray",
        description="Merge multiple Slurm job arrays into one.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "listen", help="Start an interactive listen session (spawns a subshell)"
    )

    p_submit = sub.add_parser("submit", help="Generate and submit the merged job array")
    p_submit.add_arguments(SubmitConfig, dest="config")

    sub.add_parser("cancel", help="Cancel a listen session")

    p_throttle = sub.add_parser("throttle")
    p_throttle.add_arguments(ThrottleConfig, dest="config")

    args = parser.parse_args()

    if args.command == "listen":
        cmd_listen()
    elif args.command == "submit":
        cmd_submit(args.config)
    elif args.command == "cancel":
        cmd_cancel()
    elif args.command == "throttle":
        cmd_throttle(args.config)


if __name__ == "__main__":
    main()
